# Semantics

This document is binding.

## Core object

CCReplay replays a **congestion-control implementation transition** at a recorded Linux callback boundary. It does not replay the complete TCP connection.

## Replay Contract

A replay event has four semantic classes.

### 1. Recorded shared TCP input state

State supplied by Linux TCP at the callback boundary. It is injected from the recording at every replayed event.

### 2. Controller-private state

State owned by the CC implementation, including algorithm-specific estimators, epochs, modes, and counters.

### 3. Callback inputs and controller-visible observations

Callback identity, arguments, RTT/delivery observations where read, recovery-facing inputs, and controller-visible time.

### 4. Callback result and controller-owned mutation

Return values and declared controller-owned state transitions.

## Mode A — Event-local transition replay

For each event independently:

```text
recorded shared PRE
+
recorded private PRE
+
callback inputs
+
observations/time
        |
        v
controller transition
        |
        v
computed callback result
+
computed controller-owned POST
+
computed private POST
```

No replay state carries to the next event.

### Meaning

> Given exactly the recorded boundary state and inputs for this callback, does this implementation compute the expected controller transition?

## Mode B — Stateful controller replay

Controller-private replay state is initialized once.

At each event:

- recorded shared TCP boundary state is injected from the trace;
- current replay-private state is supplied;
- the callback executes;
- replay-private state evolves.

### Meaning

> Given this recorded sequence of Linux TCP boundary states and callback inputs, how does this implementation's private control state evolve, and where does its declared controller output first differ?

### Mode B is not

- full TCP replay;
- alternate network execution;
- simulation of TCP-core updates;
- prediction of alternate performance.

## Self-replay

Self-replay is replaying a trace through an implementation intended to match the implementation that generated it.

The oracle is **exact semantic equality under the declared Replay Contract and comparison schema**.

Do not use “bit-exact” unless literal byte-level identity is actually defined.

## Cross-implementation replay

Cross-implementation replay applies two implementations to the same recorded contract. It is a software comparison, not a counterfactual network execution.

## First divergence

The first divergence is the smallest event sequence number for which two implementations, under the same mode and oracle, produce different declared callback results or semantic controller state.

It is a logic result, not automatically a causal explanation for later throughput or RTT differences.

## Exact semantic equality

Each controller declares a semantic comparison schema. Candidate exact fields include callback results, `snd_cwnd`, `snd_ssthresh`, `snd_cwnd_cnt`, and parsed algorithm-private fields.

Raw `icsk_ca_priv` bytes may be archived, but padding or unused bytes must not fail the correctness gate.

## Required sentence

> **CCReplay answers what a congestion-control implementation computes at a recorded callback boundary. It does not claim what network trajectory or performance that implementation would have produced.**
