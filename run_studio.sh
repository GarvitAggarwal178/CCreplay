#!/usr/bin/env bash
# One command: build the frontend if needed, start the backend, print the URL.
# Binds 127.0.0.1 only; never run with sudo.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

PORT=8000
DAEMON=0
STOP=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port=*) PORT="${1#--port=}"; shift ;;
    --port) PORT="$2"; shift 2 ;;
    --daemon) DAEMON=1; shift ;;
    --stop) STOP=1; shift ;;
    *) shift ;;
  esac
done

# Port-specific, not a single shared ".autorun/server.pid" -- a shared
# pidfile meant `--stop` (or any script that calls it, e.g.
# studio_measure_load.py) always killed whichever daemon happened to be
# running on ANY port, not the one just started/being targeted.
PIDFILE=".autorun/server-$PORT.pid"

if [[ "$STOP" == "1" ]]; then
  if [[ -f "$PIDFILE" ]]; then
    PID="$(cat "$PIDFILE")"
    if kill -0 "$PID" 2>/dev/null; then
      kill "$PID"
      echo "stopped server pid $PID"
    else
      echo "pid $PID not running"
    fi
    rm -f "$PIDFILE"
  else
    echo "no pidfile at $PIDFILE"
  fi
  exit 0
fi

if [[ ! -d frontend/node_modules ]]; then
  echo "frontend/node_modules missing -- run 'npm ci' in frontend/ first" >&2
else
  if [[ ! -d frontend/dist ]]; then
    echo "building frontend..."
    (cd frontend && npm run build)
  fi
fi

mkdir -p .autorun

if [[ "$DAEMON" == "1" ]]; then
  setsid nohup .venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port "$PORT" \
    > ".autorun/server-$PORT.log" 2>&1 &
  echo $! > "$PIDFILE"
  echo "started daemon pid $(cat "$PIDFILE") on http://127.0.0.1:$PORT"
else
  echo "CCReplay Studio: http://127.0.0.1:$PORT"
  exec .venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port "$PORT"
fi
