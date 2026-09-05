# Historical CoVegas A3 Case — Close Decision

## Formal verdict: **Historical CoVegas A3 reconstructed-regression case study = PASS**

## Status: **HISTORICAL NETWORK ACQUISITION CLOSED SUCCESSFULLY**

Phase 11 of `docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md`, then post-success consistency closure.
Branch 10A succeeded cleanly.

### PASS means, precisely

> On a newly acquired Replay-ABI-v2 fixed/v4 callback stream containing the predeclared historical
> off-period A3 condition, the precommitted reconstructed-v3 candidate first diverged from fixed/v4
> at the precommitted same-episode Predicate-D callback.

Concretely: `raw/covegas_campaign/rep4.ccr` (sha256
`1aeabe0283e3f0a52936391dde18ec86093c524b4f90cad319b901ef067d65de`), Predicate H `seq=9533`
(off-period DELAY→COMPETE), Predicate D `seq=10421` (`cong_avoid`, same episode, `D_hist == D_first`);
`fixed/v4` vs `reconstructed-v3` matched 10,420 events then first diverged at `seq=10421` — matching
the precommit `data/a3_reconstructed_candidate_predictions.md` §2.4 (`b8af8c1`) exactly.

### Mandatory caveats (attach wherever this PASS is stated)

- **Candidate provenance:** the buggy candidate is a *documented reconstruction* of v3's A3
  settle-latch behaviour from committed v4 source plus historical project evidence. Original
  committed v3 source is unavailable (`data/historical_regression_selection.md`). This is a
  **reconstructed-regression case study, not replay of literal original-v3 source.**
- **Debugger-path provenance:** Replay-ABI-v2 support in the differential debugger was implemented
  during the same integrated session. Its correctness is supported by precommitted positive/negative
  controls, subsequent automated regression coverage (`tests/test_ccreplay_diff_v2.py`, +7 tests),
  and the precommitted historical first-divergence result.

### Verdicts stay separate — do NOT merge the last two

```text
Reno v0 replay fidelity:                              PASS
CUBIC v1 R3 replay fidelity:                          PARTIAL
CoVegas v2 self-replay fidelity:                      PASS
Historical CoVegas A3 reconstructed-regression case study:  PASS
```

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
Historical CoVegas A3 reconstructed-regression case study:
  INCOMPLETE (trigger not reproduced)  ->  PASS
  (per the precise definition above; separate gate from CoVegas v2 self-replay fidelity)
```

CUBIC R3 remains **PARTIAL**. CoVegas v2 self-replay fidelity remains **PASS**. Reno v0 remains
**PASS**. These four gates are reported separately; the historical case-study PASS is **not** the
CoVegas self-replay PASS and must not be merged with it.
