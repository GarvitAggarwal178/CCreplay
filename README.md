# CCReplay

## Deterministic Differential Replay for TCP Congestion Control

CCReplay is a regression debugger for congestion-control implementations.

For the authoritative current project status and latest formal verdicts, see
`docs/CURRENT_STATE.md`.

A live Linux TCP connection is recorded at the congestion-control callback boundary. The trace contains the callback identity, relevant shared TCP boundary state, callback inputs, controller-private state where required, controller-visible time, and explicit callback results. A userspace engine then re-executes controller implementations against that recording.

Instead of only showing that two versions produce different throughput or cwnd curves, CCReplay is designed to report:

```text
events 1..18,420  MATCH

FIRST DIVERGENCE
event:       18,421
callback:    ssthresh

reference result: 43
candidate result: 31
```

## Architecture

```text
LIVE TCP CONNECTION
        |
        v
CC callback boundary
        |
        v
BPF wrapper / recorder
        |
        v
versioned CCReplay trace
        |
        +-------------------+
        |                   |
        v                   v
reference replay      candidate replay
        |                   |
        +---------+---------+
                  |
                  v
       differential debugger
                  |
          first divergence
```

The kernel records the boundary that only the kernel can observe faithfully. Userspace performs replay and debugging because it offers repeatability, arbitrary state inspection, checkpoints, and fewer verifier constraints.

## Important semantic boundary

CCReplay replays a congestion-control implementation at its recorded Linux callback boundary. It does **not** replay the entire Linux TCP stack.

Shared TCP state is injected from the trace at each callback. Controller-private state may evolve across callbacks in stateful replay.

## What CCReplay does not predict

Cross-implementation replay does not reconstruct an alternate network history. CCReplay does not claim alternate throughput, RTT, queue behavior, or that another CCA would have followed the replayed trajectory on a real connection.

## Primary validation

The central correctness requirement is:

> **exact semantic self-replay under the declared Replay Contract and comparison oracle.**

Reno is the first correctness target. CUBIC is the genericity gate because it introduces private historical state and controller-visible time.

Start with `docs/PROJECT.md`, `docs/SEMANTICS.md`, `docs/REPLAY_ABI.md`, and `docs/GATES.md`.

## Run CCReplay Studio

CCReplay Studio is a local web app over the engine above: browse recorded traces, build a
controller variant (parameters or Python code), diff it against a reference on real recorded
inputs, see the first divergence, reproduce it from a checkpoint, and export the result. It does
not change any replay semantics, model, or verdict above -- it only wraps `user/*.py` for
interactive use (see ADR-025).

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements-studio.txt
cd frontend && npm ci && npm run build && cd ..
./run_studio.sh
# http://127.0.0.1:8000
```

The backend binds `127.0.0.1` only and never runs as root. Controller code written in the editor
runs locally in a child process with a timeout -- that bounds a slow/crashing run, it is not a
security sandbox; the editor shows a one-time notice that it runs Python on your machine.

Smoke-check the engine wrappers without a browser: `.venv/bin/python scripts/studio_smoke.py`.
End-to-end browser check (Playwright/Chromium, drives the real running app): `./run_studio.sh
--port 8765 --daemon && .venv/bin/python scripts/studio_e2e.py http://127.0.0.1:8765`.
