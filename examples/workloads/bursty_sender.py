"""One TCP flow; edit send/pause intervals, then save a new revision."""
from traffic_api import connect, send_for, pause, emit

sock = connect()
try:
    emit('phase', 'send for 5 seconds')
    send_for(sock, 5)
    emit('phase', 'pause for 2 seconds')
    pause(2)
    emit('phase', 'send for 10 seconds')
    send_for(sock, 10)
finally:
    sock.close()
