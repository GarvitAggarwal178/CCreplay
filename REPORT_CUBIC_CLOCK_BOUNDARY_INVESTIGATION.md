# CUBIC Clock-Boundary Investigation (Part C)

## Status: COMPLETE — verdict `ATTRIBUTED_AND_CHARACTERIZED`

Per `docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md` Part C, as expanded by its Required Addendum
(items 1–4). **This does NOT upgrade R3 to PASS** — see the final section.

## Question

> Is there a practical, non-semantic-changing way on this kernel to observe the exact
> controller-visible time value used inside the CUBIC reference invocation? And, short of that, how
> fully can the observed `CLOCK_AMBIGUOUS` residual be characterized from existing evidence?

## 1. Ambiguity-rate arithmetic (addendum item 1)

```text
ambiguity_probability = 46 / 236,088 = 1.948426e-04
estimated_observation_window ≈ 1.948426e-04 × 4 ms ≈ 0.7794 µs ≈ 779 ns
```

At `HZ=250` (ground-truthed, `data/cubic_replay_capability_audit.md`), one jiffy is 4 ms. The
observed clock-ambiguity rate of 46/236,088 corresponds to an effective observation window of
approximately 780 ns if callback placement relative to the jiffy boundary is approximately uniform.

This is a **quantitative consistency check, not a direct timing measurement**: it is consistent in
scale with a sub-microsecond recorder/reference observation boundary and supports, but does not by
itself prove, the clock-boundary explanation. It is not claimed to be directly-measured callback
execution time, and it is not equated with N0's unrelated (Reno, loopback, different measurement
question) recorder-overhead figures.

## 2. Two-sided clock attribution diagnostic (addendum item 2)

Script: `data/audit_src/clock_boundary_attribution.py`. Output:
`data/cubic_clock_boundary_attribution.json`.

For every `CLOCK_AMBIGUOUS` event across the three primary traces that currently mismatches under
the production `clock_jiffies32_before` convention (4 events total — confirmed to be exactly R3A's
4 reported `CLOCK_AMBIGUOUS` mismatches, cross-checked), a diagnostic-only replay of that event in
isolation was run twice: once substituting `clock_jiffies32_before` (== production, included for
table completeness) and once substituting `clock_jiffies32_after`. Neither substitution touched
`user/cubic_model.py`, the production Replay Contract, or the selected clock convention.

| trace | seq | callback | clock_before | clock_after | classification |
| --- | ---: | --- | ---: | ---: | --- |
| rep1 | 51323 | `cong_avoid` | 16612603 | 16612604 | `MATCHES_AFTER_ONLY` |
| rep1 | 57117 | `cong_avoid` | 16614269 | 16614270 | `MATCHES_AFTER_ONLY` |
| rep2 | 75603 | `cong_avoid` | 16643546 | 16643547 | `MATCHES_AFTER_ONLY` |
| rep3 | 61729 | `cong_avoid` | 16663506 | 16663507 | `MATCHES_AFTER_ONLY` |

**Counts:** `MATCHES_BEFORE_ONLY=0`, `MATCHES_AFTER_ONLY=4`, `MATCHES_BOTH=0`, `MATCHES_NEITHER=0`.

**Every residual clock-ambiguous mismatch is fully attributable to one of the two clock values
bracketing the reference invocation** (all four are `MATCHES_AFTER_ONLY`). No additional semantic
mismatch was observed in these events. This closes the attribution question under the current
bracketing evidence. **It does not mean exact replay can select the correct clock prospectively** —
see §5 (a global "always use `_after`" convention does not generalize; see
`data/cubic_replay_model_changes.md` Investigation 2, which found switching the production
convention to `_after` resolves these 4 events but introduces 2 *new* mismatches on different,
previously-exact events).

## 3. Stateful resynchronization diagnostic (addendum item 3)

Script: `data/audit_src/clock_stateful_resync_diagnostic.py`. Output:
`data/cubic_clock_stateful_resync_diagnostic.json`.

Diagnostic-only Mode-B variant: at every divergence, replay-private state is replaced with that
event's own recorded semantic private POST state (shared TCP state was already re-injected from the
recording at every event, unchanged) and replay continues from the next event. The production
`user/replay_r3b.py`/`user/cubic_model.py` are not modified.

| trace | divergences | all `CLOCK_AMBIGUOUS`? | unexplained `CLOCK_STABLE` divergence? | exact events between divergences |
| --- | ---: | --- | --- | --- |
| rep1 | 2 (seq=51323, seq=57117) | yes | none | 51,322 before the first; 5,793 between the two; 21,571 after the second (to end of trace) |
| rep2 | 1 (seq=75603) | yes | none | 75,602 before; 3,165 after (to end of trace) |
| rep3 | 1 (seq=61729) | yes | none | 61,728 before; 16,903 after (to end of trace) |

**Strong diagnostic result:** replay is exact between every pair of ambiguous divergences (and from
each resync point to the end of its trace) after resynchronization, in every trace. **Stateful
divergence is localized to isolated clock-ambiguous invocations; replay does not exhibit
unexplained accumulating drift between those boundaries.** Zero `CLOCK_STABLE` divergences occurred
anywhere in any trace, before or after any resync — the "STOP, additional state-propagation
problem" condition was not triggered.

## 4. Bounded instrumentation feasibility check (original Part C, ≤1h cap)

Checked in a few minutes, not the full hour, once the architecture made the answer clear:

* `bictcp_update` — the helper that performs the actual `tcp_jiffies32` reads inside
  `cubictcp_cong_avoid` — **does not appear in `/proc/kallsyms`**: the compiler has inlined it into
  `cubictcp_cong_avoid` (consistent with it being a small `static` function at `-O2`). There is no
  independent symbol to attach a kprobe/fentry/fexit probe to at that granularity.
* `cubictcp_cong_avoid` itself **is** ftrace-able (confirmed present in
  `/sys/kernel/debug/tracing/available_filter_functions`), but an fentry/fexit probe at its own
  entry/exit boundary would observe timing at essentially the same granularity the recorder's
  existing before/after `tcp_jiffies32` bracket already provides — the internal reads happen at
  multiple scattered points inside the now-inlined body, not at the function's own boundary, so
  this offers no improvement.
* Line-level instrumentation at the exact internal read sites would require either post-inlining
  debug-info-dependent kprobe offsets (fragile, non-portable, effectively a private per-build patch)
  or actual source modification of `tcp_cubic.c` — the latter explicitly forbidden by this task
  ("do NOT rewrite CUBIC merely to expose its clock").

**Outcome: NOT CLOSED.** No practical, non-semantic-changing instrumentation strategy was found on
this kernel within the available tooling.

## 5. Clock investigation verdict

**`ATTRIBUTED_AND_CHARACTERIZED`**

Requirements (per the addendum) and their evidence:

* every residual ambiguous mismatch matches at least one bracketing clock value — **met** (§2: 4/4
  `MATCHES_AFTER_ONLY`, 0 `MATCHES_NEITHER`);
* stateful replay is exact between ambiguous events after diagnostic resynchronization — **met**
  (§3, all three traces);
* no unexplained `CLOCK_STABLE` divergence exists — **met** (§3, zero in any trace).

**Meaning:** the remaining replay discrepancy is fully accounted for by uncertainty about which
controller-clock value the reference observed inside the current recorder/reference observation
window — not by a missing Replay Contract input, a model transcription error, a recorder bug, or
unexplained state drift. Exact semantic replay is established for clock-stable callback
invocations. Invocations in which the controller-visible clock changes within the recorder/reference
observation window are explicitly marked clock-ambiguous and remain outside the exact stateful
replay guarantee under the current instrumentation.

**This still does NOT upgrade R3 to PASS.** `REPORT_CUBIC_REPLAY_VALIDATION.md`'s Gate verdict
(`PARTIAL`) is unchanged by this investigation — R3's governing gate definition requires R3B's
literal "first divergence = NONE" on all valid primary traces, which is not met regardless of how
fully the residual is characterized. This limitation must not block the CoVegas case study unless
CoVegas shares the same clock dependency — to be determined empirically in Part D/E, not assumed.

## Reproduction

```
python3 data/audit_src/clock_boundary_attribution.py
python3 data/audit_src/clock_stateful_resync_diagnostic.py
```

## Relevant commit

This report's own commit (adds both diagnostic scripts, their JSON outputs, and this file).

Mandatory Phase-1 regression: reverified clean before this commit.
