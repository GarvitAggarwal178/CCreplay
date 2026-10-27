"""Supported single-flow TCP workload helpers (trusted local code)."""
import json
import os
import socket
import time


def emit(name,value):
    print(json.dumps({'annotation':str(name),'value':value,'monotonic_ns':str(time.monotonic_ns()),'uid':os.getuid()}),flush=True)


def connect():
    inherited=os.environ.pop('CCR_SOCKET_FD',None)
    sock=socket.socket(fileno=int(inherited)) if inherited else socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    sock.settimeout(2)
    selected=os.environ['CCR_CONTROLLER']
    if not inherited:
        sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_CONGESTION,selected.encode())
    elif sock.getsockopt(socket.IPPROTO_TCP,socket.TCP_CONGESTION,64).rstrip(b'\0').decode()!=selected:
        raise RuntimeError('Preconfigured data socket controller mismatch')
    sock.connect((os.environ['CCR_RECEIVER'],int(os.environ['CCR_PORT'])))
    emit('connected',{'controller':sock.getsockopt(socket.IPPROTO_TCP,socket.TCP_CONGESTION,64).rstrip(b'\0').decode()})
    return sock


def send_for(sock,seconds,chunk_bytes=16384):
    if not 0<=seconds<=180 or not 1<=chunk_bytes<=1048576:
        raise ValueError('Unsupported send interval/chunk size')
    end=time.monotonic()+seconds;data=b'x'*chunk_bytes
    while time.monotonic()<end:
        sock.sendall(data)


def pause(seconds):
    if not 0<=seconds<=180:raise ValueError('Invalid pause duration')
    time.sleep(seconds)
