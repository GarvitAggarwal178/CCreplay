# Reno Retention-Fraction Sensitivity Analysis

## Critical Sanity Check: PASSED

The 1/2 (standard) ratio comparison against itself shows:
- **rep1**: n_disagree = 0 (0.0% disagreement rate)
- **rep2**: n_disagree = 0 (0.0% disagreement rate)
- **rep3**: n_disagree = 0 (0.0% disagreement rate)

All three traces confirm that self-replay with identical parameters produces zero disagreements, validating the test framework integrity.

## Key Findings

The Reno ssthresh formula under loss is `ssthresh = (cwnd * num) // den`, where the standard ratio is num=1, den=2 (i.e. cwnd halved on loss).

### Disagreement Summary

All non-standard ratios showed exactly 6 disagreement events across all three traces, consistently localized to **ssthresh callbacks**. This is expected behavior for integer-division-dependent formulas where different (num, den) pairs produce different quotients.

### Results by Ratio

| Ratio | Retention % | Median Result Delta | Per-Trace Disagreements | Observations |
|-------|-------------|---------------------|-------------------------|--------------|
| 1/2 (standard) | 50% | N/A | 0 | Self-comparison baseline |
| 6/10 | 60% | 20.0 | 6 | Median gap = 20 units |
| 7/10 | 70% | 40.0 | 6 | Median gap = 40 units (2x larger) |
| 3/4 | 75% | 50.0 | 6 | Median gap = 50 units (2.5x larger) |

### Consistency Across Traces

- All ratios showed identical disagreement counts and callback types across rep1, rep2, and rep3
- First disagreement occurred in early sequence (319-322 out of ~37k events)
- All disagreements were ssthresh mutations, not congestion state or RTT observations

### Interpretation

The results align with the expectation that gentler retention ratios (higher fraction retained) produce larger ssthresh values. The increasing median result deltas (20 → 40 → 50) are explained directly by the ratio arithmetic, not by integer-division rounding as originally stated here: delta ≈ (num/den - 1/2) * cwnd_at_loss, i.e. (0.6-0.5)*~200≈20, (0.7-0.5)*~200≈40, (0.75-0.5)*~200≈50 -- consistent with cwnd ≈ 200 at the shared divergence point (seq 319-322) across all three ratios. This confirms:

1. **Gentler ratios retain more cwnd on loss**, producing larger ssthresh values, scaled by the recorded cwnd at the loss event (not by integer-division rounding specifically -- the `//` floor only matters at the sub-1-unit level, far smaller than these deltas)
2. **Disagreement localization is precise**: all 6 events per trace are ssthresh callbacks, indicating the loss events affecting cwnd are in a narrow region of the trace

No bugs detected. The framework correctly isolates the ssthresh formula impact and maintains trace consistency across replays.

## Files Generated

- results.json: Full event-level results with delta stats
- results.csv: CSV export for analysis/plotting
- run.py: Reproducible script using all_decisions_core (same engine as sweep UI)
- manifest.json: Execution metadata
- summary.md: This report

## Conclusion

Reno retention-fraction sensitivity confirmed: gentler ratios produce deterministic, consistent disagreements localized to ssthresh events, with magnitude scaling proportional to cwnd at loss points.
