# N5 Controlled Regression Case Study — Predictions

Precommitted **before** running `user/ccreplay_diff.py` against any of the seeded-bug variants
below, per the pipeline's explicit "COMMIT THIS FILE BEFORE RUNNING THE DEBUGGER" instruction. The
bug variant files described here do not yet exist at the time this file is committed (verify via
`git log` timestamps, not merely this sentence). A RESULTS section is appended after running —
these predictions are never rewritten.

All four bugs are seeded as full-file copies of `user/cubic_model.py` with exactly one line changed
each (`user/cubic_model_bug_*.py`), diffed against `user/cubic_model.py` to make "exact source
change" independently verifiable rather than merely asserted. Each is diffed via
`user/ccreplay_diff.py` with `--reference user.cubic_model --candidate user.cubic_model_bug_<name>`
against all three primary CUBIC traces (`raw/cubic_replay/primary/rep{1,2,3}.ccr`).

## Bug 1 — wrong `ssthresh` reduction (positive control)

* **Exact source change:** `cubictcp_recalc_ssthresh`'s return statement —
  `return result, ca` where `result = max((cwnd * BETA) // BICTCP_BETA_SCALE, 2)` becomes
  `result = max((cwnd * BETA) // BICTCP_BETA_SCALE, 2) + 1` (always off by exactly +1).
* **Predicted callback class:** `ssthresh`.
* **Predicted result/state field:** `result` (off by +1 on every triggering event).
* **Predicted trigger class:** every `ssthresh` event.
* **Primary workload exercise:** YES — `ssthresh` fired 14 times in every one of the three primary
  reps (`REPORT_CUBIC_REPLAY_VALIDATION.md`'s coverage table). Predicted first divergence: the
  first `ssthresh` event in the dominant-connection sequence.

## Bug 2 — incorrect ACK accounting (positive control)

* **Exact source change:** `bictcp_update`'s first line —
  `ca["ack_cnt"] = u32(ca["ack_cnt"] + acked)` becomes `ca["ack_cnt"] = u32(ca["ack_cnt"] + 1)`
  (always increments by exactly 1, ignoring the real `acked` count — a classic "forgot to use the
  parameter" defect).
* **Predicted callback class:** `cong_avoid`.
* **Predicted result/state field:** `priv_post_ack_cnt` (immediately), with likely cascading
  divergence into `priv_post_tcp_cwnd`/`priv_post_cnt` on a later event once the wrong `ack_cnt`
  crosses a `_tcp_friendliness` threshold.
* **Predicted trigger class:** the very first `cong_avoid` event where `acked != 1` — expected to
  be extremely early (`acked` is very often 2 for a standard-MSS ACK train, so this is predicted to
  diverge on the first or second `cong_avoid` event, well before `ssthresh`'s first occurrence).
* **Primary workload exercise:** YES — `cong_avoid` is the dominant callback (~37,000+ events per
  rep).

## Bug 3 — epoch/reset defect (positive control)

* **Exact source change:** `cubictcp_recalc_ssthresh` — the line `ca["epoch_start"] = 0` is
  removed (the function no longer ends the CUBIC epoch on a cwnd reduction).
* **Predicted callback class:** `ssthresh` (immediately: `priv_post_epoch_start` differs at the
  `ssthresh` event itself, since the real function always zeroes it unconditionally).
* **Predicted result/state field:** `priv_post_epoch_start` at the triggering `ssthresh` event.
* **Predicted trigger class:** the very first `ssthresh` event — predicted to diverge at the SAME
  event as Bug 1 (both are `ssthresh`-callback bugs), but on a different field, so it is predicted
  to fire independently even if Bug 1 were absent.
* **Primary workload exercise:** YES — same 14 `ssthresh` events per rep as Bug 1.

## Bug 4 — dormant defect (required negative control)

* **Exact source change:** `cubictcp_undo_cwnd`'s return statement —
  `return max(pre["snd_cwnd"], pre["prior_cwnd"])` becomes
  `return min(pre["snd_cwnd"], pre["prior_cwnd"])`.
* **Predicted callback class:** `undo_cwnd`.
* **Predicted result/state field:** `result`.
* **Predicted trigger class:** any `undo_cwnd` event.
* **Primary workload exercise:** **NO** — `undo_cwnd` fired exactly 0 times across all three
  primary reps (`REPORT_CUBIC_REPLAY_VALIDATION.md`'s coverage table, `UNVALIDATED`). Precommitted
  expected result against the primary traces: **NO DIVERGENCE** — the defect exists in the
  candidate's source but the primary workload's callback stream never reaches the changed code
  path, so the diff engine has no opportunity to observe it. If `ccreplay_diff.py` reports
  divergence anyway, that is a false positive in the diff engine or the model, to be investigated
  before declaring N5 anything but FAIL for this control.

## Reference-vs-reference control

For every run below, `raw/cubic_replay/primary/rep{1,2,3}.ccr` diffed with
`--reference user.cubic_model --candidate user.cubic_model` must continue to report NO DIVERGENCE
(already established in `REPORT_DIFFERENTIAL_DEBUGGER.md`'s N4 hard negative oracle; re-asserted
here as a standing invariant every N5 run is expected to preserve, not re-verified from scratch
each time).

---

## RESULTS

Run via `user/ccreplay_diff.py --reference user.cubic_model --candidate user.cubic_model_bug_<name>`
against all three primary traces. Predictions above are unmodified; this section is purely additive.

| bug | prediction correct? | matched before divergence (rep1/2/3) | actual callback | actual field | actual value diff |
| --- | --- | ---: | --- | --- | --- |
| 1 — wrong ssthresh | **YES, exactly** | 1704 / 1722 / 1710 | `ssthresh` | `result` | reference=145, candidate=146 (+1, exactly as predicted) |
| 2 — ACK accounting | **PARTIALLY** (trigger class right, magnitude off) | 587 / 565 / 623 | `cong_avoid` | `priv_post_ack_cnt` | matches |
| 3 — epoch/reset | **YES, exactly** | 1704 / 1722 / 1710 (same event as Bug 1, as predicted) | `ssthresh` | `priv_post_epoch_start` | matches |
| 4 — dormant undo | **YES, exactly** | 78,688 / 78,768 / 78,632 (full trace, no divergence) | — | — | **NO DIVERGENCE**, confirmed |

**Bug 2 detail on the partial miss:** the prediction stated the divergence would appear "on the
first or second `cong_avoid` event... extremely early," reasoning that a standard-MSS ACK train
usually carries `acked=2`. The trigger *class* was correct — the bug is invisible whenever the real
`acked` value happens to equal 1 (since `+1` and `+acked` then coincide) — but slow-start's earliest
growth phase apparently produces `acked=1` far more often than assumed (587/565/623 matched events
elapsed, all presumably `acked==1`, before the first `acked!=1` event). This is recorded as a
partial miss rather than silently rounded up to "correct," per the pipeline's "do not rewrite
predictions" instruction — the reasoning behind the prediction was sound in kind, wrong in
magnitude.

**Reference-vs-reference control:** re-verified NO DIVERGENCE on all three primary traces
immediately before this run (already established in `REPORT_DIFFERENTIAL_DEBUGGER.md`'s N4 hard
negative oracle; the standing invariant held).

**Overall: 3 of 4 predictions exactly correct, 1 partially correct (right class, wrong magnitude),
0 wrong, 0 false positives on the dormant control.** N5 is declared PASS — see
`REPORT_CONTROLLED_REGRESSION_CASE_STUDY.md`.
