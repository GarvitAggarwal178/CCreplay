"""Fixed Linux orchestration. Only processes/namespaces created by this run are touched."""
import base64
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid

from ccreplay.lab_metrics import socket_samples,select_data_flow,queue_sample,receiver_summary
from ccreplay.lab_protocol import Scenario
from ccreplay.storage import ROOT,atomic_json,digest,utc

TERMINAL={'completed','failed','cancelled','interrupted'}


def recorder_maps(pid, name):
    """Identify struct_ops maps through this recorder's actual open FDs."""
    owned=[]
    for fd in Path(f'/proc/{pid}/fdinfo').glob('*'):
        for line in fd.read_text().splitlines():
            if line.startswith('map_id:'):
                mid=int(line.split(':',1)[1])
                result=subprocess.run(['bpftool','-j','map','show','id',str(mid)],capture_output=True,text=True,timeout=5)
                if result.returncode:continue
                info=json.loads(result.stdout)
                if isinstance(info,list):info=info[0]
                if info.get('type')=='struct_ops' and info.get('name')==name:
                    owned.append({k:info[k] for k in ('id','name','btf_id')})
    return owned


def cleanup_struct_ops(owned):
    """Unregister only exact journaled identities, including after SIGKILL."""
    errors=[]
    for expected in owned:
        mid=str(expected['id'])
        result=subprocess.run(['bpftool','-j','map','show','id',mid],capture_output=True,text=True,timeout=5)
        if result.returncode:continue  # Already destroyed by graceful recorder exit.
        info=json.loads(result.stdout)
        if isinstance(info,list):info=info[0]
        if info.get('type')!='struct_ops' or any(info.get(k)!=v for k,v in expected.items()):
            errors.append('Owned BPF map identity changed: '+mid);continue
        state=subprocess.run(['bpftool','-j','map','dump','id',mid],capture_output=True,text=True,timeout=5)
        if state.returncode:
            errors.append('Cannot inspect owned BPF map '+mid);continue
        if 'BPF_STRUCT_OPS_STATE_INUSE' in state.stdout:
            removed=subprocess.run(['bpftool','struct_ops','unregister','id',mid],capture_output=True,text=True,timeout=5)
            if removed.returncode:errors.append('Cannot unregister owned BPF map '+mid+': '+removed.stderr)
    return errors


def preflight():
    tools={name:shutil.which(name) for name in ['ip','tc','ss','ethtool','iperf3','clang','bpftool','pkg-config']}
    build=ROOT/'build_local'
    kernel=platform.release()
    # The exact HZ is a kernel config fact, not userspace CLK_TCK.
    hz=None
    import gzip,re
    for candidate in [Path('/proc/config.gz'),Path('/boot/config-'+kernel)]:
        if candidate.exists():
            try:
                data=gzip.open(candidate,'rt').read() if candidate.suffix=='.gz' else candidate.read_text()
                match=re.search(r'^CONFIG_HZ=(\d+)$',data,re.M)
                if match:hz=int(match[1]);break
            except OSError:pass
    built=(build/'BUILD_INFO.txt').read_text() if (build/'BUILD_INFO.txt').exists() else ''
    return {'checked_at':utc(),'kernel':kernel,'uid':os.getuid(),'tools':tools,'btf':Path('/sys/kernel/btf/vmlinux').is_file(),
            'config_hz':hz,'model_hz':250,'model_reference_kernel':'6.18.33.2-microsoft-standard-WSL2','model_kernel_matches':kernel=='6.18.33.2-microsoft-standard-WSL2','built_for_current_kernel':kernel in built,'build_info':built,
            'native':{'status':'unverified' if all(tools[k] for k in ('ip','tc','ss','ethtool','iperf3')) else 'unavailable',
                      'reason':'Actual namespace/qdisc support is checked by an owned run'},
            'recorders':{c:{'status':'unverified' if (build/('ccr_recorder'+('' if c=='reno' else '_'+c))).exists() else 'unavailable',
                            'reason':'Requires active attach and recorded self-replay qualification'} for c in ['reno','cubic','covegas']}}


class Run:
    def __init__(self,root,uid,gid,config,workload,journal_root=None):
        self.id=uuid.uuid4().hex
        self.path=Path(root)/self.id;self.path.mkdir(mode=0o700)
        self.journal_path=Path(journal_root)/(self.id+".json") if journal_root else None
        self.uid,self.gid=uid,gid
        self.config=Scenario.model_validate(config)
        self.workload=workload
        self.stop_event=threading.Event();self.cancel_event=threading.Event()
        self.log_lock=threading.Lock();self.processes=[];self.streams=[];self.namespaces=[]
        self.origin=time.monotonic();self.samples=[];self.logs=[];self.output_offsets={};self.log_bytes=0
        self.meta={'id':self.id,'kernel':platform.release(),'status':'queued','phase':'queued','created_at':utc(),'config':self.config.model_dump(),
                   'workload':{k:v for k,v in workload.items() if k!='source'},'instrumentation':'recorded-wrapper' if self.config.capture else 'native-uninstrumented',
                   'artifacts':{},'samples_count':0,'log_truncated':False,'recording':None,'summary':{},'resources':{'namespaces':[],'processes':[]}}
        self.persist()

    def persist(self):
        atomic_json(self.path/'manifest.json',self.meta)
        if self.journal_path:
            atomic_json(self.journal_path,{'id':self.id,'manifest_path':str(self.path/'manifest.json'),
                        'status':self.meta['status'],'resources':self.meta['resources'],
                        'cleanup':self.meta.get('cleanup')})

    def log(self,kind,message):
        with self.log_lock:
            if self.log_bytes >= 10*1024*1024:
                self.meta['log_truncated']=True
                return
            if len(message)>16000:message=message[:16000]+' [truncated]'
            self.log_bytes += len(message.encode())
            entry={'cursor':len(self.logs)+1,'t_s':time.monotonic()-self.origin,'kind':kind,'message':message}
            self.logs.append(entry)
            with (self.path/'log.jsonl').open('a') as f:f.write(json.dumps(entry)+'\n')

    def phase(self,state,description):
        self.meta.update(status=state,phase=description);self.persist();self.log('phase',description)
        if self.cancel_event.is_set():raise InterruptedError('Cancelled by owner')

    def command(self,argv,check=True):
        self.log('command',' '.join(map(str,argv)))
        result=subprocess.run(list(map(str,argv)),capture_output=True,text=True,timeout=8)
        if result.stdout:self.log('stdout',result.stdout)
        if result.stderr:self.log('stderr',result.stderr)
        if check and result.returncode:raise RuntimeError(f"Command exited {result.returncode}: {' '.join(map(str,argv))}: {result.stderr.strip()}")
        return result

    def ns(self,name,*args,check=True):return self.command(['ip','netns','exec',name,*args],check)

    def spawn(self,argv,name):
        self.log('command',' '.join(map(str,argv)))
        out=(self.path/(name+'.stdout')).open('wb');err=(self.path/(name+'.stderr')).open('wb');self.streams.extend([out,err])
        p=subprocess.Popen(list(map(str,argv)),stdout=out,stderr=err,start_new_session=True)
        self.processes.append(p)
        self.meta['resources']['processes'].append({'pid':p.pid,'start_ticks':Path(f'/proc/{p.pid}/stat').read_text().split()[21],'kind':name})
        self.persist();return p

    def terminate(self,p,first=signal.SIGTERM):
        if p is None or p.poll() is not None:return
        try:
            os.killpg(p.pid,first);p.wait(timeout=4)
        except ProcessLookupError:pass
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=3)

    def setup(self):
        suffix=self.id[:7];s,r,d=['cc'+suffix+c for c in 'srd'];self.s,self.r,self.d=s,r,d
        for name in [s,r,d]:
            self.command(['ip','netns','add',name]);self.namespaces.append(name)
            self.meta['resources']['namespaces']=self.namespaces.copy();self.persist()
            self.command(['ip','-n',name,'link','set','lo','up'])
        # Both ends are created directly inside owned namespaces; host links are untouched.
        self.command(['ip','-n',s,'link','add','s0','type','veth','peer','name','r0','netns',r])
        self.command(['ip','-n',r,'link','add','r1','type','veth','peer','name','d0','netns',d])
        for ns,dev,ip in [(s,'s0','10.77.1.1/24'),(r,'r0','10.77.1.2/24'),(r,'r1','10.77.2.1/24'),(d,'d0','10.77.2.2/24')]:
            self.command(['ip','-n',ns,'addr','add',ip,'dev',dev]);self.command(['ip','-n',ns,'link','set',dev,'up'])
            self.ns(ns,'ethtool','-K',dev,'tso','off','gso','off','gro','off',check=False)
        self.command(['ip','-n',s,'route','add','default','via','10.77.1.2'])
        self.command(['ip','-n',d,'route','add','default','via','10.77.2.1'])
        self.ns(r,'sysctl','-w','net.ipv4.ip_forward=1')
        c=self.config
        self.ns(s,'tc','qdisc','add','dev','s0','root','netem','delay',f'{c.delay_ms}ms','loss',f'{c.loss_percent}%')
        self.ns(d,'tc','qdisc','add','dev','d0','root','netem','delay',f'{c.delay_ms}ms')
        self.ns(r,'tc','qdisc','add','dev','r1','root','handle','1:','htb','default','10')
        self.ns(r,'tc','class','add','dev','r1','parent','1:','classid','1:10','htb','rate',f'{c.rate_mbit}mbit','ceil',f'{c.rate_mbit}mbit')
        self.ns(r,'tc','qdisc','add','dev','r1','parent','1:10','handle','10:','bfifo','limit',str(c.queue_bytes))
        self.meta['actual_readback']={'sender':json.loads(self.ns(s,'tc','-j','-s','qdisc','show','dev','s0').stdout),
             'receiver':json.loads(self.ns(d,'tc','-j','-s','qdisc','show','dev','d0').stdout),
             'router':json.loads(self.ns(r,'tc','-j','-s','qdisc','show','dev','r1').stdout),
             'classes':json.loads(self.ns(r,'tc','-j','class','show','dev','r1').stdout),
             'addresses':{'sender':'10.77.1.1','router':['10.77.1.2','10.77.2.1'],'receiver':'10.77.2.2'}}
        self.persist()

    def execute(self):
        recorder=receiver=work=None
        try:
            self.phase('preparing','checking host and creating owned network')
            self.setup()
            cca=self.config.controller
            if self.config.capture:
                self.phase('attaching','attaching callback recorder')
                build=ROOT/'build_local'
                info=preflight()
                if not info['built_for_current_kernel']:raise RuntimeError('Rebuild recorders for this running kernel with scripts/build_bpf.sh')
                if cca!='reno' and (info['config_hz']!=250 or not info['model_kernel_matches']):raise RuntimeError('CUBIC/CoVegas requires verified CONFIG_HZ=250 and source assumptions; use Recorded Reno first')
                available=Path('/proc/sys/net/ipv4/tcp_available_congestion_control').read_text().split()
                if 'ccr_'+cca in available:raise RuntimeError('Recorder controller is already registered by another session; not touching it')
                binary=build/('ccr_recorder'+('' if cca=='reno' else '_'+cca))
                build_manifest=build/'BUILD_INFO.json'
                if not build_manifest.exists():raise RuntimeError('Recorder build manifest missing; run bash scripts/build_bpf.sh')
                recorded_build=json.loads(build_manifest.read_text())
                if recorded_build.get('kernel')!=platform.release():raise RuntimeError('Recorder build kernel mismatch')
                for relative,expected in recorded_build['artifacts'].items():
                    artifact=ROOT/relative
                    if not artifact.is_file() or digest(artifact)!=expected:raise RuntimeError('Recorder build artifact/source changed: '+relative)
                self.meta['recorder_binary_sha256']=digest(binary)
                recorder=self.spawn([binary,self.path/'trace.ccr',self.path/'trace.meta.json',str(self.config.duration_s+15)],'recorder')
                for _ in range(60):
                    if self.cancel_event.is_set():raise InterruptedError('Cancelled during attach')
                    text=(self.path/'recorder.stdout').read_text(errors='replace')
                    if 'ATTACHED' in text:break
                    if recorder.poll() is not None:raise RuntimeError('Recorder attach failed: '+(self.path/'recorder.stderr').read_text(errors='replace')[-6000:])
                    time.sleep(.1)
                else:raise RuntimeError('Timed out waiting for actual recorder ATTACHED')
                self.meta['resources']['struct_ops']=recorder_maps(recorder.pid,'ccr_'+cca)
                if not self.meta['resources']['struct_ops']:raise RuntimeError('Cannot establish recorder BPF map ownership')
                self.persist()
                cca='ccr_'+cca
            self.phase('preparing','waiting for workload receiver')
            if self.workload['kind']=='iperf3':
                receiver=self.spawn(['ip','netns','exec',self.d,'iperf3','-s','-1','-J','-p','5201'],'receiver')
            else:
                # Fixed audited sink; custom source is never imported by root.
                receiver=self.spawn(['ip','netns','exec',self.d,sys.executable,ROOT/'examples/workloads/sink.py'],'receiver')
            for _ in range(30):
                if receiver.poll() is not None:raise RuntimeError('Receiver exited before listening')
                if ':5201' in self.ns(self.d,'ss','-ltn').stdout:break
                time.sleep(.1)
            else:raise RuntimeError('Receiver did not listen')
            if self.workload['kind']=='iperf3':
                argv=['ip','netns','exec',self.s,'iperf3','-c','10.77.2.2','-p','5201','-C',cca,'-t',str(self.config.duration_s),'-J']
            else:
                source=self.workload.get('source','')
                if not source or len(source.encode())>131072:raise ValueError('Invalid workload source length')
                if __import__('hashlib').sha256(source.encode()).hexdigest()!=self.workload.get('sha256'):raise ValueError('Workload revision hash mismatch')
                scripts=self.path/'script';scripts.mkdir(mode=0o700)
                (scripts/'workload.py').write_text(source)
                (self.path/'workload.py').write_text(source)
                shutil.copyfile(ROOT/'examples/workloads/traffic_api.py',scripts/'traffic_api.py')
                os.chown(self.path,self.uid,self.gid);os.chown(scripts,self.uid,self.gid)
                for p in scripts.iterdir():os.chown(p,self.uid,self.gid)
                # The run parent is private to owner; source is staged, never accepted as a path.
                argv=['ip','netns','exec',self.s,'env','-i','PATH=/usr/bin:/bin',
                      f'CCR_CONTROLLER={cca}','CCR_RECEIVER=10.77.2.2','CCR_PORT=5201',
                      os.path.realpath(sys.executable),ROOT/'ccreplay/drop_exec.py','--uid',str(self.uid),'--gid',str(self.gid),scripts/'workload.py']
            self.phase('running','running real TCP workload')
            self.meta.update(started_at=utc(),started_monotonic_ns=str(time.monotonic_ns()),selected_controller=cca);self.persist()
            work=self.spawn(argv,'workload')
            start=time.monotonic();previous=None;locked=None;observed=set();observed_data_flows=set();sample_count=0
            while work.poll() is None:
                if self.cancel_event.is_set():raise InterruptedError('Cancelled by owner')
                if self.stop_event.is_set():break
                if time.monotonic()-start>self.config.duration_s+3:raise TimeoutError('Workload exceeded configured wall-time bound')
                if recorder is not None and recorder.poll() is not None:raise RuntimeError('Recorder exited while workload was running')
                for name in ['workload.stdout','workload.stderr']:
                    if (self.path/name).stat().st_size>10*1024*1024:
                        self.meta['log_truncated']=True;raise RuntimeError('Workload exceeded 10 MiB log limit')
                for name in ['workload.stdout','workload.stderr']:
                    path=self.path/name
                    with path.open('r',errors='replace') as f:
                        f.seek(self.output_offsets.get(name,0));chunk=f.read(32768);self.output_offsets[name]=f.tell()
                    if chunk:self.log(name,chunk)
                parsed=socket_samples(self.ns(self.s,'ss','-tin').stdout)
                observed_data_flows.update(r['flow_id'] for r in parsed if (r['bytes_acked'] or 0)>4096)
                flow=select_data_flow(parsed,locked)
                queue=queue_sample(json.loads(self.ns(self.r,'tc','-j','-s','qdisc','show','dev','r1').stdout))
                now=time.monotonic()
                sample={'cursor':sample_count+1,'t_s':now-start,'flow_id':None,'cwnd_segments':None,'srtt_ms':None,
                        'bytes_acked':None,'acked_rate_bps':None,'retransmits':None,'controller':None,'socket_ambiguous':len(parsed)>1,**queue}
                if flow:
                    if locked is None and (flow['bytes_acked'] or 0)>4096:locked=flow['flow_id']
                    if locked:
                        sample.update({k:flow.get(k) for k in ['flow_id','cwnd_segments','srtt_ms','bytes_acked','retransmits','controller']})
                        observed.add(flow['controller'])
                        if previous and previous['flow_id']==flow['flow_id'] and previous['bytes_acked'] is not None and flow['bytes_acked'] is not None:
                            delta=flow['bytes_acked']-previous['bytes_acked']
                            if delta>=0:sample['acked_rate_bps']=delta*8/(now-previous['at'])
                        previous={**flow,'at':now}
                self.samples.append(sample);sample_count+=1
                with (self.path/'samples.jsonl').open('a') as f:f.write(json.dumps(sample)+'\n')
                self.meta['samples_count']=sample_count;self.persist()
                time.sleep(.25)
            self.meta['stopped_early']=self.stop_event.is_set()
            if work.poll() is None:self.phase('stopping','stopping workload gracefully');self.terminate(work,signal.SIGINT)
            self.meta['workload_exit_code']=work.poll()
            if not self.stop_event.is_set() and work.returncode!=0:raise RuntimeError(f'Workload failed (exit {work.returncode}): '+(self.path/'workload.stderr').read_text(errors='replace')[-3000:])
            self.phase('finalizing','flushing recorder and receiver artifacts')
            self.terminate(recorder)
            try:receiver.wait(timeout=3)
            except subprocess.TimeoutExpired:self.terminate(receiver)
            for stream in self.streams:stream.flush()
            final_summary={}
            try:
                payload=json.loads((self.path/('workload.stdout' if self.workload['kind']=='iperf3' else 'receiver.stdout')).read_text())
                final_summary=receiver_summary(payload) if self.workload['kind']=='iperf3' else {k:payload.get(k) for k in ['receiver_throughput_bps','receiver_bytes','receiver_duration_s']}
                if self.stop_event.is_set():final_summary['receiver_throughput_bps']=None
                atomic_json(self.path/'receiver.json',payload)
            except (ValueError,KeyError):final_summary={'receiver_throughput_bps':None,'receiver_bytes':None}
            self.meta['observed_controllers']=sorted(c for c in observed if c)
            self.meta['summary']=final_summary
            valid_flows={x['flow_id'] for x in self.samples if x['flow_id']}
            if self.config.capture:
                self.phase('validating','validating finalized recording and model self-replay')
                from ccreplay.recordings import inspect
                integrity=inspect(self.path/'trace.ccr',self.path/'trace.meta.json')
                if not integrity['replayable']:raise RuntimeError('Recorder produced no replayable callbacks')
                if observed!={cca} or len(valid_flows)!=1 or len(observed_data_flows)!=1:raise RuntimeError('Observed data flow/controller does not match supported capture scope')
                from user.replay_r1 import run_r1_on_trace
                from user.replay_r2 import run_r2_on_trace
                if self.config.controller=='reno':
                    a=run_r1_on_trace(str(self.path/'trace.ccr'),str(self.path/'trace.meta.json'))
                    b=run_r2_on_trace(str(self.path/'trace.ccr'),str(self.path/'trace.meta.json'))
                    model={'verdict':'PASS' if a['mismatch_count']==0 and b['first_divergence'] is None else 'FAIL',
                           'event_local':a,'stateful':b}
                else:
                    from user.replay_r3a import run_r3a_on_trace
                    from user.replay_r3b import run_r3b_on_trace
                    if self.config.controller=='cubic':
                        a=run_r3a_on_trace(str(self.path/'trace.ccr'),str(self.path/'trace.meta.json'));b=run_r3b_on_trace(str(self.path/'trace.ccr'),str(self.path/'trace.meta.json'))
                    else:
                        from user.replay_e2 import run_e2_on_trace
                        from user.replay_e3 import run_e3_on_trace
                        a=run_e2_on_trace(str(self.path/'trace.ccr'),str(self.path/'trace.meta.json'));b=run_e3_on_trace(str(self.path/'trace.ccr'),str(self.path/'trace.meta.json'))
                    if self.config.controller=='cubic':
                        divergence=b.get('first_divergence')
                        verdict='FAIL' if a.get('clock_stable_mismatched',0)>0 or (divergence and divergence.get('clock')!='CLOCK_AMBIGUOUS') else 'PARTIAL' if a.get('mismatch_count',0)>0 or divergence else 'PASS'
                        model={'verdict':verdict,'historical_verdict':'PARTIAL','event_local':a,'stateful':b}
                    else:
                        model={'verdict':'PASS' if a.get('mismatch_count')==0 and b.get('first_divergence') is None else 'FAIL',
                               'reference_strength':'No independent kernel-native reference','event_local':a,'stateful':b}
                self.meta['recording']={**integrity,'self_replay':model,'termination':'stopped' if self.stop_event.is_set() else 'normal'}
            else:self.meta['recording']=None
            self.meta.update(status='completed',phase='ready',finished_at=utc())
        except BaseException as exc:
            self.meta.update(status='cancelled' if isinstance(exc,InterruptedError) else 'failed',phase='finalizing partial evidence',error=f'{type(exc).__name__}: {exc}',finished_at=utc())
            self.log('error',self.meta['error'])
        finally:
            for p in reversed(self.processes):self.terminate(p)
            for stream in self.streams:stream.close()
            failures=cleanup_struct_ops(self.meta['resources'].get('struct_ops',[]))
            for name in reversed(self.namespaces):
                try:self.command(['ip','netns','delete',name])
                except Exception as exc:failures.append(str(exc))
            self.meta['cleanup']={'completed':not failures,'errors':failures,'owned_namespaces':self.namespaces.copy()}
            self.meta['resources']['active']=False
            # Keep partial evidence explicitly; never register it as a green replay result.
            if self.config.capture and not self.meta.get('recording'):
                self.meta['recording']={'integrity':'partial','replayable':False,'reason':self.meta.get('error','Not finalized')}
            for file in self.path.iterdir():
                if file.is_file() and file.name != 'manifest.json':
                    self.meta['artifacts'][file.name]={'bytes':file.stat().st_size,'sha256':digest(file)}
            self.persist()
            for base,dirs,files in os.walk(self.path):
                os.chown(base,self.uid,self.gid)
                for f in files:os.chown(Path(base)/f,self.uid,self.gid)
