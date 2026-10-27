"""Owner-started foreground agent. Unix peer UID, fixed operations, one run."""
import argparse
import base64
import json
import os
from pathlib import Path
import signal
import socket
import socketserver
import stat
import time
import struct
import threading
import uuid

from ccreplay.lab_protocol import MAX_MESSAGE,Message
from ccreplay.lab_runner import Run,TERMINAL,preflight,cleanup_struct_ops
from ccreplay.storage import atomic_json,utc


class Agent:
    def __init__(self,uid,gid,socket_path):
        if os.geteuid()!=0:raise ValueError('Lab agent requires root; Studio must run separately as a normal user')
        if uid<=0 or gid<=0:raise ValueError('Choose the invoking normal uid/gid, not root')
        self.uid,self.gid=uid,gid
        self.socket=Path(socket_path)
        self.socket.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if self.socket.parent.is_symlink() or self.socket.parent.stat().st_uid not in (0,uid):raise ValueError('Unsafe agent runtime directory')
        os.chown(self.socket.parent,uid,gid);os.chmod(self.socket.parent,0o700)
        self.run_root=self.socket.parent/('session-'+uuid.uuid4().hex)
        self.run_root.mkdir(mode=0o700);os.chown(self.run_root,uid,gid)
        self.journal_root=Path('/run')/('ccreplay-lab-'+str(uid))
        self.journal_root.mkdir(mode=0o700,exist_ok=True)
        if self.journal_root.is_symlink() or self.journal_root.stat().st_uid!=0:
            raise ValueError('Unsafe root journal directory')
        os.chmod(self.journal_root,0o700)
        self.runs={};self.lock=threading.Lock();self.active=None
        self.recover()

    def recover(self):
        # Only this owner's private session manifests and exact process start IDs.
        for manifest in self.journal_root.glob('*.json'):
            try:
                meta=json.loads(manifest.read_text())
                if meta['status'] in TERMINAL:continue
                for process in reversed(meta.get('resources',{}).get('processes',[])):
                    pid=process['pid'];stat=Path(f'/proc/{pid}/stat')
                    if stat.exists() and stat.read_text().split()[21]==process['start_ticks']:
                        try:
                            os.killpg(pid,signal.SIGTERM)
                            deadline=time.monotonic()+2
                            while stat.exists() and stat.read_text().split()[21]==process['start_ticks'] and time.monotonic()<deadline:time.sleep(.05)
                            if stat.exists() and stat.read_text().split()[21]==process['start_ticks']:os.killpg(pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                failures=cleanup_struct_ops(meta.get('resources',{}).get('struct_ops',[]))
                for name in meta.get('resources',{}).get('namespaces',[]):
                    # Names have internal run-ID prefix and were journaled after successful creation.
                    if name.startswith('cc'+meta['id'][:7]):
                        result=__import__('subprocess').run(['ip','netns','delete',name],capture_output=True,text=True,timeout=5)
                        if result.returncode and Path('/run/netns',name).exists():failures.append(result.stderr)
                owner_manifest=Path(meta['manifest_path'])
                if owner_manifest.exists() and not owner_manifest.is_symlink():
                    value=json.loads(owner_manifest.read_text())
                    value.update(status='interrupted',error='Agent restarted; owned resources recovered' if not failures else 'Agent restarted; cleanup requires attention',finished_at=utc(),
                                 cleanup={'completed':not failures,'errors':failures,'owned_namespaces':meta.get('resources',{}).get('namespaces',[])})
                    value['resources']['active']=False
                    if value['config'].get('capture'):
                        value['recording']={'integrity':'partial','replayable':False,'reason':'Agent interrupted before capture validation'}
                    atomic_json(owner_manifest,value)
                meta['status']='interrupted'
                atomic_json(manifest,meta)
            except (OSError,ValueError,KeyError):continue

    def manifests(self):
        values=[]
        for p in self.socket.parent.glob('session-*/*/manifest.json'):
            try:values.append(json.loads(p.read_text()))
            except (OSError,ValueError):pass
        return sorted(values,key=lambda v:v['created_at'],reverse=True)

    def locate(self,rid):
        if rid in self.runs:return self.runs[rid].path
        for p in self.socket.parent.glob('session-*/'+rid+'/manifest.json'):
            if p.is_file():return p.parent
        raise KeyError('Unknown lab run')

    def handle(self,msg):
        op=msg.operation
        if op=='capabilities':
            value=preflight();value.update(agent_connected=True,owner_uid=self.uid,owner_gid=self.gid,can_run_lab=all(value['tools'][k] for k in ('ip','tc','ss','iperf3','ethtool')))
            history=self.manifests()
            qualified=next((v for v in history if v.get('kernel')==value['kernel'] and v.get('actual_readback') and v.get('cleanup',{}).get('completed')),None)
            if qualified:value['native']={'status':'available','last_run_id':qualified['id'],'reason':'Owned namespace/qdisc setup executed successfully'}
            for cca in value['recorders']:
                passed=next((v for v in history if v.get('kernel')==value['kernel'] and v['config']['controller']==cca and v.get('recording') and v['recording'].get('self_replay',{}).get('verdict')=='PASS'),None)
                if passed:value['recorders'][cca]={'status':'available','last_successful_check':passed['finished_at'],'run_id':passed['id'],'reason':'Actual attach, selected data controller and self-replay PASS'}
            return value
        if op=='start':
            if msg.config is None:raise ValueError('Run config required')
            with self.lock:
                if self.active and (self.active.meta['status'] not in TERMINAL or not self.active.meta.get('cleanup')):raise ValueError('One network run is already active')
                workload=msg.workload
                if not isinstance(workload,dict) or workload.get('kind') not in ('script','iperf3'):raise ValueError('Unsupported workload')
                run=Run(self.run_root,self.uid,self.gid,msg.config.model_dump(),workload,self.journal_root)
                self.runs[run.id]=run;self.active=run
                thread=threading.Thread(target=run.execute,daemon=True);thread.start()
            return run.meta
        if op=='list':return self.manifests()
        if not msg.run_id:raise ValueError('run_id required')
        path=self.locate(msg.run_id)
        if op=='status':return json.loads((path/'manifest.json').read_text())
        if op in ('stop','cancel'):
            run=self.runs.get(msg.run_id)
            if run and run.meta['status'] not in TERMINAL:
                if op=='cancel':run.cancel_event.set()
                run.stop_event.set()
            return json.loads((path/'manifest.json').read_text())
        if op in ('samples','log'):
            p=path/('samples.jsonl' if op=='samples' else 'log.jsonl')
            data=[];budget=0
            if p.exists():
                with p.open() as stream:
                    for line in stream:
                        try:value=json.loads(line)
                        except ValueError:continue
                        if value['cursor']>msg.after:
                            size=len(line.encode())
                            if data and budget+size>MAX_MESSAGE-4096:break
                            data.append(value);budget+=size
                        if len(data)>=msg.limit:break
            return {'items':data,'cursor':data[-1]['cursor'] if data else msg.after,'truncated':False}
        if op=='artifact':
            if not msg.artifact:raise ValueError('Artifact name required')
            p=path/msg.artifact
            if not p.is_file():raise ValueError('Artifact unavailable')
            with p.open('rb') as stream:stream.seek(msg.offset);data=stream.read(128*1024)
            return {'data':base64.b64encode(data).decode(),'bytes':len(data),'total_bytes':p.stat().st_size}
        raise ValueError('Unknown operation')

    def close(self):
        for run in self.runs.values():
            if run.meta['status'] not in TERMINAL:run.cancel_event.set();run.stop_event.set()
        import time
        deadline=time.monotonic()+15
        while any(r.meta['status'] not in TERMINAL or not r.meta.get('cleanup') for r in self.runs.values()) and time.monotonic()<deadline:time.sleep(.1)


def main():
    p=argparse.ArgumentParser();p.add_argument('--uid',type=int,required=True);p.add_argument('--gid',type=int,required=True);p.add_argument('--socket',required=True);args=p.parse_args()
    socket_path=Path(args.socket)
    if socket_path.exists() or socket_path.is_symlink():
        info=socket_path.lstat()
        if socket_path.is_symlink() or not stat.S_ISSOCK(info.st_mode) or info.st_uid!=args.uid:
            raise SystemExit('Refusing to replace an unknown socket path')
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as probe:
            probe.settimeout(1)
            try:probe.connect(str(socket_path))
            except (ConnectionRefusedError,FileNotFoundError):socket_path.unlink(missing_ok=True)
            else:raise SystemExit('An agent is already listening; its runs were left untouched')
    agent=Agent(args.uid,args.gid,args.socket)
    class Handler(socketserver.StreamRequestHandler):
        timeout=15
        def handle(self):
            try:
                _,uid,_=struct.unpack('3i',self.request.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                if uid!=agent.uid:raise PermissionError('Peer UID does not match agent owner')
                line=self.rfile.readline(MAX_MESSAGE+1)
                if len(line)>MAX_MESSAGE or not line.endswith(b'\n'):raise ValueError('Message too large/incomplete')
                msg=Message.model_validate_json(line)
                result={'ok':True,'result':agent.handle(msg)}
            except Exception as exc:result={'ok':False,'error':f'{type(exc).__name__}: {exc}'}
            encoded=json.dumps(result,default=str).encode()+b'\n'
            if len(encoded)>MAX_MESSAGE:encoded=b'{"ok":false,"error":"Response too large; request a smaller page"}\n'
            self.wfile.write(encoded)
    if agent.socket.exists():raise SystemExit('Agent socket already exists; stop that owner session before starting another')
    server=socketserver.ThreadingUnixStreamServer(str(agent.socket),Handler)
    os.chmod(agent.socket,0o600);os.chown(agent.socket,args.uid,args.gid)
    def stop(*_):threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    print('Lab agent ready:',agent.socket,'owner uid',agent.uid,flush=True)
    try:server.serve_forever(poll_interval=.25)
    finally:agent.close();server.server_close();agent.socket.unlink(missing_ok=True)

if __name__=='__main__':main()
