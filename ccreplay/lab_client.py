"""Normal-user local agent bridge; no sudo or shell endpoint."""
import json
import os
from pathlib import Path
import socket
from ccreplay.lab_protocol import MAX_MESSAGE,Message


def socket_path():
    return os.environ.get('CCREPLAY_LAB_SOCKET',f'/tmp/ccreplay-lab-{os.getuid()}/agent.sock')


def call(operation,**kwargs):
    msg=Message(operation=operation,**kwargs)
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        client.settimeout(15)
        try:client.connect(socket_path())
        except OSError as exc:raise ConnectionError(f'Lab agent unavailable. In a second terminal run: sudo bash scripts/start_lab_agent.sh ({exc})') from exc
        client.sendall(msg.model_dump_json().encode()+b'\n')
        with client.makefile('rb') as stream:data=stream.readline(MAX_MESSAGE+1)
    if len(data)>MAX_MESSAGE:raise ValueError('Agent response too large')
    value=json.loads(data)
    if not value['ok']:raise ValueError(value['error'])
    return value['result']
