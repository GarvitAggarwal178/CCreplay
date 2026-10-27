"""Agent-only helper: enter namespace first, then permanently drop all IDs.

The root agent never imports or evaluates the workload source.
"""
import argparse
import json
import os
import sys
import socket

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--uid',type=int,required=True);p.add_argument('--gid',type=int,required=True);p.add_argument('script');args=p.parse_args()
    if args.uid<=0 or args.gid<=0:raise SystemExit('A non-root uid and gid are required')
    cca=os.environ.get('CCR_CONTROLLER')
    if cca not in ('reno','cubic','ccr_reno','ccr_cubic','ccr_covegas'):
        raise SystemExit('Unsupported configured socket controller')
    # BPF struct_ops CCAs are restricted even inside a new network namespace.
    # Configure one unconnected socket before dropping privileges, without
    # changing the host's allowed/default CCA lists. Only the descriptor survives.
    connection=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_CONGESTION,cca.encode())
    connection.set_inheritable(True)
    os.environ['CCR_SOCKET_FD']=str(connection.fileno())
    os.setgroups([]);os.setresgid(args.gid,args.gid,args.gid);os.setresuid(args.uid,args.uid,args.uid)
    if os.getuid()==0:raise SystemExit('Privilege drop failed')
    print(json.dumps({'workload_start':True,'uid':os.getuid(),'gid':os.getgid()}),flush=True)
    os.execve(sys.executable,[sys.executable,'-u',args.script],dict(os.environ))
