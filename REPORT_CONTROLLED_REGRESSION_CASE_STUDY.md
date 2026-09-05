# Controlled Regression Case Study (N5)

**Naming note:** this is `docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md`'s
`REPORT_CONTROLLED_REGRESSION_CASE_STUDY.md` (already a public-facing name, no rename needed).

## Status: PASS

## Question

Does `user/ccreplay_diff.py` (N4) correctly localize seeded, known defects to the right callback
and field, and correctly report no divergence for a defect the primary workload never exercises?

## Method

Four single-line bug variants of `user/cubic_model.py` (`user/cubic_model_bug_*.py`), each an exact
copy with one deliberate change, per `data/n5_predictions.md`'s precommitted predictions (committed
`4d2972e`, before any bug file existed). Diffed via `user/ccreplay_diff.py --reference
user.cubic_model --candidate user.cubic_model_bug_<name>` against all three primary CUBIC traces.

## Results

| bug | class | correct? |
| --- | --- | --- |
| 1 — wrong `ssthresh` reduction (+1) | positive control | **exact** |
| 2 — incorrect ACK accounting | positive control | **partial** (right callback/field, trigger event later than the optimistic estimate) |
| 3 — epoch/reset defect | positive control | **exact** |
| 4 — dormant `undo_cwnd` defect | **required negative control** | **exact — NO DIVERGENCE**, 78,688/78,768/78,632 events fully replayed with no false positive |

Full detail, including the exact predicted-vs-actual values and the honest accounting of Bug 2's
partial miss (predictions not rewritten, a RESULTS section appended instead): `data/n5_predictions.md`.

Reference-vs-reference (both sides `user.cubic_model`) re-confirmed NO DIVERGENCE on all three
traces immediately before the bug runs — the standing invariant from `REPORT_DIFFERENTIAL_DEBUGGER.md`'s
N4 hard negative oracle held throughout.

## Why PASS

* Predictions were committed (`4d2972e`) strictly before any bug code existed — verified by commit
  ordering, not merely asserted.
* The required dormant-defect negative control produced its precommitted expected result (NO
  DIVERGENCE) exactly — no false positive.
* All three positive controls produced genuine divergence, correctly localized to the predicted
  callback and field in every case; two of three matched the predicted trigger event exactly, one
  matched the predicted callback/field exactly but not the predicted trigger magnitude (reported as
  a partial miss, not rounded up).
* No prediction was silently corrected after the fact; the one partial miss is documented with its
  reasoning gap named explicitly (slow-start's early `acked==1` frequency was underestimated).

## Reproduction

```
python3 user/ccreplay_diff.py raw/cubic_replay/primary/rep1.ccr raw/cubic_replay/primary/rep1.meta.json \
  --reference user.cubic_model --candidate user.cubic_model_bug_ssthresh
```
(substitute `_ack_accounting`, `_epoch_reset`, `_dormant_undo` and `rep2`/`rep3` as needed).

## Relevant commits

`4d2972e` (predictions precommit), and this report's own commit (bug variant files + RESULTS
section + this report).

Mandatory Phase-1 regression: reverified clean before this commit (26 v0 + 14 v1 = 40 tests).
