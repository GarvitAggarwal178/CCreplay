# Historical CoVegas A3 Case — Close Decision

## Status: **HISTORICAL NETWORK ACQUISITION CLOSED SUCCESSFULLY**

Phase 11 of `docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md`. Branch 10A succeeded cleanly.

## What was achieved

- **Outcome 1** — a Replay ABI v2 CoVegas trace (`raw/covegas_campaign/rep4.ccr`, valid run 4 of a
  capped 9-run / 12-attempt campaign) containing **Predicate H and Predicate D in the same COMPETE
  episode**: a spurious off-period DELAY→COMPETE entry (`seq=9533`, `ROBUST_OFF`) followed ≈ 1 s
  later by a settle-latch guard evaluation (`seq=10421`, ratio 0.9959) that the v4 A3 guard fails.
- **Branch 10A** — `D_hist == D_first`. `fixed/v4` vs `reconstructed-v3` (`ccreplay_diff.py`,
  stateful) first diverges at exactly `seq=10421` (`cong_avoid`); the state difference is
  `priv_post_mode` DELAY↔COMPETE, `priv_post_dlv_rate_compete` 0↔latched, and the full
  `revert_to_delay()`-vs-`cubic_growth()` field set — matching the precommitted prediction
  (`data/a3_reconstructed_candidate_predictions.md` §2.4, commit `b8af8c1`) in every particular.
- The divergent event is `CLOCK_STABLE` (`clock_jiffies32_before == _after`); the settle-time gate
  is `250/250` under both jiffies bracket endpoints — the classification carries no clock ambiguity.

Full evidence: `REPORT_FINAL_HISTORICAL_CAPTURE_CAMPAIGN.md`.

## Verdict wording (narrow, verbatim)

> On the recorded fixed/v4 callback stream, reconstructed-v3 first differs from fixed/v4 at the
> precommitted Predicate-D event (`seq=10421`, `cong_avoid`) in the historical off-period COMPETE
> episode entered at `seq=9533`.

Not claimed: alternate throughput / RTT / queue state; a recreated 120 s network outcome; that the
first divergence caused every later performance symptom.

> CCReplay answers what a congestion-control implementation computes at a recorded callback
> boundary. It does not claim what network trajectory or performance that implementation would have
> produced.

`reconstructed-v3` is a **documented reconstruction** (v4's committed source with exactly the A3
guard reverted, `data/a3_reconstructed_candidate_diff.md`), not original committed v3 source —
v3's `src/covegas.bpf.c` was never committed to `~/cn-spike/covegas`
(`data/historical_regression_selection.md`).

## Hard termination

No further historical network campaign is authorized. Because Branch 10A succeeded, more captures
are no longer useful.

```text
NO run 10
NO > 12 total attempts   (4 were used)
NO longer trace
NO HOLD_MS change
NO threshold change
NO new historical workload
NO post-hoc H/D redefinition
```

## Formal verdict change

```text
Historical CoVegas A3:   INCOMPLETE  ->  CLOSED SUCCESSFULLY (narrow-sense differential-replay PASS)
```

CUBIC R3 remains **PARTIAL**. CoVegas v2 self-replay remains **PASS**. Reno v0 remains **PASS**.
