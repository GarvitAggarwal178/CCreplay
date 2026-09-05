# Limitations

These limitations are part of the design and should be stated before evaluation.

## 1. Cross-implementation replay is not an alternate network trajectory

The trace was produced by the live reference controller. A different controller would have altered future observations.

CCReplay compares controller logic under a fixed recorded contract; it does not predict alternate throughput, RTT, or queue state.

## 2. CCReplay replays the controller boundary, not Linux TCP as a whole

Linux TCP may mutate shared state between callbacks. Mode B therefore injects recorded shared boundary state at every event.

## 3. Initial recording requires a wrapper/reference implementation

The initial design does not assume a passive independent `struct_ops` observer beside native CUBIC.

This constrains initial recordability to callable/validated reference implementations.

## 4. Replay Contracts are implementation-specific

Reno, CUBIC, Vegas, BBR, and CoVegas may require different state schemas.

There is no universal-minimality claim.

## 5. Exactness is semantic, not raw-byte equality

Correctness compares declared semantic callback results/state. Raw private bytes may contain padding or unused data.

## 6. Trace completeness is load-bearing

Dropped replay-critical events invalidate fidelity claims. CCReplay detects loss; it does not reconstruct lost events.

## 7. Controller-visible time may be load-bearing

Algorithms such as CUBIC may depend on a specific kernel timebase. High-resolution diagnostic timestamps are not automatically substitutes.

## 8. Callback coverage is controller-specific

A trace promises only the callback surface declared by its capability manifest.

## 9. No arbitrary event minimization

The base reproducer is checkpoint + suffix.

## 10. First divergence is a software result

It does not by itself prove the cause of a later performance outcome.

## 11. Initial evaluation is testbed-specific

Do not claim production-Internet portability or overhead without evidence.

## 12. Kernel portability is not guaranteed

BTF, kfunc availability, verifier behavior, and instrumentation capabilities can vary by kernel.

## 13. Reno R2 did not exercise non-trivial private-state propagation

Reno R2 did not independently validate non-trivial private-state propagation because Reno has no
private controller state under ABI v0 (ADR-014). Mode B's private-state thread-through was proven
to work mechanically (the sentinel is carried unchanged across all 112,051 sequential transitions,
`tests/test_reno_model.py::TestPrivateStateThreading`), but no controller exercised in Phase 1 ever
had a private field actually change value between events.

**Closed by R3B (CUBIC):** all 16 semantic private fields (ADR-019) were confirmed to change value
across the replayed sequence on all three primary traces (`fields_that_never_changed_in_any_trace`
is empty), carried through 51,323–75,603 consecutive sequential transitions per trace without ever
being resynchronized from the recording, with exact semantic equality until the clock-ambiguity
residual (item 14). See `REPORT_GATE_R3_CUBIC.md`.

## 14. Controller-visible clock ambiguity is not always resolvable from a before/after snapshot pair

CUBIC (unlike Reno) depends on a global, non-per-socket clock (`tcp_jiffies32`) that the recorder
cannot inject at replay time — only snapshot immediately before and after the real kfunc call
(ADR-018). When the snapshot pair differs (`CLOCK_AMBIGUOUS`, ~0.02% of primary-trace events), the
exact value the real kernel's internal computation actually read is not always recoverable: a
diagnostic substitution (`data/cubic_replay_model_changes.md` Investigation 2) found that neither
"always use the before value" nor "always use the after value" resolves every `CLOCK_AMBIGUOUS`
event — different individual events are each consistent with a different single-read timing, with
no universal rule. This is a characterized clock-boundary limitation under the current recorder
architecture for any CC implementation that reads a global (non-per-socket) clock, not a recorder
or model defect, and is not "fixed" by picking a different snapshot convention — see
`REPORT_CUBIC_REPLAY_VALIDATION.md`'s R3 verdict for how this was scored, and
`REPORT_CUBIC_CLOCK_BOUNDARY_INVESTIGATION.md` for the full quantitative-consistency, two-sided
attribution, and stateful-resynchronization characterization (verdict
`ATTRIBUTED_AND_CHARACTERIZED` — which does not upgrade R3 to PASS).
