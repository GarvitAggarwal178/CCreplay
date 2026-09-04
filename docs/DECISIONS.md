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

## ADR-013 — Three independent counters, not just gapless sequence, for drop integrity

**Status:** accepted (capability audit / pre-R0).

A gapless, monotonic `seq` proves no *interior* record was dropped, but cannot detect loss
truncated off the *tail* of a run (userspace stops polling before teardown; the last N events
were reserved+submitted but never drained, or never reserved at all after the last observed
`seq`). `RECORDER.md`'s authoritative BPF-side drop counter is necessary but, alone, does not
close this either, since it only counts reservation failures, not a total-invocation count to
check emitted+drops against.

**Decision:** the recorder maintains three atomic counters (`invocations`, `emitted`, `drops`),
all read directly from the map at teardown, before the struct_ops program is unregistered. A
trace is integrity-valid only if `invocations == emitted + drops` **and** `seq` is gapless — the
two checks catch different failure classes (interior loss vs. tail truncation) and neither
substitutes for the other.

## ADR-014 — Reno wrapper has no `.init` and no controller-private state

**Status:** accepted (capability audit / pre-R0).

Upstream `tcp_reno_ops` implements no `.init`. The capability audit's empirical field-mutation
pass (100% exact replay match on 24,651 real `cong_avoid` events using only already-classified
shared-TCP-state fields) confirmed Reno reads/writes nothing outside `SharedTcpPreState`/
`ControllerOwnedPostState` — it has no algorithm-private history, epoch, or mode state. Per
`RECORDER.md`'s "do not invent private state merely because the generic schema supports it," the
wrapper declares no `.init` and does not allocate `SK_STORAGE` for Reno, even though `SK_STORAGE`
was separately validated as available (capability audit section B) for a future controller that
does need it.

## ADR-015 — `is_cwnd_limited`/`max_packets_out` added as required (not optional) `cong_avoid` inputs

**Status:** accepted (capability audit / pre-R0, before first trace recorded).

`docs/REPLAY_ABI.md`'s original example field list for `cong_avoid` (`snd_cwnd`, `snd_cwnd_cnt`)
did not mention the gating condition `tcp_is_cwnd_limited()`. The capability audit's Mode-A dry
run against real captured traffic found two events with identical `snd_cwnd`/`snd_ssthresh`/
`acked` but opposite outcomes (one grew, one didn't), explained exactly by differing
`is_cwnd_limited`/`max_packets_out` values. Without these fields, event-local replay would apply
growth the real kernel did not. Added to Replay ABI v0's required `cong_avoid` input set before
any trace was recorded under this contract, so no `trace_version` bump or re-recording was
triggered — this is the contract-discovery process `GATES.md`/`IMPLEMENTATION_HANDOFF.md`
anticipate, completed at the cheapest possible point (pre-recording, via a disposable audit
capture) rather than after an R1 mismatch.

## ADR-016 — Dominant-connection selection for multi-socket recordings

**Status:** accepted (capability audit / pre-R0).

Registering `ccr_reno` as a named congestion controller makes it available to *any* socket that
requests it by name for the lifetime of the recording, not only the one connection under test.
Empirically, two independent loopback smoke tests (the `SK_STORAGE` audit and the real recorder's
own end-to-end test) both showed a second, short-lived socket contributing exactly one stray event
alongside the ~99.999%-share main transfer socket — plausibly `iperf3` applying `-C` to its control
channel as well as its data channel, though this was not chased to a certain root cause (see
`data/capability_audit.md` section B).

`docs/SEMANTICS.md`'s core object is a **connection's** callback boundary, not a recording
window's. **Decision:** every `EventRecord` carries a `sock_cookie` (session-scoped socket-pointer
discriminator — `bpf_get_socket_cookie()` is unavailable from this program type on this kernel, so
the raw `sk` pointer value is used instead, see `docs/REPLAY_ABI.md`). The parser
(`user/ccr_trace.py`) selects the socket with the most events as the trace's dominant connection
and reports any other sockets' events as diagnostic, not as part of the replayed sequence. A trace
is rejected if the dominant connection accounts for less than 99% of events (an actual mixed-load
recording, not an incidental stray-socket artifact) rather than silently pooling two connections'
histories under one sequence.
