# Historical CoVegas Regression Case Study

## Status: **INCOMPLETE**

**Blocker:** `TRIGGER NOT REPRODUCED` — see `data/historical_trigger_validation.md`. The historical
regression's trigger (a spurious `DELAY→COMPETE` mode transition during an off-period) did not
occur in any of 3 bounded primary-workload attempts, so the buggy-vs-fixed differential replay
(Part F) was never run — running it and reporting "no divergence" on a trace that never reaches the
code path in question would not test the regression, and the addendum explicitly forbids doing so.

This is a phase-blocker `INCOMPLETE`, not a `FAIL`: nothing about CCReplay, the CoVegas Replay
Contract, or the recorder failed. `REPORT_COVEGAS_REPLAY_FIDELITY.md`'s PASS verdict is unaffected
— self-replay fidelity was fully demonstrated (Part E) before this blocker was even reached; the
blocker is specifically about reproducing a *rare, historically-documented-as-rare* network
condition on demand within a bounded number of attempts, not about any capability CCReplay lacks.

## What was completed

1. **D1–D4** — selected and fully documented the v3/v4 "A3 latch-guard" regression, precommitted
   predictions, audited the Replay Contract (`data/historical_regression_selection.md`,
   `data/historical_regression_predictions.md`, `data/covegas_replay_capability_audit.md`).
2. **Part E** — built the CoVegas recorder/parser/model from scratch (no kernel-native reference
   exists, ADR-022), captured a primary trace on the intermittent workload, and demonstrated
   **PASS**-verdict self-replay fidelity: E2 zero mismatches (63,329 events, 1,658,687 field
   comparisons at Part E's own initial single-trace capture), E3 first divergence = NONE across the
   entire sequence, all 30 private fields (including both union arms) demonstrated to change
   nontrivially. **Current combined evidence (Part E + Part 8's rep2/rep3 fold-in): 190,277 events,
   4,982,990 field comparisons, still 0 mismatches, across all 3 traces** — see
   `REPORT_COVEGAS_REPLAY_FIDELITY.md` for the authoritative current figures; the verdict is
   unchanged (PASS) throughout.
3. **Part 8 (addendum) — trigger verification** — attempted 3 bounded reps of the historically-
   relevant intermittent cross-traffic workload specifically to verify the regression trigger's
   presence before diffing. All 3 clean captures (zero drops each), all 3 showing zero spurious
   off-period mode transitions. `data/historical_trigger_validation.md`.

## Why this outcome, not a workaround

`REPORT_COVEGAS_V4.md`'s own historical data (`data/historical_regression_selection.md`) already
disclosed that a spurious off-period re-entry occurred at `HOLD_MS=500` (the default, and the only
configuration this session's recorder builds). **Correction, reconciliation pass:** the exact
denominator is **3 runs, 9 off-period boundaries** (`REPORT_COVEGAS_V4.md`'s own B2
prediction-check table: "spurious re-entries ... 1 (of 9 boundaries)"), not "1 of 9 runs" as an
earlier version of this report stated. This session's own new trigger campaign has the identical
shape: **3 runs, 9 off-period boundaries, 0 observed trigger events** — see
`data/historical_trigger_validation.md` for the corrected accounting.

Under the rough independence model using the historical 1/9-per-boundary descriptive rate,
`P(0 in 9) = (8/9)^9 ≈ 34.6%` (not the previously-stated ≈70%, which incorrectly used 3 as the
trial count instead of 9; and this is a rough binomial sensitivity figure under an independence
assumption, not an estimated trigger distribution). So observing zero is plausible and unsurprising
at this sample size — it is not evidence of a problem, and it is not being claimed as the expected
or most likely count. The correction narrows the supporting number, not the conclusion. Reproducing
the trigger reliably would require either
substantially more attempts (bounded-attempts discipline explicitly caps this) or deviating from the
historically-relevant workload configuration (explicitly forbidden — that would test a different,
unvalidated scenario, undermining the entire premise of using a real historical regression as the
case study).

## What Part F would have required, unblocked

Given the trigger, `user/ccreplay_diff.py` (N4) already generalizes to any two model modules
implementing the shared `transition()`/`comparison_fields()` interface — the "buggy" CoVegas variant
(`covegas_model.py` with the A3 guard reverted to v3's unconditional latch, per
`data/historical_regression_selection.md`'s exact, disclosed isolation) was designed but not yet
implemented as a separate module, since there was no reproduced trigger to run it against. This
remains straightforward follow-up work once a trigger-positive trace exists (either from a future
attempt, or a longer/multi-rep capture campaign outside this session's budget).

## Predictions status

`data/historical_regression_predictions.md` remains committed, unresolved, and not rewritten — the
predictions were about what *would* happen if the trigger occurred and the diff ran; since neither
happened, there are no results to append, and none are fabricated.

## Source repo integrity

`~/cn-spike` verified unmodified throughout Part D/E/8 (read-only source inspection and one-time
algorithm-logic copy into CCReplay, both disclosed in `docs/PROVENANCE.md`).

## Relevant commits

`b0aac41`, `84efbe3`, `9e4f155` (Part D/E), and this report's own commit (trigger-verification
attempts, `data/historical_trigger_validation.md`, this report).

Mandatory Phase-1/CUBIC/CoVegas regression: reverified clean before this commit.
