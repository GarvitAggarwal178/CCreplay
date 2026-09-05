# Phase 5 — A3 Guard-Ratio Analysis

Offline, existing data only. Source: `data/a3_settle_latch_events.json`
(`data/audit_src/a3_settle_latch_events.py`). The v4 A3 guard is
`dlv_rate_bps < (dlv_rate_max * 3) / 4`, i.e. `ratio = dlv_rate_bps / dlv_rate_max` vs. threshold
`0.75`.

## All 9 current eligible settle-latch guard evaluations

Every one is the single settle-latch resolution of a COMPETE episode; all 9 episodes were entered
during a cross-traffic ON period (`data/historical_a3_existing_trace_scan.md`, all DELAY→COMPETE
transitions `ROBUST_ON`).

| trace | episode | seq | t (s) | phase | dlv_rate_bps | dlv_rate_max | ratio | threshold | guard |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |
| rep1 | 1 | 608 | 2.485 | ON | 231,866 | 566,686 | 0.4092 | 0.75 | **PASS** |
| rep1 | 2 | 20,245 | 43.229 | ON | 350,224 | 1,120,903 | 0.3124 | 0.75 | **PASS** |
| rep1 | 3 | 44,328 | 85.285 | ON | 269,271 | 1,121,137 | 0.2402 | 0.75 | **PASS** |
| rep2 | 1 | 544 | 3.055 | ON | 142,182 | 508,445 | 0.2796 | 0.75 | **PASS** |
| rep2 | 2 | 19,940 | 43.901 | ON | 319,698 | 1,121,180 | 0.2851 | 0.75 | **PASS** |
| rep2 | 3 | 41,744 | 84.075 | ON | 356,895 | 1,196,009 | 0.2984 | 0.75 | **PASS** |
| rep3 | 1 | 612 | 2.486 | ON | 231,544 | 567,686 | 0.4079 | 0.75 | **PASS** |
| rep3 | 2 | 21,247 | 43.403 | ON | 336,982 | 1,120,942 | 0.3006 | 0.75 | **PASS** |
| rep3 | 3 | 44,607 | 85.169 | ON | 282,170 | 1,122,140 | 0.2515 | 0.75 | **PASS** |

**Ratio range: 0.2402 – 0.4092.** All 9 pass the v4 guard by a wide margin (all well below 0.75) —
the settle-time delivery rate is < ~41% of the recently observed maximum in every case, consistent
with a genuine competitor depressing CoVegas's throughput.

## Archived historical positive (read-only `~/cn-spike/covegas/raw/partC_v4/Ph500_B5x_rep2_ringbuf.csv`)

| episode | t (s) | phase | dlv_rate_bps | dlv_rate_max | ratio | threshold | guard |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| spurious off-period entry (t≈65.51 s → revert t≈66.51 s) | 66.512 | OFF | 1,194,436 | 1,197,147 | **0.9977** | 0.75 | **FAIL** |

`dlv_rate_compete` was never latched in that episode (max 0); the revert fired 0.998 s after entry
(≈ `RATE_SETTLE_MS`). See `data/historical_a3_archive_analysis.json`.

## Allowed interpretation

> All nine existing eligible evaluations occurred in ON-period episodes and passed the v4 guard.
> The archived off-period positive had a guard-row ratio ≈ 0.998 and therefore failed the guard.
> This is mechanism-consistent empirical evidence, not proof that workload phase causally
> determines the ratio.

**Do not claim H deterministically implies D.** The 9 ON-period ratios and the 1 OFF-period ratio
are separated by a large gap (0.41 vs 0.998), which is *consistent with* the A3 mechanism's design
rationale (a spurious off-period COMPETE entry leaves the settle-time rate near solo capacity), but
n=1 on the OFF side and the ratio is not a recorded controller decision variable in its own right.
