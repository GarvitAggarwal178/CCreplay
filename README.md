# CCReplay

## Deterministic Differential Replay for TCP Congestion Control

CCReplay is a regression debugger for congestion-control implementations.

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
