# CCReplay — Project Statement

## Project title

**CCReplay: Deterministic Differential Replay for TCP Congestion Control**

## Problem

Congestion-control regressions are usually discovered at the level of outcomes: throughput changed, RTT changed, cwnd became unstable, or a controller mode became stuck. Those outcomes may be produced by thousands of congestion-control callbacks.

Traditional traces can show that behavior changed, but they do not directly answer:

> **At which congestion-control transition did the candidate implementation first stop behaving like the reference implementation?**

CCReplay addresses that question.

## Contribution

> **CCReplay defines and validates a versioned replay contract for Linux congestion-control callbacks, records real executions at that boundary, and differentially replays controller implementations to localize the exact transition where they first diverge.**

## Primary user

A developer implementing, modifying, refactoring, or debugging a TCP congestion-control algorithm.

## Primary use case

Regression localization between reference and candidate versions of the same controller, including controlled injected bugs and genuine historical buggy/fixed versions.

## Why this is a networking project

The artifact operates at the real Linux TCP congestion-control interface. The hard systems questions are networking-specific:

- what callback-visible TCP state is required for faithful replay;
- how TCP-core-owned state differs from controller-private state;
- how controller-visible clocks affect algorithms such as CUBIC;
- how to instrument a real CC implementation without silently changing semantics;
- how to validate replay against a live Linux execution.

## Why this is more than observability

Observability says:

> “At time T, cwnd was 52.”

CCReplay aims to say:

> “Reference and candidate agreed through event 18,420. At event 18,421, callback `ssthresh`, the reference returned 43 and the candidate returned 31.”

That is an executable regression-debugging primitive.

## Core artifacts

1. **Replay Contract / Replay ABI** — versioned, callback-aware, and explicit about shared TCP state, private state, callback inputs, and callback results.
2. **Kernel/BPF recorder** — wrapper controller, exact logical ordering, loss detection, PRE/result/POST capture.
3. **Userspace replay engine** — event-local transition replay and stateful controller replay.
4. **Correctness oracles** — Reno exact semantic self-replay, then CUBIC fidelity.
5. **Differential debugger** — first divergence, state/result diff, context, and checkpoint-based suffix reproducer.
6. **Case studies** — one controlled bug and one real historical regression.

## Non-goals

CCReplay is not a new CCA, controller selector, active control plane, CC performance predictor, network simulator, whole-TCP deterministic replay system, or arbitrary event-minimization framework.

## Success criteria

- R0 recorder viability passes.
- R1 Reno event-local exact semantic self-replay passes.
- R2 Reno stateful-controller exact semantic self-replay passes.
- R3 CUBIC demonstrates private-history/time-dependent replay.
- A controlled injected bug is localized correctly.
- A real historical regression is localized to a meaningful callback/result/state difference.
- Recorder overhead is practically negligible under precommitted equivalence margins.
- Replay ABI ablation identifies load-bearing field classes per supported algorithm.

## Professor-level pitch

> We built a debugger for TCP congestion-control code. A BPF wrapper records the real Linux congestion-control callback boundary, including the shared TCP state the controller sees, its callback inputs, private state where needed, and its return value or state mutation. Our replay engine re-runs controller implementations against that exact contract. If a new version changes behavior, CCReplay reports the first callback where it differs from the reference and exactly which result or state field changed. We validate the mechanism by requiring exact semantic self-replay and demonstrate it on both a controlled bug and a real historical controller regression.

## Claim boundary

> **CCReplay answers what a congestion-control implementation computes at a recorded callback boundary. It does not claim what network trajectory or performance that implementation would have produced.**
