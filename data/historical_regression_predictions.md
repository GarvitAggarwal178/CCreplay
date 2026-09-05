# Historical Regression Predictions (D2)

Committed **before** any buggy-vs-fixed differential replay is run, per D2's explicit instruction
and addendum item 9's language constraints. Not rewritten after results — a separate RESULTS
section is appended to `REPORT_HISTORICAL_COVEGAS_REGRESSION.md` instead.

## Historical symptom

CoVegas v3: permanent COMPETE-mode capture under intermittent cross-traffic — spuriously re-enters
COMPETE 2–11s into an off-period (no competitor present) and never returns to DELAY for the rest of
the trace, in 9/9 historical runs (`data/historical_regression_selection.md`,
`REPORT_COVEGAS_V3.md` Part C).

## Known buggy/fixed code difference

`handle_compete_mode()`'s settle-latch: v3 (buggy build, this session's isolated reconstruction)
latches `dlv_rate_compete` to the current smoothed rate unconditionally once `RATE_SETTLE_MS` has
elapsed since COMPETE entry; v4 (fixed, real committed source) gates that latch on
`dlv_rate_bps < (dlv_rate_max * 3) / 4`, reverting to DELAY immediately instead of latching if the
guard fails.

## Expected affected mechanism

The COMPETE-entry settle-latch decision inside `handle_compete_mode`, evaluated once per
`cong_avoid` invocation while `mode == COMPETE` and `dlv_rate_compete == 0` (i.e. once settle time
has elapsed since the most recent DELAY→COMPETE transition).

## Expected affected controller-private state class

`dlv_rate_compete` (the field the guard directly gates) and, as a downstream structural
consequence, `mode` (buggy build should show `mode` remaining `COMPETE` well past where the fixed
build reverts to `DELAY`) and `detect_count`/`u.delay.*` fields (which only update while `mode ==
DELAY`, so they should diverge in lockstep with `mode` once the two builds' mode histories part
ways). `dlv_rate_max` itself is expected to remain in agreement between builds up to the point of
first divergence (it decays on the same minrtt-probe cadence in both, independent of the guard).

## Expected callback class/region

`cong_avoid` (the callback that dispatches to `handle_compete_mode`/`handle_delay_mode`). The guard
condition itself is not evaluated in any other callback.

## Expected workload/trigger requirement

The intermittent cross-traffic workload (addendum item 7: CUBIC cross-traffic 20s ON / 20s OFF ×3,
`partC_run_intermittent.sh` or its provenance-preserving copy) is required — a solo trace has no
off-period in which a spurious COMPETE re-entry could occur, and would very likely show first
divergence = NONE regardless of which build is "buggy," proving nothing about this specific
mechanism. This will be verified as PRESENT in the recorded trace before any buggy-vs-fixed diff is
run (Part 8 / `data/historical_trigger_validation.md`), not assumed.

## Exact first event

**UNKNOWN — CCReplay must discover it.** Historical evidence (the v4 telemetry example, "spurious
COMPETE entry at t=65.51s... reverted at t=66.51s") describes one specific *historical* occurrence
under the historical harness's own timing, workload seed, and network conditions — not a prediction
for this session's new recording, which will have its own timing. No specific event sequence
number or wall-clock offset is frozen here.

## Exact first divergent semantic field

**UNKNOWN unless independently established by historical evidence.** The expected *state class*
above (`dlv_rate_compete`, then `mode`) is a reasoned hypothesis from the source/report evidence,
not a certainty — the two builds could plausibly first diverge on `dlv_rate_compete` alone (buggy
build latches a nonzero value; fixed build reverts, leaving it 0) on the very settle-check event, or
the divergence could first become externally visible on a later, structurally downstream field
(e.g. `mode`, or a POST-state field of a subsequent event) depending on exactly how CCReplay's
comparison schema is defined for this callback. The precise first differing field is left for
CCReplay to discover, not frozen here as a certainty.

## What is NOT predicted (per addendum item 9)

Exact first callback occurrence count, exact sequence number, exact first divergent field value —
all left `UNKNOWN`, to preserve the value of the case study as a genuine discovery rather than a
confirmation of an already-known answer.

---

## RESULTS (appended — predictions above NOT rewritten)

The Final Integrated Session's capped acquisition campaign
(`REPORT_FINAL_HISTORICAL_CAPTURE_CAMPAIGN.md`) obtained a qualifying trace on valid run 4:
`raw/covegas_campaign/rep4.ccr`. `fixed/v4` vs `reconstructed-v3` differential replay
(`user/ccreplay_diff.py`, stateful) result:

| predicted (above / `a3_reconstructed_candidate_predictions.md` §2.4) | observed | verdict |
| --- | --- | --- |
| affected mechanism: `handle_compete_mode` settle-latch decision, once per `cong_avoid` while `mode==COMPETE` and `dlv_rate_compete==0` after settle time | first divergence at `seq=10421`, `cong_avoid`, exactly that decision | **matched** |
| affected callback: `cong_avoid` | `cong_avoid` | **matched** |
| affected state class: `dlv_rate_compete`, then `mode` (+ downstream `detect_count` / `u.delay.*`) | `priv_post_dlv_rate_compete` (0 vs 1,192,908), `priv_post_mode` (DELAY vs COMPETE), `priv_post_detect_count`, `priv_post_delay_*` all differ | **matched** |
| workload/trigger: intermittent cross-traffic, spurious off-period COMPETE re-entry — verified present before the diff | Predicate H at `seq=9533` (`ROBUST_OFF`), same episode as the Predicate-D event | **matched** |
| exact first event: UNKNOWN — CCReplay to discover | `seq=10421` (event index 10420); 10,420 events matched before it | **discovered** |
| exact first divergent field: UNKNOWN | the divergence is simultaneous across `priv_post_mode`, `priv_post_dlv_rate_compete`, `post_snd_cwnd`, and the `revert_to_delay`-vs-`cubic_growth` field set (v4 reverts + returns; v3 latches + grows) | **discovered** — not a single field; the whole branch outcome differs on that one event |

Narrow-sense **PASS**: *on the recorded fixed/v4 callback stream, reconstructed-v3 first differs
from fixed/v4 at the Predicate-D event in the historical off-period COMPETE episode.* No claim about
alternate throughput / RTT / queue state or a recreated network outcome.
`reconstructed-v3` is v4's committed source with exactly the A3 guard reverted
(`data/a3_reconstructed_candidate_diff.md`), a documented reconstruction, not original v3 source.
