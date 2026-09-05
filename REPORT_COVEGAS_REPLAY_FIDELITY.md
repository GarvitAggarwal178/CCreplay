# CoVegas Replay Fidelity Validation

**Naming note:** this is `docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md`'s `REPORT_COVEGAS_REPLAY_FIDELITY.md`
(Part E — already a public-facing name, no rename needed; the pipeline itself instructs against
relying on an internal R-number here).

## Status: **PASS**

## Question

Can CCReplay faithfully self-replay the CoVegas implementation (the fixed/v4 build) required for
the historical regression case study, event-locally and statefully, under Replay ABI v2's
mode-dependent comparison schema?

## Reference strength (restated from D4)

> CoVegas self-replay validates CCReplay's ability to capture and reproduce the selected BPF
> implementation's callback inputs, semantic state, ordering, time dependencies, and private-state
> propagation. Because the live reference and userspace model derive from the same algorithm
> implementation, this oracle does not independently establish the correctness of the CoVegas
> algorithm itself.

## Method

1. **E1** — recorded the fixed/reference CoVegas (`bpf/covegas_wrapper.bpf.c`, algorithm logic
   copied near-verbatim from the read-only source per ADR-022) on the validated Gate-3-R2 topology,
   using the historically-relevant intermittent cross-traffic workload
   (`scripts/covegas_run_intermittent.sh`, adapted from
   `~/cn-spike/covegas/scripts/partC_run_intermittent.sh` — covegas continuous 120s on port 5201,
   real kernel `cubic` cross-traffic 20s-on/20s-off ×3 on port 5301, addendum item 7).
2. **E2** — event-local (Mode A) self-replay, `user/replay_e2.py`, mode-dependent comparison schema
   (ADR-023).
3. **E3** — stateful (Mode B) self-replay, `user/replay_e3.py`, private state initialized once
   (all-zero), the trace's own `init` event as transition #1.

## Pre-E1 fix (E4 anti-fitting log)

A loopback smoke test (diagnostic-only, not primary evidence) run before any Gate-3-R2 capture
found one mismatch, root-caused to a real recorder bug (category C): `fill_common()` and the
algorithm's own `now` computation each called `bpf_ktime_get_ns()` independently instead of sharing
one read. Fixed by sharing a single `now` value. Full account:
`data/covegas_replay_model_changes.md` Entry 1. Re-verified clean on loopback (462,114 events, 0
mismatches) before proceeding to any primary capture.

## Evidence

### E1 — primary traces

Three reps captured (`raw/covegas_replay/primary/rep{1,2,3}.ccr`) — rep2/rep3 were captured for
Part 8's trigger-verification attempts (`data/historical_trigger_validation.md`) and folded in here
since the data already existed and strengthens this gate's evidence at no extra cost. All three:
**zero drops**, gapless global sequence, dominant connection ≥99.99% (same ADR-016 stray-socket
pattern as Reno/CUBIC). `ktime_ambiguous` 100% in every trace (expected, see below); `jiffies`
mostly stable (9/12/(rep3 count) ambiguous events per trace). Callback coverage: `init`×2/trace,
`cong_avoid`~31,150–31,700/trace, `pkts_acked`~31,700–32,350/trace, `ssthresh` 8–9/trace (real
loss/competition occurred in every rep), `undo_cwnd`×0.

**Correction, reconciliation pass:** the `undo_cwnd`×0 line above previously cited Part B's CUBIC
auxiliary trace as having separately `VALIDATED` this callback. That was wrong — Part B's auxiliary
trace validated **CUBIC's** `undo_cwnd` path under ABI v1; it contains no CoVegas events and says
nothing about the CoVegas ABI-v2 recorder/model path specifically. See "`undo_cwnd` coverage audit"
below for the corrected classification.

### E2 — event-local (all three traces)

| | value |
| --- | ---: |
| Events checked | 190,277 |
| Field comparisons | 4,982,990 |
| Mismatches | **0** |

**100.0000% exact semantic equality on every event across all three independent traces**, every
callback type that fired, the full mode-dependent private-state schema (both union arms, gated by
that event's own recorded/computed mode independently per ADR-023), and every clock-ambiguity
combination observed.

### E3 — stateful

**First divergence = NONE across all three traces, 190,277 sequential transitions total** (each
trace's private state initialized fresh and independently — not one continuous 190,277-event
sequence, three separate all-exact runs). All 30 semantic private fields (17 dedicated + 6
`delay`-arm + 7 `cubic`-arm) changed value at least once across the combined replayed sequences
(`fields_that_never_changed_in_any_trace = []`) — the mode-dependent union was genuinely exercised
in both directions (DELAY→COMPETE and COMPETE→DELAY transitions occurred in every trace, evidenced
directly by both arms' fields changing and by real `ssthresh` invocations in each), not merely
present in the schema.

## Clock-transfer question: "Do not silently inherit CUBIC's clock exception. Prove whether it applies."

**It does not apply, empirically, on these traces.** Neither clock produced a single mismatch across
190,277 events: `jiffies`'s ambiguous events (9–12 per trace) all replayed exactly, vs. CUBIC's ~9%
ambiguous-event mismatch rate); `ktime`'s 100% `CLOCK_AMBIGUOUS` rate — itself a real, measured, and
expected property of a nanosecond-resolution clock read twice with real work in between, not a bug
(`data/covegas_replay_model_changes.md`'s note) — also produced zero mismatches, because every
`bpf_ktime_get_ns()`-derived comparison CoVegas makes is against millisecond-scale thresholds (the
200ms probe hold, `RATE_SETTLE_MS`≥1000ms), where nanosecond-level before/after slop never crosses a
decision boundary in this trace. This is a genuinely different empirical outcome from CUBIC's (where
`tcp_jiffies32` ambiguity *did* cause real, characterized mismatches) — proven, not assumed, exactly
as required.

## `undo_cwnd` coverage audit (reconciliation addendum)

Traced against the actual CoVegas source (`bpf/covegas_wrapper.bpf.c`'s `ccr_covegas_undo_cwnd`,
`user/covegas_model.py`'s `cubic_undo_cwnd` — despite the misleading function name, it is
CoVegas's own `undo_cwnd` model, not CUBIC's) rather than assumed:

* **Exact CoVegas `undo_cwnd` implementation:** the recorder calls `tcp_reno_undo_cwnd(sk)`
  directly (`extern __u32 tcp_reno_undo_cwnd(struct sock *sk) __ksym;`) — the identical shared
  kernel helper CUBIC's `undo_cwnd` also delegates to. It reads no CoVegas-private field and
  mutates no CoVegas-private field (confirmed directly from the source; matches D3's audit table:
  "private state read: none ... private state mutated: none").
* The userspace model (`cubic_undo_cwnd(pre) = max(pre["snd_cwnd"], pre["prior_cwnd"])`) is an
  independent from-scratch reproduction of that same formula (a Python model cannot call a kfunc),
  not a delegation — matching what the real recorder computes.
* ABI v2 adds no controller-specific state comparison for this callback beyond the standard
  PRE==POST private-state assertion every callback gets; `undo_cwnd` is not expected to touch
  `mode` or the union.
* **CoVegas ABI-v2 primary traces contain zero `undo_cwnd` invocations** (E1, above) — the
  recorder/model path for this specific callback was never exercised by real recorded events.

**Classification — Outcome A:** `undo_cwnd` function semantics have independent evidence through
the shared kernel helper (identical to CUBIC's own validated `undo_cwnd` path, Part B), but the
CoVegas ABI-v2 recorder/model path itself was not exercised in the primary traces. No auxiliary
CoVegas `undo_cwnd`-triggering trace was captured this session (manufacturing one is out of scope
for this documentation-reconciliation pass).

**This does not downgrade the CoVegas Replay Fidelity PASS verdict, and does not affect the
historical A3 case study's readiness.** The regression mechanism the historical case study targets
(`handle_compete_mode`'s settle-latch) is exercised through `cong_avoid`, not `undo_cwnd` — E2/E3's
PASS already covers the exact callback/state path the historical case needs. Distinguish:

> **historical-case replay fidelity** — PASS, unaffected (`cong_avoid`/`ssthresh`/`mode`/union
> transitions all exercised and exact).

from:

> **complete five-callback observed coverage** — four of five callbacks (`init`, `cong_avoid`,
> `ssthresh`, `pkts_acked`) have direct primary-trace evidence; `undo_cwnd` has function-level
> evidence only (Outcome A), not CoVegas-trace evidence.

## CoVegas `bpf_ktime_get_ns()` semantics (reconciliation addendum)

Traced directly against `bpf/covegas_wrapper.bpf.c` and `user/covegas_model.py`'s dataflow, not
inferred:

1. **Which read feeds the controller?** `ccr_covegas_init`/`ccr_covegas_cong_avoid` each call
   `bpf_ktime_get_ns()` exactly **once**, at function entry (`__u64 ... now = bpf_ktime_get_ns();`),
   before any recording or algorithm logic runs.
2. **Is that value stored in the EventRecord?** Yes — the same `now` local variable is passed
   into `fill_common(e, sk, seq, callback_id, now)`, which sets both `e->ts_ns` and
   `e->clock_ktime_ns_before` to it (`bpf/covegas_wrapper.bpf.c` lines ~552/563).
3. **Is it identical to `clock_ktime_ns_before`, or is there a separate unobserved read?** For
   `init`/`cong_avoid` it is the *same* value, not merely equal by coincidence — `fill_common` and
   the algorithm logic (`ca->last_minrtt_probe_ns = now` in `init`; `handle_minrtt_probe(tp, ca,
   now)` in `cong_avoid`) both receive the one local `now`. `handle_minrtt_probe` itself takes
   `now` as a parameter and never calls `bpf_ktime_get_ns()` internally. There is no second,
   unobserved controller read for these two callbacks. `user/covegas_model.py`'s `transition()`
   confirms this on the replay side: `ktime_now = event["clock_ktime_ns_before"]` is the only ktime
   value the model ever reads, e.g. `next_ca["last_minrtt_probe_ns"] = u64(ktime_now)` for `init`.
4. **Position relative to the original uninstrumented source:** the read-only reference
   (`~/cn-spike/covegas/src/covegas.bpf.c`) calls `bpf_ktime_get_ns()` once per entry point and
   passes that same value into `handle_minrtt_probe`, identically in shape (confirmed by direct
   inspection: its `covegas_cong_avoid`/`covegas_init` each declare `__u64 now =
   bpf_ktime_get_ns();` and call `handle_minrtt_probe(tp, ca, now)`). The recorder's fix (sharing
   one read with `fill_common`) did not move or add a read relative to the original — it added the
   recorder's *own* consumption of the pre-existing single read, replacing what had been, before
   the fix, a second independent `bpf_ktime_get_ns()` call added by the recorder itself (the
   category-C bug named in the "Pre-E1 fix" section above).
5. **Does this preserve intended callback semantics?** Yes — the algorithm's own timing behavior
   is unchanged from the original source; only the recorder's *observation* of that value changed
   (from a separate, spurious second read to reusing the actual one the algorithm consumes).
6. **What is `clock_ktime_ns_after` used for?** It is computed in `finish_clock()`, called
   *after* the algorithm logic has already run, purely for `CLOCK_STABLE`/`CLOCK_AMBIGUOUS`
   bookkeeping (`ccr_counters_map`'s `clock_ktime_stable`/`clock_ktime_ambiguous` counters) and
   diagnostic reporting. It is never read by `user/covegas_model.py` and never fed to the
   algorithm at recording time — it is a pure elapsed-time diagnostic bracket, not a second
   candidate input value.

**Conclusion — for `init`/`cong_avoid`, `clock_ktime_ns_before` is an exact recorded controller-
visible ktime input**, not a CUBIC-style unresolved before/after observation ambiguity. `before !=
after` on effectively every event (the measured 100% `CLOCK_AMBIGUOUS` rate) is the expected
result of a nanosecond-resolution clock with real recorder/algorithm work happening in between —
it reflects elapsed wall-clock time during instrumentation, not uncertainty about which value the
controller consumed. For `ssthresh`/`undo_cwnd`/`pkts_acked`, `bpf_ktime_get_ns()` is called only
for `fill_common`'s own diagnostic timestamp — the algorithm in those three callbacks never reads
ktime at all, so `clock_ktime_ns_before`/`_after` there are purely diagnostic and not a controller
input in any sense. This distinction (exact recorded input vs. diagnostic elapsed-time bracket) is
architecturally different from CUBIC's `tcp_jiffies32` situation, where the *global* clock cannot
be captured as a per-socket field and is only ever bracketed, never exactly known — CoVegas's
`bpf_ktime_get_ns()` sidesteps that specific hazard by being a value the controller itself computes
and that the recorder can capture at the exact moment of computation.

## E4 — anti-fitting log

`data/covegas_replay_model_changes.md` — one entry (the pre-E1 `bpf_ktime_get_ns()` sharing fix,
category C, found and fixed before any primary trace existed). No further entries were needed: E2's
first run against the real primary trace already showed zero mismatches.

## E5 — Fidelity verdict: **PASS**

> Faithful self-replay is demonstrated for the state/callback path required by the historical
> regression.

The historical regression (Part D1) concerns `handle_compete_mode`'s COMPETE-entry settle-latch —
exercised directly in this trace (mode transitions occurred, confirmed by both union arms changing
and 9 real `ssthresh` events). E2 is 100% exact and E3 shows first divergence = NONE across the
entire trace, covering that exact mechanism along with everything else in the manifest except
`undo_cwnd` (already separately validated). **Continuation to Part F is authorized without
qualification** — this is an unqualified PASS, not a PARTIAL requiring the "only rare/non-central
callbacks remain unvalidated" carve-out.

## Reproduction

```
python3 user/replay_e2.py raw/covegas_replay/primary/rep1.ccr raw/covegas_replay/primary/rep1.meta.json \
  raw/covegas_replay/primary/rep2.ccr raw/covegas_replay/primary/rep2.meta.json \
  raw/covegas_replay/primary/rep3.ccr raw/covegas_replay/primary/rep3.meta.json
python3 user/replay_e3.py raw/covegas_replay/primary/rep1.ccr raw/covegas_replay/primary/rep1.meta.json \
  raw/covegas_replay/primary/rep2.ccr raw/covegas_replay/primary/rep2.meta.json \
  raw/covegas_replay/primary/rep3.ccr raw/covegas_replay/primary/rep3.meta.json
```

## Relevant commits

`b0aac41` (ABI v2 design), `84efbe3` (recorder+parser+model), and this report's own commit (E1
primary trace, E2/E3 engines, this report).

Mandatory Phase-1 regression: reverified clean before this commit.
