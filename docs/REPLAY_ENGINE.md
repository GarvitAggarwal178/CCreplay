# Replay Engine

## Purpose

Re-execute congestion-control implementations against a recorded Replay Contract.

The replay engine does not emulate Linux TCP as a whole.

## Controller model requirements

A controller model must expose explicit deterministic state.

Conceptually:

```text
implementation identity
private-state schema
init private state
execute event-local transition
execute stateful transition
snapshot/restore private state
comparison schema per callback
```

The concrete API is an implementation detail. The semantics are not.

## Determinism

A replay controller must not depend on:

- wall-clock reads;
- hidden globals;
- unstated process state.

Controller-visible time comes from the replay event.

## Mode A — Event-local transition replay

For each event:

1. load recorded shared TCP PRE state;
2. load recorded private PRE state;
3. supply callback inputs;
4. supply recorded observations/time;
5. execute one controller transition;
6. compare callback result;
7. compare declared controller-owned POST state;
8. compare declared private POST state.

No private replay state carries to the next event.

## Mode B — Stateful controller replay

Controller-private state is initialized once.

For each event:

1. inject recorded shared TCP boundary state;
2. supply callback inputs/observations/time;
3. execute with current replay-private state;
4. compare declared callback result;
5. compare declared controller-owned state;
6. compare replay-private semantic state where the oracle declares it;
7. carry private replay state forward.

The next callback's shared TCP state again comes from the recording.

## Self-replay

For a matching implementation:

- Mode A should match every event under its oracle.
- Mode B should report no first divergence.

## Cross-implementation replay

Two implementations consume the same recorded shared boundary/event input. In Mode B they maintain separate private state.

The resulting comparison is about controller logic under a fixed replay contract, not a real alternate network execution.

## Comparison schema

Every controller/callback pair declares exact compared fields.

Examples:

- Reno `ssthresh`: scalar return;
- Reno `undo_cwnd`: scalar return;
- Reno `cong_avoid`: `snd_cwnd`, `snd_cwnd_cnt`, plus any explicitly controller-owned fields;
- CUBIC: additional parsed private-state fields as needed.

Gate reports must print the comparison schema used.

## Checkpoints

Stateful replay checkpoints serialize controller-private state.

Requirements:

- exact `restore(snapshot())` round-trip;
- deterministic encoding;
- version/schema ID;
- no hidden state outside the checkpoint.

A checkpoint represents replay-controller state, not a network snapshot.

## Repeatability

Running the same controller model against the same trace twice must produce identical replay output.

This is an automated precondition for correctness-gate PASS.
