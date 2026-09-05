# CCReplay — Demo Numbers (every value cites a repository source)

Snapshot taken during Phase 6 of `docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md`. Historical numbers
reflect the status **at this point** and do not pretend a new campaign has succeeded.

## Reno (Replay ABI v0)

| value | source |
| --- | --- |
| 112,051 events (37,260 + 37,391 + 37,400) | `REPORT_PHASE1_RENO_REPLAY_VALIDATION.md` §D / terminal block |
| 0 drops, 0 sequence gaps | `REPORT_PHASE1_RENO_REPLAY_VALIDATION.md` §D; `raw/r0/rep{1,2,3}_validation.json` |
| 224,120 R1 field comparisons, 0 mismatches | `REPORT_PHASE1_RENO_REPLAY_VALIDATION.md` §E |
| R2 first divergence = NONE | `REPORT_PHASE1_RENO_REPLAY_VALIDATION.md` §F |

Caveat: **Reno has no non-trivial controller-private state** (ADR-014; `docs/LIMITATIONS.md` #13,
closed for CUBIC by R3B).

## CUBIC (Replay ABI v1)

| value | source |
| --- | --- |
| 236,094 raw primary events | `REPORT_CUBIC_REPLAY_VALIDATION.md` "Event-count accounting" |
| 236,088 replay-qualified (dominant-connection) events | same |
| 236,042 `CLOCK_STABLE` events, **0** `CLOCK_STABLE` mismatches | `REPORT_CUBIC_REPLAY_VALIDATION.md` R3A table |
| 46 `CLOCK_AMBIGUOUS` events, 4 production-convention mismatches | same |
| full-46 two-sided attribution = **2 `BEFORE_ONLY` / 4 `AFTER_ONLY` / 40 `BOTH` / 0 `NEITHER`** | `REPORT_CUBIC_CLOCK_BOUNDARY_INVESTIGATION.md` Table 2b; `data/cubic_clock_boundary_attribution_all_ambiguous.json` |
| **R3 = PARTIAL** (not PASS) | `REPORT_CUBIC_REPLAY_VALIDATION.md` "Gate verdict"; `docs/CURRENT_STATE.md` §5 |
| 16 semantic private fields (`struct bictcp`, `unused` excluded) | ADR-019; `docs/REPLAY_ABI.md` "v1 concrete instantiation" |
| `undo_cwnd` auxiliary trace: 12 invocations, 0 mismatches (75,417-event trace) | `REPORT_CUBIC_REPLAY_VALIDATION.md` "Auxiliary evidence: `undo_cwnd` (Part B)" |
| ~780 ns clock-observation window is **inferred from tick-collision probability**, not directly measured | `REPORT_CUBIC_CLOCK_BOUNDARY_INVESTIGATION.md` §1 |

## N4 / N5 / N6 (differential debugger)

| value | source |
| --- | --- |
| identical-vs-identical → **NO DIVERGENCE** (Reno 37,260 events; CUBIC 78,688 events) | `REPORT_DIFFERENTIAL_DEBUGGER.md` hard-negative oracle |
| N5: 4 seeded variants — 3 positive controls + 1 dormant negative control | `REPORT_CONTROLLED_REGRESSION_CASE_STUDY.md`; `data/n5_predictions.md` |
| bug 1 (wrong `ssthresh` reduction, +1): **exact** — first divergence event 1704 / seq 1705 / `ssthresh` / `result` (145 vs 146) | `REPORT_CONTROLLED_REGRESSION_CASE_STUDY.md`; `data/n5_predictions.md`; re-run in `scripts/demo/demo_02_first_divergence.sh` |
| bug 2 (ACK accounting): callback/field correct; trigger-event timing estimate a partial miss (disclosed, not rounded up) | `REPORT_CONTROLLED_REGRESSION_CASE_STUDY.md`; `data/n5_predictions.md` |
| bug 3 (epoch/reset): **exact** | same |
| bug 4 (dormant `undo_cwnd` defect): **NO DIVERGENCE** on 78,688 / 78,768 / 78,632 events — no false positive | same |
| N6: checkpoint every 500 events → checkpoint at 1500, divergence at 1704, **204-event full suffix**, identical divergence reproduced | `REPORT_CHECKPOINT_REPRODUCER.md`; re-run in `scripts/demo/demo_03_checkpoint_reproducer.sh` |
| checkpoint serialization **byte-identical** across independent runs (`json.dumps(..., sort_keys=True)`) | `REPORT_CHECKPOINT_REPRODUCER.md` |

`byte-identical` is used here **only** for the literal checkpoint-serialization result.

## CoVegas (Replay ABI v2)

| value | source |
| --- | --- |
| 190,277 events (E2), 4,982,990 field comparisons, **0** mismatches | `REPORT_COVEGAS_REPLAY_FIDELITY.md` E2 |
| stateful first divergence = **NONE** on all 3 traces (E3) | `REPORT_COVEGAS_REPLAY_FIDELITY.md` E3 |
| 30 semantic private fields (17 dedicated + 6 DELAY-arm + 7 COMPETE-arm / `u.cubic.*`) | `docs/REPLAY_ABI.md` "v2 concrete instantiation"; ADR-023 |
| CoVegas Replay Fidelity = **PASS** (unqualified) | `REPORT_COVEGAS_REPLAY_FIDELITY.md` E5 |

Caveat: `undo_cwnd` for CoVegas is **Outcome A** — function-level evidence via the shared
`tcp_reno_undo_cwnd` helper only; **0 CoVegas ABI-v2 trace invocations** (`docs/CURRENT_STATE.md`
§5; `REPORT_COVEGAS_REPLAY_FIDELITY.md` "`undo_cwnd` coverage audit").

## Historical CoVegas A3 case (status at Phase 6)

| value | source |
| --- | --- |
| **INCOMPLETE** — historical off-period trigger not reproduced; buggy-vs-fixed differential replay not run | `REPORT_HISTORICAL_COVEGAS_REGRESSION.md`; `docs/CURRENT_STATE.md` §5 |
| historical `HOLD_MS=500` descriptive rate: 1 spurious off-period re-entry / 9 off-period boundaries (3 runs) | `data/historical_trigger_validation.md`; `~/cn-spike/covegas/REPORT_COVEGAS_V4.md` B2 |
| existing-trace scan: Predicate H and Predicate D both **absent** in all 3 v2 traces (interpretation **CASE 4**) | `data/historical_a3_existing_trace_scan.md`; `REPORT_EVIDENCE_RECONCILIATION_AND_A3_PREDICATE_AUDIT.md` |
| reconstructed-v3 A3 candidate: `ONLY_A3_SEMANTIC_DIFFERENCE = YES`; synthetic positive control PASS; fixed/v3 real-trace diff NO DIVERGENCE ×3 | `data/a3_reconstructed_candidate_diff.md`; `data/a3_candidate_controls.json` |

## Demo re-run (Phase 6.7 rehearsal)

`bash scripts/demo/demo_00_run_all.sh` → **EXIT 0**, wall-clock **≈ 1.6 s**. All three steps PASS;
outputs agree with the N4 / N5 / N6 committed reports (78,688-event negative control NO DIVERGENCE;
first divergence event 1704 / seq 1705 / `ssthresh` / `result` 145→146; checkpoint 1500 → suffix
204 → identical reproduced).
