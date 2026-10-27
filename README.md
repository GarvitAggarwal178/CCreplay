# CCReplay Studio

Run real Linux TCP experiments, capture congestion-control callbacks and inspect exactly where two compatible controller revisions compute different results.

**Live Network Lab** measures actual Linux sockets over owned namespaces/veth with NetEm, HTB and a FIFO queue. **Replay** computes controller decisions on fixed recorded inputs; it does not predict an alternate connection's throughput, RTT or queue trajectory.

The application uses the existing Python replay engine, FastAPI/SQLite and React/Vite. Four complete genuine recording families remain immediately usable offline. The interface contains Start, Network Lab, Replay, Controllers, Recordings, Runs and Advanced tools.

## Start from a normal-user checkout

Prerequisites: Python 3.12+ (verified here with 3.14.4), Node/npm compatible with `frontend/package-lock.json`, and the Python packages in `requirements-studio.txt`. Existing dependencies are already installed on this host. For a fresh checkout:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-studio.txt
(cd frontend && npm ci && npm run build)
```

Start Studio **without sudo**:

```sh
./run_studio.sh
# http://127.0.0.1:8000
```

For native networking/capture, in a second terminal from the original checkout:

```sh
sudo bash scripts/start_lab_agent.sh
```

The agent uses a private owner-only Unix socket. It creates and cleans only its own resources. The API, controller interpreter and custom traffic source run without root privileges. User Python is trusted local code, not a hostile-code sandbox.

## This root-only WSL session

This checkout lives under `/root` and no ordinary login account is configured. A prepared accessible copy is at `/var/tmp/ccreplay-studio`, owned by the existing non-root uid/gid 65534. No login account was created. From the current root terminal:

```sh
cd /var/tmp/ccreplay-studio
setpriv --reuid=65534 --regid=65534 --clear-groups .venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

In a second root terminal:

```sh
cd /root/ccreplay
CCREPLAY_OWNER_UID=65534 CCREPLAY_OWNER_GID=65534 bash scripts/start_lab_agent.sh
```

After source changes, refresh the prepared copy with:

```sh
cd /root/ccreplay
.venv/bin/python scripts/prepare_unprivileged_workspace.py --uid 65534 --gid 65534 --dest /var/tmp/ccreplay-studio
```

**Canonical source is `/root/ccreplay`.** Edit and build there. The prepared copy is runtime only: new controller revisions live in `/var/tmp/ccreplay-studio/controllers/user/`, jobs/parameters in its `studio_data/`, and replay sessions, workloads and imported recordings in its `runtime/`. Agent capture artifacts live under `/tmp/ccreplay-lab-65534/session-*`. Refreshing preserves these owner files; do not edit the prepared source as a second authority.

The helper copies known source and the existing environment, preserves destination saved runs, and leaves original owner data untouched. Run it while Studio is stopped. A changed replay dependency makes an old rerun refuse rather than silently substitute current code. A normal login user's home checkout is the preferred everyday setup; the numeric-uid route is the verified option for this existing root-only host.

## Use the workbench

- Start → investigate a controller change. Compare CUBIC with itself, then “Loss threshold +1.” Open the actual first difference and step through matched neighbors.
- Controllers → **Compare two independent algorithms** opens `/#/algorithm-workbench`: import/edit two trusted Python policies using event-local or initialized stateful execution, supply synthetic or captured v0 callback inputs, and inspect computed decisions. Sources, compared inputs and initialization are saved with hashes; differences are neutral policy comparisons.
- Controllers → edit a parameter or Python source → save a new immutable revision → compare it. Editing again never changes the earlier saved result.
- Network Lab → start a native run; watch measured ACKed-data rate, cwnd, RTT and queue samples. Enable callback recording to qualify/run Recorded Reno, then open **that new recording** in Replay.
- Save a traffic script in Network Lab to generate real single-flow TCP traffic. It is different from a replay controller script.
- Runs → reopen results without execution, export identities and compare two separate native executions. Advanced retains parameter sweeps and all-decision statistics.

See [demo](docs/DEMO.md), [development/setup/checks](docs/DEVELOPMENT.md), [architecture](docs/ARCHITECTURE.md), [contract](docs/REPLAY_CONTRACT.md), [validation/limits](docs/VALIDATION.md), and [provenance/archive restoration](docs/PROVENANCE.md).

## Final review workflow

Use Start → Network Lab → Runs & Compare for two separately executed native Reno/CUBIC runs. Capture must be off for native performance comparison. From a completed run, “Run the other algorithm with these settings” creates a draft; it never starts a second run automatically. Runs & Compare presents configured-condition checks before receiver goodput/retransmissions and all cursor-paged cwnd, RTT, ACKed-rate and queue samples.

Use Recordings → Controllers → Replay for same-ABI revision investigation. Replay shows callback disagreement breadth, numeric magnitudes and computed timelines; first difference is a drill-down. Saved configuration and source hashes remain immutable. Advanced contains historical evidence, sweeps and the independent v0 policy sandbox.

Start as a normal user with `bash run_studio.sh`; optionally start the owner-authorized network agent separately using `sudo bash scripts/start_lab_agent.sh`. Verify with `(cd frontend && npm run build && npm run lint)`, `.venv/bin/python -m pytest -q`, `.venv/bin/python scripts/studio_smoke.py`, `PATH="$PWD/.venv/bin:$PATH" bash scripts/demo/demo_00_run_all.sh`, and `.venv/bin/python scripts/studio_e2e.py http://127.0.0.1:8000`. Browser checks never initiate privileged live runs.
