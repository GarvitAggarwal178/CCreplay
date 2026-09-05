# Historical Trigger Validation (Part 8)

Verified BEFORE running the buggy-vs-fixed differential replay, per the addendum's explicit
instruction not to run the diff and report "no divergence" without first confirming the
regression-triggering condition actually occurred. Historical trigger: a spurious DELAY→COMPETE
mode transition during an off-period (no real competitor present) — the condition A3's guard is
intended to catch and revert, and the condition that, absent A3, permanently locks CoVegas into
COMPETE mode (`data/historical_regression_selection.md`).

Method: `data/audit_src/check_historical_trigger.py <rep_prefix>`, using real recorded mode
transitions (`priv_pre_mode` → `priv_post_mode` on actual trace events, not the model)
cross-referenced against that run's own real wall-clock on/off schedule. Each attempt is logged
below, oldest first, none overwritten.

## Attempt: `raw/covegas_replay/primary/rep1.ccr`

On-periods (seconds relative to the covegas connection's own first recorded event):
`[(0.33, 21.01), (41.02, 61.69), (81.71, 102.3)]`

### All mode transitions found

| seq | t (s) | phase | direction | callback |
|---|---|---|---|---|
| 418 | 1.49 | ON | DELAY->COMPETE | cong_avoid |
| 2656 | 11.77 | ON | COMPETE->DELAY | cong_avoid |
| 19995 | 42.23 | ON | DELAY->COMPETE | cong_avoid |
| 26096 | 61.27 | ON | COMPETE->DELAY | cong_avoid |
| 44100 | 84.29 | ON | DELAY->COMPETE | cong_avoid |
| 47885 | 99.69 | ON | COMPETE->DELAY | cong_avoid |

### Trigger classification for this attempt

**ABSENT** in this attempt. No DELAY->COMPETE transition occurred during an OFF period. Consistent
with `REPORT_COVEGAS_V4.md`'s own historical data — **correction, reconciliation pass:** the
source is 3 `HOLD_MS=500` runs × 3 off-period boundaries/run = **9 off-period boundaries** (not 9
runs), with 1 observed spurious re-entry (`REPORT_COVEGAS_V4.md`'s own B2 prediction-check table:
"spurious re-entries ... 1 (of 9 boundaries)"); 0 of 9 boundaries at `HOLD_MS=0` and 0 of 9
boundaries at `HOLD_MS=2000` (3 runs each) — a genuinely rare event even in the fixed build, not
evidence the trigger cannot occur.

---

## Attempt: `raw/covegas_replay/primary/rep2.ccr`

Real recorded mode transitions (`priv_pre_mode` -> `priv_post_mode` on actual trace events, not the model) cross-referenced against this run's own real wall-clock on/off schedule (`iperf3` timestamps for this exact rep, not hardcoded from a different run).

On-periods (seconds relative to the covegas connection's own first recorded event): [(0.8, 21.41), (41.42, 61.96), (81.96, 102.63)]

### All mode transitions found

| seq | t (s) | phase | direction | callback |
|---|---|---|---|---|
| 418 | 2.02 | ON | DELAY->COMPETE | cong_avoid |
| 1508 | 9.90 | ON | COMPETE->DELAY | cong_avoid |
| 19694 | 42.90 | ON | DELAY->COMPETE | cong_avoid |
| 24122 | 58.66 | ON | COMPETE->DELAY | cong_avoid |
| 41478 | 83.07 | ON | DELAY->COMPETE | cong_avoid |
| 47437 | 101.76 | ON | COMPETE->DELAY | cong_avoid |

### Trigger classification for this attempt

**ABSENT** in this attempt. No DELAY->COMPETE transition occurred during an OFF period.

---

## Overall conclusion: `TRIGGER NOT REPRODUCED`

**3 of 3 bounded attempts** (rep1, rep2, rep3 — a small bounded number, per the addendum's explicit
limit) show the historical trigger **absent**: every recorded mode transition across all three
attempts (6 per trace, 18 total) occurred during an ON period; zero occurred during an OFF period.
Scoped to the relevant off-period boundaries specifically (3 on-periods/run × 3 runs = **9
off-period boundaries**, mirroring `REPORT_COVEGAS_V4.md`'s own B2 boundary accounting): **3 runs,
9 off-period boundaries, 0 observed trigger events.**

This is not evidence something is wrong with the recorder, the topology, or the workload.
`REPORT_COVEGAS_V4.md`'s own historical data (`data/historical_regression_selection.md`) —
**correction, reconciliation pass:** the source is **3 `HOLD_MS=500` runs, 9 off-period
boundaries, 1 observed spurious re-entry** (not "1 of 9 runs" as an earlier version of this file
stated; `REPORT_COVEGAS_V4.md`'s own B2 prediction-check table reports this as "1 (of 9
boundaries)"). The full three-setting sweep (`HOLD_MS` = 0/500/2000, 3 runs each = 9 runs total, 3
boundaries/run = 27 boundaries total) shows 1 spurious re-entry pooled across all 27 boundaries —
that pooled 1/27 figure describes the full sweep, not the `HOLD_MS=500` configuration alone, and
must not be substituted for it.

Using only the selected configuration's own descriptive rate (1 event / 9 boundaries), a **rough
binomial sensitivity calculation under an independence assumption — not an estimated trigger
distribution** — for seeing 0 events in this campaign's own 9 boundaries:

```text
P(0 in 9) = (8/9)^9 ≈ 34.6%
```

So observing zero is plausible and unsurprising at this sample size — not being claimed as the
expected or most likely count. It is **not** "≈70%" — an earlier version of this file computed
`(8/9)^3 ≈ 70%` by treating the historical denominator as 3 runs instead of 9 boundaries, which
understated the sample size the
1-in-9 rate was actually drawn from. The result (trigger absent, not reproduced, not an anomaly)
is unchanged; only the supporting probability figure is corrected.

**Per the addendum's explicit instruction, this session does NOT:**

* run the buggy-vs-fixed differential replay against these traces and report "no divergence" (that
  would not test the regression at all, since the recorded event sequence never reaches the code
  path the A1-reverted "buggy" build differs on);
* attempt a fourth, fifth, ... retry to force a different outcome (that would cross into the
  "no hidden retries" territory `INSTRUCTIONS.md` §11 prohibits, and the addendum's own "small
  bounded number" framing was already honored at 3);
* manufacture a different trigger (e.g. adjusting `HOLD_MS` or other tunables specifically to make
  the spurious-entry condition easier to hit) — that would test a different, unvalidated workload
  configuration, not the historically-relevant one this case study committed to
  (`data/historical_regression_predictions.md`).

**Part F (historical buggy-vs-fixed differential case) is therefore not run this session.**
`REPORT_HISTORICAL_COVEGAS_REGRESSION.md` records this outcome as `INCOMPLETE` with this file named
as the exact blocker, per `INSTRUCTIONS.md` §2's phase-budget-expiry discipline applied to a
trigger-availability blocker instead of a wall-clock one.


## Attempt: `raw/covegas_replay/primary/rep3.ccr`

Real recorded mode transitions (`priv_pre_mode` -> `priv_post_mode` on actual trace events, not the model) cross-referenced against this run's own real wall-clock on/off schedule (`iperf3` timestamps for this exact rep, not hardcoded from a different run).

On-periods (seconds relative to the covegas connection's own first recorded event): [(0.6, 21.33), (41.34, 62.01), (82.02, 102.57)]

### All mode transitions found

| seq | t (s) | phase | direction | callback |
|---|---|---|---|---|
| 424 | 1.49 | ON | DELAY->COMPETE | cong_avoid |
| 2607 | 11.93 | ON | COMPETE->DELAY | cong_avoid |
| 21021 | 42.40 | ON | DELAY->COMPETE | cong_avoid |
| 26753 | 61.31 | ON | COMPETE->DELAY | cong_avoid |
| 44373 | 84.15 | ON | DELAY->COMPETE | cong_avoid |
| 48619 | 100.36 | ON | COMPETE->DELAY | cong_avoid |

### Trigger classification for this attempt

**ABSENT** in this attempt. No DELAY->COMPETE transition occurred during an OFF period.

---

