# Case Studies Re-confirmation Results

## Summary

All 5 documented differential-debugger case studies have been re-run and **all cases match their expected, already-documented outcomes**.

## Results Table

The "Expected" column is the verdict (DIVERGENCE / NO DIVERGENCE) documented qualitatively in
`docs/CASE_STUDIES.md` and, where a specific seq is pinned down, `docs/CURRENT_STATE.md` section 14.
**Only positive_1_ssthresh, negative_dormant_undo, and historical_a3 have a pre-existing documented
seq to check against** (section 14: seq 1,705 / NO DIVERGENCE / seq 10,421). positive_2_epoch_reset
and positive_3_ack_accounting are documented only as "DIVERGENCE expected" with a qualitative
callback-type description (CASE_STUDIES.md: a state-reset bug diverges "first event after the reset
should have occurred"; an ACK-accounting bug diverges at "first congestion-avoidance event where
altered accounting changes a controller-owned state transition") -- their seq numbers below are this
run's own output, not a value matched against a prior canonical number, and are reported as
observations, not confirmations:

| Case | Expected (verdict) | Observed (verdict) | First Divergent Seq | Callback | Verdict match | Seq independently documented? |
|------|---------------------|---------------------|---------------------|----------|----------------|-------------------------------|
| positive_1_ssthresh | DIVERGENCE | DIVERGENCE | 1705 | ssthresh | ✓ | yes -- matches CURRENT_STATE §14 |
| positive_2_epoch_reset | DIVERGENCE | DIVERGENCE | 1705 | ssthresh | ✓ | no -- observed only, qualitative match to "first event after reset" |
| positive_3_ack_accounting | DIVERGENCE | DIVERGENCE | 588 | cong_avoid | ✓ | no -- observed only, qualitative match to "cong_avoid" callback type |
| negative_dormant_undo | NO DIVERGENCE | NO DIVERGENCE | None | None | ✓ | yes -- matches CURRENT_STATE §14 |
| historical_a3 | DIVERGENCE | DIVERGENCE | 10421 | cong_avoid | ✓ | yes -- matches CURRENT_STATE §14 |

positive_1 and positive_2 sharing seq 1705 was checked for a script bug and confirmed genuine (they
use distinct candidate controller ids, `cubic_bug_ssthresh` and `cubic_bug_epoch_reset`; both bugs
happen to first manifest at the same recorded ssthresh callback in this trace).

## Critical Sanity Checks

The checks that compare against a pre-existing documented number all pass:

- **Case 'positive_1_ssthresh'**: first_divergent_seq=1705, callback='ssthresh' ✓ (CURRENT_STATE §14)
- **Case 'negative_dormant_undo'**: observed_result='NO DIVERGENCE' (confirmed dormant negative control) ✓ (CURRENT_STATE §14)
- **Case 'historical_a3'**: first_divergent_seq=10421 ✓ (CURRENT_STATE §14)

positive_2 and positive_3's verdicts (DIVERGENCE) match their documented qualitative expectation, but
their specific seq/callback values have no prior documented number to check against -- see table note
above.

## Conclusion

The three cases with a pre-existing documented seq (positive_1_ssthresh, negative_dormant_undo,
historical_a3) all matched docs/CURRENT_STATE.md section 14 exactly. The remaining two
(positive_2_epoch_reset, positive_3_ack_accounting) matched their documented qualitative verdict and
callback-type expectation from docs/CASE_STUDIES.md; their exact seq numbers are this run's own
output, reported here for the record, not a confirmation against a prior pinned value. The
differential debugger continues to correctly identify regressions in seeded bug variants and
successfully reproduces the historical CoVegas A3 regression on the acquired campaign trace
(raw/covegas_campaign/rep4.ccr).
