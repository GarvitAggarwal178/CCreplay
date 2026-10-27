"""Fixed single-connection receiver; not owner-supplied executable code."""
import json
import signal
import socket
import time

count=0;started=None;stopped=False

def stop(*_):
    global stopped
    stopped=True

signal.signal(signal.SIGTERM,stop)
s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('10.77.2.2',5201));s.listen(1);s.settimeout(.5)
connection=None
try:
    while not stopped:
        try:connection,_=s.accept();break
        except socket.timeout:continue
    if connection:
        connection.settimeout(.5);started=time.monotonic()
        while not stopped:
            try:
                chunk=connection.recv(65536)
                if not chunk:break
                count+=len(chunk)
            except socket.timeout:continue
finally:
    elapsed=time.monotonic()-started if started else None
    print(json.dumps({'receiver_bytes':count,'receiver_duration_s':elapsed,'receiver_throughput_bps':count*8/elapsed if elapsed else None,'finalized':not stopped}),flush=True)
    if connection:connection.close()
    s.close()
