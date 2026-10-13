# CUBIC Parameter Sensitivity Sweep Results

## Zero-Point Sanity Check: **ALL PASSED**

All documented default parameters showed n_disagree=0 across all three CUBIC traces, confirming the sweep engine correctly validates self-replay against identical parameter configurations:
- **BETA (default=717)**: n_disagree=0 for rep1, rep2, rep3 ✓
- **BIC_SCALE (default=41)**: n_disagree=0 for rep1, rep2, rep3 ✓
- **FAST_CONVERGENCE (default=1)**: n_disagree=0 for rep1, rep2, rep3 ✓
- **TCP_FRIENDLINESS (default=1)**: n_disagree=0 for rep1, rep2, rep3 ✓
- **HYSTART (default=1)**: n_disagree=0 for rep1, rep2, rep3 ✓

## Sweep 1: BETA Multiplicative Decrease Factor

**Parameter space**: values [512, 614, 717, 819, 921] with default=717

**Trend**: The sweep reveals a V-shaped disagreement profile centered at the default value, but it is
**not symmetric**: BETA=512 (205 below default) shows ~2.24% disagreement, while BETA=921 (204 above
default -- almost the same distance) shows only ~0.28%, about 8x smaller. Moving below the default by
a given distance disagrees far more than moving above it by the same distance. As BETA increases
toward the default of 717, disagreement rate decreases monotonically to zero (n_disagree=0 for all
traces); beyond the default it increases again but stays much smaller than the corresponding below-
default value. The median delta in controller-computed cwnd reduction (result_median_delta) ranges
from -40.0 at BETA=512 to +40.0 at BETA=921, confirming expected reduction-factor sensitivity. All
disagreement first appears after event 500+, suggesting the parameter affects steady-state algorithm
behavior rather than initialization.

## Sweep 2: BIC_SCALE Scaling Factor

**Parameter space**: values [10, 20, 41, 82, 164] with default=41

**Trend**: Like BETA, this is a V-shaped profile centered at the default, not a monotonic increase
across the whole swept range. Values 10 and 20 (both below the default of 41) exhibit similar
disagreement rates (~2.89%) with ~2273-2277 events per trace. The default value of 41 achieves zero
disagreement (n_disagree=0 for all traces). Values 82 and 164 (above default) show disagreement rates
of ~3.20-3.25% with ~2516-2561 events -- monotonically increasing only on this above-default side, and
somewhat higher than the below-default side (~2.89% vs ~3.2-3.25%), the opposite asymmetry from BETA.
The post_snd_cwnd_median_delta is uniformly 1.0 for non-default values, indicating consistent cwnd
increment differences. All disagreements appear early (first_disagreement_seq around 2028-2035 across
all sweeps), suggesting BIC_SCALE primarily affects the congestion-avoidance increment calculation
applied throughout the connection lifetime.

## Sweep 3: FAST_CONVERGENCE Boolean Enable Flag

**Parameter space**: values [0, 1] with default=1 (enabled)

**Trend**: Disabling fast convergence (value=0) produces minimal but measurable disagreement (~0.0000889 disagreement rate) across all three traces. This low disagreement rate suggests the fast-convergence path is rarely exercised in the recorded traces or affects only a small number of callback decisions. With the default enabled (value=1), all traces achieve perfect n_disagree=0. The early first_disagreement_seq value of 5105-5109 indicates the parameter effect manifests mid-connection after substantial cumulative behavior.

## Sweep 4: TCP_FRIENDLINESS Boolean Enable Flag

**Parameter space**: values [0, 1] with default=1 (enabled)

**Trend**: Disabling TCP friendliness (value=0) produces measurable disagreement (~0.00267 disagreement rate) across all three traces, with approximately 209-210 events showing disagreement. This higher disagreement rate compared to FAST_CONVERGENCE suggests the TCP-friendliness check is invoked more frequently in the replay traces. With the default enabled (value=1), all traces achieve perfect n_disagree=0. The first_disagreement_seq around 742-752 is **earlier** than FAST_CONVERGENCE's (5105-5109) -- not later, as originally stated here -- indicating TCP_FRIENDLINESS's effect manifests earlier in the connection (around the same point as BETA=819's divergence, seq 742/752), while FAST_CONVERGENCE's effect only appears much later (seq ~5105+), consistent with it depending on a specific earlier event (e.g. a loss/epoch boundary) rather than being active from early steady-state.

## Sweep 5: HYSTART Boolean Enable Flag

**Parameter space**: values [0, 1] with default=1 (enabled)

**Trend**: Disabling HYSTART (value=0) produces very low disagreement (~0.0005 disagreement rate) comparable to FAST_CONVERGENCE, with 39-49 events showing disagreement across the three traces. This suggests HYSTART is similarly rarely triggered in the recorded connection phases. With the default enabled (value=1), all traces achieve perfect n_disagree=0. The first_disagreement_seq begins at 0, indicating the parameter affects decisions from the earliest callback boundary, likely during slow-start initialization.

## Summary

The parameter sensitivity sweep demonstrates that CCReplay's sweep engine correctly identifies the zero-disagreement point at documented default parameters for all five CUBIC algorithm parameters. Non-default values produce varying disagreement profiles:
- **Continuous parameters** (BETA, BIC_SCALE) both show a V-shaped profile centered at the default, but each is asymmetric in the opposite direction: BETA disagrees ~8x more when moved below default than above by a comparable distance; BIC_SCALE disagrees somewhat *more* above default than below.
- **Boolean parameters** (FAST_CONVERGENCE, TCP_FRIENDLINESS, HYSTART) show small but measurable disagreement when disabled, with TCP_FRIENDLINESS producing the largest effect (~0.27% disagreement), followed by HYSTART (~0.05%) and FAST_CONVERGENCE (~0.0089%) -- both corrected here from the ~100x-too-small percentages ("0.00009%"/"0.0005%") originally written, which forgot to convert the raw fraction to a percent.

The consistency of this behavior across all three trace replicates (rep1, rep2, rep3) confirms reproducible parameter sensitivity and validates the replay oracle's ability to detect implementation-level differences arising from parameter variations.
