# CCReplay — Current State (Authoritative Handoff)

**This document answers: what is CCReplay's status right now?** It is the single place a future
session, a teammate, or the final report should read first to avoid using a superseded claim or a
stale gate verdict.

**Authority rule:** this document is authoritative for *current status*. It is not authoritative
for raw measurements, exact commands, per-experiment methodology, or detailed failure history —
the individual `REPORT_*.md` files and `data/*.md` files remain authoritative for that. Where this
document and an older report disagree on a verdict, later evidence supersedes earlier status, but
the earlier report is not rewritten — it is historical evidence of what was known at that time.
Language such as *"Originally UNVALIDATED in the primary R3 traces; subsequently VALIDATED using
the targeted auxiliary trace"* is used deliberately throughout this document to preserve that
distinction. This document does not rewrite or hide historical failures.

---

## 1. What CCReplay is

CCReplay is a regression debugger for TCP congestion-control implementations: it records the
congestion-control callback boundary of a live Linux TCP connection under an explicit, versioned
Replay Contract, then re-executes controller implementations against that recording to localize
the exact controller transition at which two implementations first diverge.

## 2. What CCReplay is NOT

- Not a network simulator — it does not synthesize alternate network trajectories.
- Not a counterfactual performance predictor — it never claims what throughput, RTT, or queue
  state a different controller would have produced.
- Not a whole-TCP replay system — it replays the congestion-control implementation boundary, not
  Linux TCP as a whole; shared TCP state is injected from the recording at every callback.
- Not an active control plane or controller selector.
- Not a claim that cross-implementation replay reconstructs a real alternate connection (e.g.
  replaying a CUBIC-generated trace through Vegas does not reconstruct a real Vegas connection).

> **Binding semantic rule:** CCReplay answers what a congestion-control implementation computes at
> a recorded Linux congestion-control callback boundary. It does not claim what network trajectory
> or performance that implementation would have produced.

## 3. Current architecture

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

The kernel records the boundary only the kernel can observe faithfully (`bpf/*_wrapper.bpf.c`,
one per supported controller). Userspace (`user/*.py`) performs replay, comparison, checkpointing,
and differential debugging. Full 8-step recorder pseudocode and the Mode A/Mode B replay shapes are
in `docs/ARCHITECTURE.md`; this diagram is the current, unchanged top-level pipeline.

## 4. Replay ABI versions

| ABI | Controller | Key feature |
| --- | --- | --- |
| v0 | Reno | stateless (no controller-private state); 3-callback manifest |
| v1 | CUBIC | private history + controller-visible time; 7-callback manifest |
| v2 | CoVegas | mode-dependent union private state + two independent clock brackets; 5-callback manifest |

Full field-by-field schemas are in `docs/REPLAY_ABI.md` ("v0/v1/v2 concrete instantiation" sections
and ADR-017 through ADR-024 in `docs/DECISIONS.md`) — not duplicated here. Per-version summary:

**v0 — Reno**
- Callback manifest: `{ssthresh, cong_avoid, undo_cwnd}`, no `.init`.
- Controller-private state: NONE (Reno has no algorithm-private state, ADR-014).
- Clock dependencies: none (Reno's math has zero time dependency).
- Live-reference strength: real target-kernel `tcp_reno_*` kfuncs — Oracle C, independent kernel
  reference, the strongest reference strategy used anywhere in this project.
- Formal replay verdict: **PASS** (R0/R1/R2, see §5).

**v1 — CUBIC**
- Callback manifest: `{init, ssthresh, cong_avoid, set_state, cwnd_event, pkts_acked, undo_cwnd}`.
- Controller-private state: 16 semantic `struct bictcp` fields (ADR-019); `unused` deliberately
  excluded (dead field).
- Clock dependencies: two controller-visible clocks — `tcp_jiffies32` (global, non-per-socket,
  bracketed before/after) and `tp->tcp_mstamp` (per-socket, cached, single PRE snapshot).
- Live-reference strength: real target-kernel CUBIC kfuncs for recording (Oracle C); userspace
  replay model built from the real kernel source (`data/kernel_source_ref/tcp_cubic.c`), not the
  read-only `bpf_cubic.c` port.
- Formal replay verdict: **PARTIAL** (R3, see §5 — do not upgrade to PASS).

**v2 — CoVegas**
- Callback manifest: `{init, cong_avoid, ssthresh, undo_cwnd, pkts_acked}` (no `set_state`/`cwnd_event`).
- Controller-private state: 17 dedicated fields + a mode-dependent `union` (6 `delay`-arm / 7
  `cubic`-arm fields, genuinely memory-aliased across mode transitions) = 30 semantic fields total;
  comparison schema is `f(callback, controller_mode, replay_phase)` (ADR-023), not a flat schema.
- Clock dependencies: two independent clock brackets — `tcp_jiffies32` (global) and
  `bpf_ktime_get_ns()` (computed fresh by the controller itself each invocation, ADR-024) — both
  independently `CLOCK_STABLE`/`CLOCK_AMBIGUOUS` classified.
- Live-reference strength: **no kernel-native form exists** (ADR-022) — the recorder instruments a
  copy of the read-only BPF source directly; there is no independent kernel reference. This is the
  weakest reference strategy of the three versions, and is stated as such everywhere CoVegas
  results are reported.
- Formal replay verdict: **PASS**, unqualified (E1–E3, see §5).

## 5. Formal evidence ledger

| Component / gate | Formal verdict | Current evidence | Remaining caveat |
| --- | --- | --- | --- |
| Reno R0 (recorder viability) | **PASS** | 112,051 events (37,260+37,391+37,400), 0 drops, 0 sequence gaps, all 3 traces | none |
| Reno R1 (event-local self-replay) | **PASS** | 112,051 events checked, 224,120 field comparisons, 0 mismatches | none |
| Reno R2 (stateful self-replay) | **PASS** | 112,051 events replayed sequentially, first divergence = NONE | Reno has no controller-private state (ADR-014); R2 did not exercise *non-trivial* private-state propagation — that question is closed for CUBIC by R3B, not by R2 itself |
| CUBIC R3 (event-local + stateful self-replay) | **PARTIAL — do not upgrade to PASS** | R3A: 236,088 events checked, 4,485,714 field comparisons; 236,042 `CLOCK_STABLE` events, 0 mismatches; 46 `CLOCK_AMBIGUOUS` events, 4 mismatches. R3B: first divergence in every trace lands on a `CLOCK_AMBIGUOUS` `cong_avoid` event (rep1 at 51,323/78,688; rep2 at 75,603/78,768; rep3 at 61,729/78,632) — all sequential transitions before that point are exact. All 16 semantic private fields changed value nontrivially in every trace. `undo_cwnd`: originally 0 events / UNVALIDATED in the primary traces; **subsequently VALIDATED** using a targeted auxiliary trace (12 `undo_cwnd` invocations, 0 mismatches, first divergence = NONE across the full 75,415-event auxiliary sequence) — this does not change the R3 verdict. | R3's literal PASS criterion (R3B first divergence = NONE on all primary traces) is not met; the residual is fully attributed and characterized (§7, clock verdict `ATTRIBUTED_AND_CHARACTERIZED`) but not resolved |
| CUBIC clock-boundary characterization | `ATTRIBUTED_AND_CHARACTERIZED` | See §7 for the full arithmetic, two-sided attribution, and stateful-resync evidence | Does not upgrade R3 to PASS; not closed by any available non-invasive instrumentation on this kernel (bounded feasibility check: NOT CLOSED) |
| Differential debugger (N4) | **COMPLETE / PASS** | Hard-negative sanity oracle: Reno (37,260 events) and CUBIC (78,688 events), both NO DIVERGENCE against themselves | Only proves the tool doesn't report a false divergence; N5 proves it reports a true one |
| Controlled seeded regression (N5) | **PASS** | 4 seeded bugs: 3 positive controls (2 exact, 1 partial-magnitude miss, correctly localized to callback/field in all 3) + 1 required dormant negative control (exact NO DIVERGENCE, 78,688/78,768/78,632 events, no false positive) | Predictions committed (`4d2972e`) before bug code existed; the one partial miss is disclosed, not rounded up |
| Checkpoint + suffix reproducer (N6) | **COMPLETE** | Bug 1 demo: checkpoint@event 1500, divergence@event 1704, 204-event suffix replayed in full, reproduced the identical divergence | Reproducer, not minimizer — no event in the suffix is skipped or deleted, by design |
| CoVegas Replay Fidelity (E1–E3) | **PASS**, unqualified | E2 (event-local): 190,277 events, 4,982,990 field comparisons, 0 mismatches, all 3 primary traces. E3 (stateful): first divergence = NONE across all 3 traces (190,277 sequential transitions total, 3 separate all-exact runs). All 30 semantic private fields (17 dedicated + both union arms) changed value nontrivially; both mode-transition directions exercised. Neither clock (`tcp_jiffies32`, `bpf_ktime_get_ns()`) produced a single mismatch — the CUBIC clock exception was proven, not assumed, not to transfer to this trace set. `undo_cwnd`: 0 events in primary traces — Outcome A (function semantics independently supported via the shared `tcp_reno_undo_cwnd` kernel helper; the CoVegas ABI-v2 recorder/model path itself was not exercised) — this is not the CUBIC auxiliary trace's result and does not itself constitute CoVegas-trace evidence. | Reference-strength caveat: CoVegas has no independent kernel-native reference (ADR-022); this PASS validates CCReplay's replay fidelity for the selected BPF implementation, not the independent correctness of the CoVegas algorithm itself. `undo_cwnd` coverage is function-level only (Outcome A), not trace-level — does not affect this PASS or the historical case study's readiness (the historical mechanism runs through `cong_avoid`, fully exercised). |
| Historical CoVegas regression case study | **INCOMPLETE — TRIGGER NOT REPRODUCED** | 3 bounded intermittent-workload capture attempts (rep1/rep2/rep3), 18 real recorded mode transitions total, 0 occurred during an off-period. The buggy-vs-fixed differential replay was intentionally NOT run because the required trigger was absent. | This is not: a CCReplay fidelity failure; a debugger failure; a disproven historical regression. It is a trigger-availability blocker. |

## 6. Important Replay Contract discoveries

Contract discovery — finding that the originally assumed field/callback set was insufficient, and
folding the fix in before or without invalidating already-recorded evidence — occurred for every
supported controller:

**Reno**
- `is_cwnd_limited`/`max_packets_out` were not in the original example field list but were found
  required, pre-recording, from two otherwise-identical real events with opposite `cong_avoid`
  outcomes (ADR-015).
- `bpf_get_socket_cookie()` is unavailable from this program type on this kernel (verifier
  rejection); the raw `sk` pointer is used as a within-trace socket discriminator instead (ADR-016).

**CUBIC**
- The real kernel source diverges from the read-only `bpf_cubic.c` port in three load-bearing ways
  (time-math rounding order, HyStart round-reset trigger relocation, a real `sk_gso_max_size` field
  read vs. a hardcoded constant) — discovered only after fetching the actual kernel source
  (ADR-017), reversing this session's own precommitted prediction about `snd_una`.
- CUBIC depends on two independent controller-visible clocks, not one — `tcp_jiffies32` (global,
  cannot be injected, only bracketed) and `tp->tcp_mstamp` (per-socket, cached) — discovered before
  any recorder code was written (ADR-018).
- `pkts_acked`'s HyStart path writes `tp->snd_ssthresh` directly, a controller-owned mutation from
  a nominally `void` callback that has nothing to do with ssthresh — required an explicit
  `post_snd_ssthresh` field or the mutation would be invisible to comparison (ADR-020).
- `struct bictcp` has 17 declared members, not the originally-assumed 15/16 — ground-truthed via
  compiled `offsetof`/`sizeof`, one field (`unused`) confirmed dead and excluded from the oracle
  (ADR-019).

**CoVegas**
- No kernel-native reference exists at all — the recorder must instrument a copy of the BPF
  implementation directly, with no separable "reference vs. instrumentation" split (ADR-022).
- The private-state `union` genuinely aliases memory across a mode transition (confirmed directly
  from the source's own comment) — a raw-byte comparison across a mode transition would report a
  spurious "mutation" that is really just reinterpretation, requiring a mode-dependent comparison
  schema keyed independently by PRE mode and POST mode (ADR-023).
- The second clock (`bpf_ktime_get_ns()`) is computed fresh by the controller itself once per
  invocation — architecturally different from CUBIC's cached `tp->tcp_mstamp` — requiring its own
  independent before/after bracket rather than inheriting CUBIC's single-snapshot treatment
  (ADR-024).

**Replay Contract discovery is a measured result of the project, not merely schema bookkeeping.**

## 7. Clock-boundary finding

CUBIC's only unresolved replay residual is confined to events where the recorder's before/after
snapshot of the global `tcp_jiffies32` clock disagrees (`CLOCK_AMBIGUOUS`) — 46 of 236,088 primary
events (≈0.02%), producing 4 mismatches out of 4,485,714 field comparisons.

**Ambiguity-rate arithmetic** (a quantitative consistency estimate, not a direct timing
measurement):

```text
46 / 236088 ≈ 1.95e-4
1 jiffy = 4 ms
1.95e-4 × 4 ms ≈ 0.78 µs ≈ 780 ns
```

This is consistent in scale with a sub-microsecond recorder/reference observation boundary; it
supports, but does not by itself prove, the clock-boundary explanation.

**Two-sided attribution — two scopes, not to be conflated:**

- *Table 2a (the four production-convention mismatches):* all 4 are `MATCHES_AFTER_ONLY` (0
  `MATCHES_BEFORE_ONLY`, 0 `MATCHES_BOTH`, 0 `MATCHES_NEITHER`).
- *Table 2b (all 46 `CLOCK_AMBIGUOUS` events, recomputed on reconciliation):* `MATCHES_BEFORE_ONLY
  = 2`, `MATCHES_AFTER_ONLY = 4`, `MATCHES_BOTH = 40`, `MATCHES_NEITHER = 0`. The 40 `MATCHES_BOTH`
  events are ones whose compared fields happen not to depend on the one-jiffy delta for that event
  — not additional evidence of a "correct" clock, only insensitivity to the shift.

Every one of the 46 is semantically compatible with at least one bracketing value — the recorded
transition is not claimed to prove the reference "necessarily saw" that value, only that no event
requires an unexplained semantic difference outside the recorded bracket. This does not mean a
global "always use `_after`" convention resolves the ambiguity: substituting it resolves the 4
production mismatches but introduces 2 *new* mismatches on previously-exact events.

**Stateful resynchronization diagnostic:** resynchronizing replay-private state from the recorded
POST state at each divergence shows replay is exact between every pair of ambiguous divergences,
and from each resync point to the end of its trace, in every trace. Zero unexplained
`CLOCK_STABLE` divergences occurred anywhere.

**Bounded instrumentation search:** `bictcp_update` is compiler-inlined (no independent symbol to
probe); a function-boundary probe on `cubictcp_cong_avoid` offers no finer granularity than the
existing before/after bracket; line-level instrumentation would require fragile per-build kprobe
offsets or forbidden source modification. **NOT CLOSED** — no practical, non-semantic-changing
instrumentation strategy was found on this kernel.

**Verdict: `ATTRIBUTED_AND_CHARACTERIZED`.** The remaining discrepancy is fully accounted for by
uncertainty about which controller-clock value the reference observed inside the current
recorder/reference observation window — not a missing contract input, transcription error,
recorder bug, or unexplained state drift. **The original R3 remains PARTIAL because its literal
first-divergence-none condition was not met.**

CoVegas was checked separately and empirically found *not* to share this exception on its own
traces — neither of its two clocks produced a single mismatch (§5).

## 8. Recorder-overhead status

**Ring-buffer notification/wakeup handling was the dominant measured contributor** under the N0
high-rate loopback diagnostic — not `bpf_ktime_get_ns()`, not the reference-kfunc/`BPF_CORE_READ`
work itself, and not `bpf_stats` instrumentation.

Measured means (3 reps each unless noted): `baseline_production` ≈ **7,933 ns**/callback;
`nowakeup_variant` (busy-polled, `BPF_RB_NO_WAKEUP`) ≈ **232 ns**/callback — a **~34×** reduction,
reproducible with non-overlapping distributions across all reps. `noktime_variant` (2 reps) showed
no detectable reduction relative to baseline.

This finding must **not** be read as any of the following, all of which this session explicitly
did not establish:
- that production recorder cost universally is 232 ns/callback (loopback-only diagnostic, not
  adopted into the production recorder this session);
- that ring-buffer wakeups are proven dominant on every topology (only measured under the N0
  high-rate loopback condition — the Gate-3-R2 netns topology was not re-measured at this
  granularity);
- that formal recorder non-interference (whether the recorder detectably perturbs the connection
  it instruments) has passed — that is a distinct, separate evaluation that has not been run.

## 9. Current limitations

- Cross-implementation replay is not an alternate network trajectory; CCReplay never claims
  alternate throughput, RTT, or queue-state outcomes.
- CCReplay replays the controller boundary, not Linux TCP as a whole; shared TCP state is always
  injected from the recording, never simulated forward.
- Exactness is semantic equality on the declared comparison schema, not raw-byte or "bit-exact"
  equality; padding/unused private-state bytes are excluded from the oracle.
- CUBIC's clock-boundary ambiguity affects ≈0.02% of primary events; it is characterized (§7) but
  not resolved, and R3 remains PARTIAL as a direct consequence.
- The historical CoVegas trigger is a rare (~11%/run), probabilistic network condition; 3 bounded
  attempts produced 0 occurrences (an expected outcome, not an anomaly), so the historical
  buggy-vs-fixed differential replay has not been run.
- CoVegas self-replay (E2/E3 PASS) validates CCReplay's fidelity to the selected BPF
  implementation, not the independent correctness of the CoVegas algorithm — no kernel-native
  CoVegas reference exists.
- N0's recorder-overhead figures are a loopback diagnostic characterizing a dominant cost
  contributor, not a production-topology performance claim or a formal non-interference result.
- No arbitrary event minimization exists; the base reproducer is checkpoint + full suffix replay,
  by design.
- Replay ABI ablation (identifying which recorded field classes are load-bearing) has not yet been
  run for any controller.

## 10. Historical CoVegas case-study state

- **Fixed build:** v4 — the actual, currently committed `~/cn-spike/covegas/src/covegas.bpf.c`
  source. This is the only version of that file ever committed to the read-only repository.
- **Buggy build:** a reconstruction — v4's real source with exactly one conditional in
  `handle_compete_mode` (the A3 settle-latch guard, `if (ca->dlv_rate_bps < (ca->dlv_rate_max * 3)
  / 4) { latch } else { revert }`) reverted to an unconditional latch, matching v3's documented
  behavior. **v3's actual source was never committed to the read-only repo** — the reconstruction
  is built from two independent, mutually-consistent documentary sources (`REPORT_COVEGAS_V3.md`
  Part C's mechanism diagnosis and v4's own change-log comment describing what it added), not a
  diffable historical commit. This is disclosed as a reconstruction, not presented as literal v3
  source.
- **Trigger definition:** a spurious `DELAY→COMPETE` mode transition during an off-period (no real
  competitor present) — the condition A3's guard is designed to catch, and the condition that,
  absent A3, permanently locks CoVegas into COMPETE mode.
- **Historical evidence:** **3 `HOLD_MS=500` runs, 9 off-period boundaries** (3 boundaries/run —
  the default, and the only configuration this session's recorder builds), **1 observed spurious
  re-entry** (`REPORT_COVEGAS_V4.md`'s own B2 prediction-check table: "1 (of 9 boundaries)"). Not
  "1 of 9 runs" — that phrasing appeared in earlier CCReplay documentation and is corrected here.
  0 of 9 boundaries at `HOLD_MS=0` and 0 of 9 boundaries at `HOLD_MS=2000` (3 runs each). The full
  three-setting sweep (9 runs, 27 boundaries) shows 1 spurious re-entry pooled across all 27 — that
  pooled 1/27 figure must not be substituted for the `HOLD_MS=500`-specific 1/9 rate.
- **Current attempts:** 3 bounded runs on the historically-relevant intermittent-workload topology;
  trigger absent in all 3 (**3 runs, 9 off-period boundaries, 0 observed trigger events**). Using
  the selected configuration's own descriptive rate (1/9 per boundary) as a rough binomial
  sensitivity calculation under an independence assumption — not an estimated trigger distribution
  — `P(0 in 9) = (8/9)^9 ≈ 34.6%`, still among the single most likely outcomes at this sample size,
  not an anomaly. (An earlier draft of this figure used `(8/9)^3 ≈ 70%`, treating the historical
  denominator as 3 runs instead of 9 boundaries — corrected here.)
- The buggy CoVegas model module was designed but not implemented, since there was no
  trigger-positive trace to run it against.
- `data/historical_regression_predictions.md` remains committed and unresolved by design — no
  RESULTS section was appended, since no diff was ever run.

**Do not describe the case study as failed.** Nothing about CCReplay, the CoVegas Replay Contract,
or the recorder failed; self-replay fidelity was fully demonstrated (PASS, §5) before this blocker
was even reached. The blocker is specifically about reproducing a rare, historically-documented-as-
rare network condition on demand within a bounded number of attempts.

## 11. Current open work — prioritized

- **Priority A — Decide historical case-study strategy.** A project-level decision (more bounded
  attempts vs. a longer/multi-rep capture campaign vs. accepting INCOMPLETE as the final state for
  this case study) is required. **This decision is not executed in this task.**
- **Priority B — Replay ABI ablation.** Mask one recorded field class at a time and rerun
  self-replay to identify load-bearing fields, per `docs/REPLAY_ABI.md`'s ablation section. Not yet
  started for any controller.
- **Priority C — Formal recorder non-interference.** A dedicated study of whether the recorder
  detectably perturbs the connection it instruments under the validated Gate-3-R2 topology,
  distinct from N0's isolated CPU-cost diagnostic.
- **Priority D — Professor demo.** Packaging the differential-debugger / checkpoint-reproducer
  results (N4–N6) into a presentable demonstration.
- **Priority E — Prior-art review.** Broadening related-work claims in `docs/PRIOR_ART.md`.

## 12. Things future agents MUST NOT do

1. Do not upgrade CUBIC R3 to PASS. Its literal PASS criterion (R3B first divergence = NONE on all
   primary traces) is not met, regardless of how fully the clock residual is characterized.
2. Do not downgrade CoVegas self-replay (E1–E3, PASS) because the historical trigger was absent —
   these are unrelated results; fidelity was proven before the trigger blocker was reached.
3. Do not call the historical regression case study FAIL. It is INCOMPLETE, blocked on trigger
   availability, not a disproven regression or a CCReplay defect.
4. Do not describe CUBIC's clock limitation as "irreducible" — it is a characterized clock-boundary
   limitation under the current recorder architecture, and the bounded instrumentation search was
   NOT CLOSED, not exhaustively proven impossible.
5. Do not say "byte-exact" or "bit-exact" anywhere — the oracle is exact semantic equality on the
   declared comparison schema.
6. Do not treat `undo_cwnd` as UNVALIDATED for CUBIC — it was subsequently VALIDATED via the
   targeted auxiliary trace (§5); this does not change the R3 verdict.
7. Do not run the historical CoVegas buggy-vs-fixed differential replay against a trace where the
   trigger is confirmed absent and report "no divergence" as if it tested the regression.
8. Do not attempt a fourth (or further) bounded historical-trigger capture without a new,
   explicit, project-level decision (Priority A) authorizing it.
9. Do not manufacture the historical trigger by adjusting tunables (e.g. `HOLD_MS`) away from the
   historically-relevant configuration — that tests a different, unvalidated scenario.
10. Do not modify `~/cn-spike`, `~/cn`, or `~/cn-spike/covegas` — all are read-only source
    repositories; anything reused must be copied into CCReplay and documented in
    `docs/PROVENANCE.md`.
11. Do not present the N0 recorder-overhead figures as a production-topology or
    formal-non-interference result — they are a loopback diagnostic only (§8).
12. Do not claim ACK, RTT, and loss alone are a sufficient replay input, or that the project
    replays the Linux TCP core as a whole — both are explicitly forbidden claims (CLAUDE.md).
13. Do not perform arbitrary deletion of TCP control events as "trace minimization" — the only
    validated reproducer shape is checkpoint + full suffix.
14. Do not silently relax a correctness oracle after seeing a mismatch to obtain a PASS — any
    relaxation must be documented before accepting a result, must not hide a logic difference, and
    must be named explicitly in the report.
15. Do not call CoVegas's `undo_cwnd` "VALIDATED" by citing CUBIC's Part B auxiliary trace — that
    trace contains no CoVegas events. CoVegas `undo_cwnd` is Outcome A (function-level evidence via
    the shared `tcp_reno_undo_cwnd` helper only; the CoVegas ABI-v2 trace path is unexercised) —
    do not manufacture a CoVegas-specific auxiliary trace to close this in a documentation-only
    task.
16. Do not state the CoVegas historical trigger rate as "1 of 9 runs" — the correct denominator is
    9 off-period boundaries from 3 `HOLD_MS=500` runs (§10, §14). Do not substitute the pooled
    27-boundary full-sweep rate for the `HOLD_MS=500`-specific rate.
17. Do not claim the recorded CUBIC clock bracket "necessarily" reflects the value the reference
    read — the supported statement is semantic compatibility with at least one bracketing value,
    not proof of which one (§7).

## 13. Canonical terminology

- **Replay Contract / Replay ABI** — the versioned, explicit definition of what a trace records at
  each callback boundary (four semantic classes: shared TCP PRE state, controller-private state,
  callback inputs/observations, callback result/controller-owned POST state).
- **Mode A (event-local replay)** — each event replayed independently from its own recorded PRE
  state; no replay state carries across events.
- **Mode B (stateful replay)** — controller-private replay state initialized once and evolved
  across events; shared TCP state still injected from the recording at every event.
- **Self-replay** — replaying a trace through an implementation intended to match the one that
  generated it.
- **Cross-implementation replay** — applying two different implementations to the same recorded
  contract; a software comparison, not a counterfactual network execution.
- **First divergence** — the smallest event sequence number at which two implementations, under
  the same mode and oracle, produce different declared results or semantic state; a logic result,
  not automatically a causal performance explanation.
- **Exact semantic equality** — equality on every field declared exact by the callback/controller
  comparison schema; not raw-byte or "bit-exact" equality.
- **Oracle A / B / C** — event-local self-replay / stateful self-replay / independent live-reference
  implementation (`docs/CORRECTNESS_ORACLES.md`).
- **`CLOCK_STABLE` / `CLOCK_AMBIGUOUS`** — a per-event classification of whether a controller-visible
  clock's before/after snapshot pair agreed or changed during the reference call.
- **`ATTRIBUTED_AND_CHARACTERIZED`** — the clock-investigation verdict meaning the residual is fully
  explained (attributable to a bracketing clock value, no unexplained drift) but not resolved.
- **Replay-critical drop** — a lost event that invalidates a trace's integrity guarantee (checked
  via `invocations == emitted + drops` and gapless sequence, ADR-013).
- **Contract discovery** — finding, before or without invalidating existing evidence, that the
  Replay Contract's originally assumed field/callback set was insufficient.
- **Anti-fitting rule** — model changes are permitted only for category A (missing contract input),
  B (transcription error), or C (recorder bug) — never event-specific fitting to force a match.

## 14. Canonical numbers

Cross-checked against the source reports listed at the top of this document before being written
here.

```text
RENO (v0)
  R0: 112,051 events (37,260 + 37,391 + 37,400), 0 drops, 0 sequence gaps
  R1: 112,051 events checked, 224,120 field comparisons, 0 mismatches
  R2: 112,051 events replayed sequentially, first divergence = NONE

CUBIC (v1)
  Primary raw events: 236,094 -- replay-qualified (dominant connection): 236,088 (6 excluded, ADR-016 stray-socket pattern)
  R3A: 236,088 events checked, 4,485,714 field comparisons
       CLOCK_STABLE: 236,042 events, 0 mismatches
       CLOCK_AMBIGUOUS: 46 events, 4 mismatches
  R3B: rep1 51,323/78,688 before first divergence; rep2 75,603/78,768; rep3 61,729/78,632
       (all three: callback=cong_avoid, clock=CLOCK_AMBIGUOUS)
  Clock ambiguity rate: 46 / 236,088 ~= 1.95e-4  ~=  0.78 us estimated observation window
  Two-sided attribution, ALL 46 CLOCK_AMBIGUOUS events (recomputed on reconciliation):
       MATCHES_BEFORE_ONLY=2  MATCHES_AFTER_ONLY=4  MATCHES_BOTH=40  MATCHES_NEITHER=0
  (narrower Table 2a, the 4 production-convention mismatches only: BEFORE_ONLY=0 AFTER_ONLY=4 BOTH=0 NEITHER=0)
  undo_cwnd auxiliary trace: 75,417 total events, 75,415 dominant-connection, 12 undo_cwnd
       invocations, 0 mismatches, first divergence = NONE (VALIDATED, does not change R3 verdict)

COVEGAS (v2)
  E1: 3 primary traces, 0 drops each, dominant connection >=99.99% each
  E2: 190,277 events checked, 4,982,990 field comparisons, 0 mismatches
  E3: first divergence = NONE, 190,277 sequential transitions (3 independent all-exact runs)
  All 30 semantic private fields (17 dedicated + 6 delay-arm + 7 cubic-arm) changed nontrivially
  undo_cwnd: 0 events in primary traces -- Outcome A (function semantics independently supported
       via the shared tcp_reno_undo_cwnd helper; CoVegas ABI-v2 recorder/model path itself
       unexercised); does not affect the PASS verdict or the historical case study's readiness
  ktime (init/cong_avoid): clock_ktime_ns_before IS the exact value the controller consumes (single
       shared bpf_ktime_get_ns() read, traced in source) -- not a CUBIC-style before/after
       ambiguity; clock_ktime_ns_after is a diagnostic-only elapsed-time bracket, never consumed

HISTORICAL COVEGAS REGRESSION
  Historical rate (HOLD_MS=500): 3 runs, 9 off-period boundaries, 1 observed trigger (not "1 of 9 runs")
  0 of 9 boundaries at HOLD_MS=0 (3 runs); 0 of 9 boundaries at HOLD_MS=2000 (3 runs)
  Full 3-setting sweep: 9 runs, 27 boundaries, 1 trigger pooled (not substitutable for the HOLD_MS=500 rate)
  Current attempts: 3 runs, 9 off-period boundaries, 0 observed trigger events
  Rough binomial sensitivity (independence assumption, not an estimated distribution):
       P(0 in 9, rate 1/9) ~= (8/9)^9 ~= 34.6% -- still the expected outcome (corrected from an
       earlier (8/9)^3 ~= 70% figure that used the wrong denominator)

RECORDER OVERHEAD (N0, loopback diagnostic only)
  baseline_production:  mean 7,933 ns/callback  (3 reps: 6847.0, 8837.0, 8113.6)
  noktime_variant:      mean 9,067 ns/callback  (2 reps: 9872.0, 8261.1)
  nowakeup_variant:     mean   232 ns/callback  (3 reps: 317.8, 191.6, 186.9)
  ratio baseline/nowakeup ~= 34x
```

---

*Source material read to build this document: `CLAUDE.md`, `README.md`, `docs/PROJECT.md`,
`docs/ARCHITECTURE.md`, `docs/SEMANTICS.md`, `docs/REPLAY_ABI.md`, `docs/CORRECTNESS_ORACLES.md`,
`docs/LIMITATIONS.md`, `docs/GATES.md`, `docs/DECISIONS.md`, `docs/PROVENANCE.md`, all
`REPORT_*.md` files, and the `data/*.md` files documenting the historical case study and the
CoVegas Replay Contract audit.*
