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

## Historical CoVegas A3 reconstructed-regression case study — **PASS** (post-success closure)

**PASS means:** on a newly acquired Replay-ABI-v2 fixed/v4 callback stream containing the
predeclared historical off-period A3 condition, the precommitted reconstructed-v3 candidate first
diverged from fixed/v4 at the precommitted same-episode Predicate-D callback. This is a **separate
gate** from CoVegas v2 self-replay fidelity (also PASS) — do not merge them.

**Two mandatory caveats:** (1) `reconstructed-v3` is a documented reconstruction (v4 source, A3
guard reverted), not original committed v3 source; (2) the Replay-ABI-v2 differential-debugger
path was implemented in the same session that produced this result — validated by precommitted
positive/negative controls, `tests/test_ccreplay_diff_v2.py` (7 tests), the final ABI regression,
and exact agreement with the precommitted first-divergence prediction.

| value | source |
| --- | --- |
| Originally **INCOMPLETE** (trigger not reproduced in 3 bounded attempts) → **PASS** (reconstructed-regression case study) | `REPORT_HISTORICAL_COVEGAS_REGRESSION.md`; `data/historical_case_freeze_decision.md`; `docs/CURRENT_STATE.md` §10 |
| capped acquisition campaign: 4 attempts / 4 valid runs / 12 valid boundaries; H=1, D=1, **H+D same episode = 1** on valid run 4; stopped on first acquisition (cap 9 valid / 12 total) | `REPORT_FINAL_HISTORICAL_CAPTURE_CAMPAIGN.md`; `data/historical_capture_campaign_results.json` |
| acquired trace `raw/covegas_campaign/rep4.ccr` (sha256 `1aeabe0283e3f0a52936391dde18ec86093c524b4f90cad319b901ef067d65de`): H DELAY→COMPETE `seq=9533` (`ROBUST_OFF`); D settle-latch guard FAIL `seq=10421`, ratio 1,192,908/1,197,822 = **0.9959** | same |
| `fixed/v4` vs `reconstructed-v3`: first divergence **event 10420 / seq 10421 / `cong_avoid`** (10,420 events matched before); `priv_post_mode` DELAY↔COMPETE, `priv_post_dlv_rate_compete` 0↔1,192,908, + `revert_to_delay`-vs-`cubic_growth` field set; divergent event is `CLOCK_STABLE` | `REPORT_FINAL_HISTORICAL_CAPTURE_CAMPAIGN.md`; `scripts/demo/demo_04_historical_a3.sh` |
| `post_snd_cwnd` at first divergence: `v4 = 37`, `v3 = 65` — **computed boundary values** under the same recorded input state; NOT an alternate trajectory | `REPORT_FINAL_HISTORICAL_CAPTURE_CAMPAIGN.md` "On the `post_snd_cwnd` difference" |
| matches precommitted prediction `data/a3_reconstructed_candidate_predictions.md` §2.4 (commit `b8af8c1`, before capture) exactly | `data/historical_regression_predictions.md` RESULTS section |
| historical suffix reproducer: checkpoint@event 10000 + **420-event suffix** reproduces the identical divergence | `data/demo/historical_a3_checkpoints.json`; `tests/test_ccreplay_diff_v2.py::TestV2CheckpointReproducer` |
| reconstructed-v3 A3 candidate: `ONLY_A3_SEMANTIC_DIFFERENCE = YES`; synthetic positive control PASS; fixed/v3 on the 3 *original* traces NO DIVERGENCE ×3 | `data/a3_reconstructed_candidate_diff.md`; `data/a3_candidate_controls.json` |
| guard-ratio: 26 total ON-period eligible evaluations range **0.097–0.711** (all PASS); the one OFF-period H+D episode = **0.9959** (FAIL); archived historical positive ≈ 0.9977 — mechanism-consistent, not a phase→ratio causal law, not `H ⇒ D` | `data/a3_guard_ratio_analysis.md` |

Narrow claim only — **not** alternate throughput / RTT / queue state, **not** a recreated network
outcome. `reconstructed-v3` is a documented reconstruction (v4 source, A3 guard reverted), not
original committed v3 source.

## Demo re-run (Phase 6.7 rehearsal)

`bash scripts/demo/demo_00_run_all.sh` → **EXIT 0**, wall-clock **≈ 1.6 s**. All three steps PASS;
outputs agree with the N4 / N5 / N6 committed reports (78,688-event negative control NO DIVERGENCE;
first divergence event 1704 / seq 1705 / `ssthresh` / `result` 145→146; checkpoint 1500 → suffix
204 → identical reproduced).
