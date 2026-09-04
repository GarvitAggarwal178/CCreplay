# CCReplay — Repository Guide

**Read this before doing anything in this repository.**

## Mission

CCReplay is a **regression debugger for TCP congestion-control implementations**.

It records the congestion-control callback boundary of a live Linux TCP connection under an explicit, versioned Replay Contract, then re-executes controller implementations against that recording to localize the exact controller transition where two implementations first diverge.

CCReplay is a callback-boundary recorder, deterministic controller replay engine, and differential debugger. It is **not** a network simulator, controller selector, active control plane, whole-TCP replay system, or counterfactual performance predictor.

## Binding semantic rule

> **CCReplay answers what a congestion-control implementation computes at a recorded Linux congestion-control callback boundary. It does not claim what network trajectory or performance that implementation would have produced.**

If a plot, report sentence, CLI label, or evaluation claim contradicts that sentence, it does not ship.

## Allowed claims

CCReplay may claim that:

1. A trace contains an ordered sequence of recorded CC callback invocations.
2. Each event supplies the shared TCP boundary state, callback inputs, controller-visible observations/time, controller-private state where required, and callback result defined by the Replay Contract.
3. A supported controller implementation can be re-executed against that contract.
4. Self-replay can be validated by exact semantic equality under a declared oracle.
5. Two implementations replayed against the same recorded contract can be compared to identify the first callback at which their declared results or state transitions differ.
6. Replay-ABI ablation can identify which recorded field classes are load-bearing for faithful replay of a supported implementation.

## Forbidden claims

CCReplay must never claim:

- what throughput another CCA would have achieved;
- what RTT another CCA would have achieved;
- what queue state another CCA would have created;
- that replaying a CUBIC-generated trace through Vegas reconstructs a real Vegas connection;
- that cross-implementation replay is an alternate network execution;
- that ACK, RTT, and loss alone are a sufficient replay input;
- that the project replays the Linux TCP core as a whole;
- that arbitrary deletion of TCP control events is valid trace minimization.

## Fundamental replay boundary

CCReplay replays the **congestion-control implementation**, not the entire TCP stack.

At each callback boundary distinguish four classes:

### 1. Recorded shared TCP input state

State owned or evolved by Linux TCP outside or around the CC implementation. It is injected from the trace at every replayed callback.

Examples include callback-visible values such as `snd_cwnd`, `snd_ssthresh`, `snd_cwnd_cnt`, congestion state, in-flight state, cwnd-limited status, RTT/delivery observations, recovery-facing state, and controller-visible time.

### 2. Controller-private state

Algorithm-specific state whose evolution belongs to the controller implementation. In stateful replay this is initialized once and evolves across events.

### 3. Callback inputs

Arguments passed to the callback.

### 4. Callback result / controller-owned mutation

Return values and declared controller-owned mutations produced by the controller.

## Replay modes

### Mode A — Event-local transition replay

Every event is evaluated independently from recorded shared PRE state and recorded private PRE state.

Purpose: validate one transition, discover missing Replay ABI inputs, and localize regressions without accumulated private-state drift.

### Mode B — Stateful controller replay

Controller-private replay state is initialized once and evolves across events. At every event boundary the shared TCP state is injected from the recording.

Mode B does **not** simulate Linux TCP-core evolution between callbacks.

## Documentation authority

The files under `docs/` are the project specification. If implementation reality forces a semantic change, stop, document it, update the specification and an ADR, then change implementation.

## Gate discipline

Every gate has a written PASS/FAIL condition in `docs/GATES.md`.

- Never weaken a correctness assertion to make a gate pass.
- Never silently discard a mismatch or event loss.
- Preserve failed traces and logs.
- If the Replay Contract changes, bump its version and re-record affected traces.
- Broaden research claims only after updating `docs/PRIOR_ART.md`.

A correct FAIL is preferable to a false PASS.

## Read-only source repositories

Treat these as read-only:

- `~/cn-spike`
- `~/covegas`
- `~/cn`

Anything reused must be copied into CCReplay and documented in `docs/PROVENANCE.md`.

## Known environment/harness hazards

Inherited target environment: WSL2 Ubuntu, kernel `6.18.33.2-microsoft-standard-WSL2`.

1. Avoid `$`-prefixed shell references in external tool command strings where the harness may strip them; place shell logic in scripts.
2. Do not run `pkill -f iperf3` directly in a fragile command string.
3. Use `MSYS_NO_PATHCONV=1` when required for WSL Linux paths from Windows/Git-Bash contexts.
4. Use scripts for long/complex commands.
5. `ss` may match control/data/stale sockets; reuse validated disambiguation logic if needed.
6. Disable veth offloads for the validated emulation harness.
7. Audit BTF directly; `vmlinux.h` may omit callable function prototypes.
8. Use only the validated Gate 3-R2 topology for network experiments.

## Freeze rule

Once R0 implementation begins, do not reopen broad project ideation unless a documented project-level kill condition fires.
