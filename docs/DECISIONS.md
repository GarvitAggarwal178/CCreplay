# Architecture Decision Records

## ADR-001 — NetFork deprioritized

**Status:** accepted.

Gate 0 showed ordinary throughput comparisons were highly reproducible, while the weak queue-delay axis was driven by tiny policy separation. The later phasecheck weakened the “same waveform with multi-second phase drift” interpretation.

**Decision:** do not build NetFork as the semester artifact.

## ADR-002 — Live ShadowCC rejected as centerpiece

**Status:** accepted.

Passive in-kernel shadow execution provides weaker debugging ergonomics than userspace replay while imposing verifier/state constraints.

The kernel retains the task only it can perform faithfully: capture the live CC callback boundary.

## ADR-003 — Record/replay architecture adopted

**Status:** accepted.

```text
kernel callback recorder -> versioned trace -> userspace replay -> differential debugger
```

## ADR-004 — Replay controller boundary, not full TCP

**Status:** accepted.

Linux TCP may mutate shared state between callbacks. Mode B therefore injects recorded shared boundary state at every callback while controller-private replay state evolves.

## ADR-005 — Callback results are first-class

**Status:** accepted.

Return values such as `ssthresh()` are controller decisions and may be applied by TCP after callback return. They must be recorded explicitly.

## ADR-006 — Exact semantic replay terminology

**Status:** accepted.

Correctness means exact equality on declared semantic callback results/state fields, not blanket raw-byte equality.

## ADR-007 — Wrapper recorder initially

**Status:** accepted.

Do not assume an independent `struct_ops` observer can coexist with native CCA ownership. Initial recorder is the active wrapper/reference CC.

## ADR-008 — Callback capability manifest

**Status:** accepted.

Different CCAs implement different callback subsets. Each trace declares the surface it promises to record.

## ADR-009 — Sequence allocation before recording success

**Status:** accepted.

A failed ring-buffer reservation must not erase a callback from logical history. Sequence is allocated at callback entry; authoritative drops live outside the ring buffer.

## ADR-010 — `SK_STORAGE` preferred, not assumed

**Status:** proposed pending R0.

Use if available from the selected context; otherwise use a documented fallback.

## ADR-011 — Mode A and Mode B retained

**Status:** accepted.

Mode A independently validates transitions. Mode B validates private-state evolution while injecting recorded shared TCP state at every event. Neither claims alternate network execution.

## ADR-012 — Arbitrary event minimization excluded

**Status:** accepted.

Base reproducer is checkpoint + suffix. Dependency-aware reduction is optional stretch work.
