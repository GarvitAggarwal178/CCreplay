# CoVegas Replay Fidelity Validation

**Naming note:** this is `docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md`'s `REPORT_COVEGAS_REPLAY_FIDELITY.md`
(Part E — already a public-facing name, no rename needed; the pipeline itself instructs against
relying on an internal R-number here).

## Status: **PASS**

## Question

Can CCReplay faithfully self-replay the CoVegas implementation (the fixed/v4 build) required for
the historical regression case study, event-locally and statefully, under Replay ABI v2's
mode-dependent comparison schema?

## Reference strength (restated from D4)

> CoVegas self-replay validates CCReplay's ability to capture and reproduce the selected BPF
> implementation's callback inputs, semantic state, ordering, time dependencies, and private-state
> propagation. Because the live reference and userspace model derive from the same algorithm
> implementation, this oracle does not independently establish the correctness of the CoVegas
> algorithm itself.

## Method

1. **E1** — recorded the fixed/reference CoVegas (`bpf/covegas_wrapper.bpf.c`, algorithm logic
   copied near-verbatim from the read-only source per ADR-022) on the validated Gate-3-R2 topology,
   using the historically-relevant intermittent cross-traffic workload
   (`scripts/covegas_run_intermittent.sh`, adapted from
   `~/cn-spike/covegas/scripts/partC_run_intermittent.sh` — covegas continuous 120s on port 5201,
   real kernel `cubic` cross-traffic 20s-on/20s-off ×3 on port 5301, addendum item 7).
2. **E2** — event-local (Mode A) self-replay, `user/replay_e2.py`, mode-dependent comparison schema
   (ADR-023).
3. **E3** — stateful (Mode B) self-replay, `user/replay_e3.py`, private state initialized once
   (all-zero), the trace's own `init` event as transition #1.

## Pre-E1 fix (E4 anti-fitting log)

A loopback smoke test (diagnostic-only, not primary evidence) run before any Gate-3-R2 capture
found one mismatch, root-caused to a real recorder bug (category C): `fill_common()` and the
algorithm's own `now` computation each called `bpf_ktime_get_ns()` independently instead of sharing
one read. Fixed by sharing a single `now` value. Full account:
`data/covegas_replay_model_changes.md` Entry 1. Re-verified clean on loopback (462,114 events, 0
mismatches) before proceeding to any primary capture.

## Evidence

### E1 — primary trace

`raw/covegas_replay/primary/rep1.ccr`: 63,330 events, **zero drops**, gapless global sequence,
`clock_jiffies_stable=63,321` (9 ambiguous), `clock_ktime_ambiguous=63,330` (100% — expected, see
below), dominant connection 63,329/63,330 (99.998%, same ADR-016 stray-socket pattern as
Reno/CUBIC). Callback coverage: `init`×2, `cong_avoid`×31,348, `pkts_acked`×31,971, `ssthresh`×9,
`undo_cwnd`×0 (already separately `VALIDATED` via Part B's auxiliary trace — architecturally
identical `tcp_reno_undo_cwnd` delegation, zero CoVegas-specific logic). `ssthresh` firing 9 times
confirms real loss/competition occurred — the intermittent workload genuinely exercised
loss-adjacent behavior, not merely a clean transfer.

### E2 — event-local

| | value |
| --- | ---: |
| Events checked | 63,329 |
| Field comparisons | 1,658,687 |
| Mismatches | **0** |
| `jiffies` `CLOCK_STABLE` / mismatched | 63,320 / 0 |
| `jiffies` `CLOCK_AMBIGUOUS` / mismatched | 9 / 0 |
| `ktime` `CLOCK_STABLE` / mismatched | 0 / 0 |
| `ktime` `CLOCK_AMBIGUOUS` / mismatched | 63,329 / 0 |

**100.0000% exact semantic equality on every event**, across every callback type that fired,
including the full mode-dependent private-state schema (both union arms, gated by that event's own
recorded/computed mode independently per ADR-023).

### E3 — stateful

**First divergence = NONE across the entire 63,329-event sequence.** All 30 semantic private fields
(17 dedicated + 6 `delay`-arm + 7 `cubic`-arm) changed value at least once during the replayed
sequence (`fields_that_never_changed_in_any_trace = []`) — the mode-dependent union was genuinely
exercised in both directions (DELAY→COMPETE and COMPETE→DELAY transitions occurred, evidenced
directly by both arms' fields changing and by 9 real `ssthresh` invocations), not merely present in
the schema.

## Clock-transfer question: "Do not silently inherit CUBIC's clock exception. Prove whether it applies."

**It does not apply, empirically, on this trace.** Neither clock produced a single mismatch:
`jiffies`'s 9 `CLOCK_AMBIGUOUS` events all replayed exactly (0/9 mismatched, vs. CUBIC's ~9%
ambiguous-event mismatch rate); `ktime`'s 100% `CLOCK_AMBIGUOUS` rate — itself a real, measured, and
expected property of a nanosecond-resolution clock read twice with real work in between, not a bug
(`data/covegas_replay_model_changes.md`'s note) — also produced zero mismatches, because every
`bpf_ktime_get_ns()`-derived comparison CoVegas makes is against millisecond-scale thresholds (the
200ms probe hold, `RATE_SETTLE_MS`≥1000ms), where nanosecond-level before/after slop never crosses a
decision boundary in this trace. This is a genuinely different empirical outcome from CUBIC's (where
`tcp_jiffies32` ambiguity *did* cause real, characterized mismatches) — proven, not assumed, exactly
as required.

## E4 — anti-fitting log

`data/covegas_replay_model_changes.md` — one entry (the pre-E1 `bpf_ktime_get_ns()` sharing fix,
category C, found and fixed before any primary trace existed). No further entries were needed: E2's
first run against the real primary trace already showed zero mismatches.

## E5 — Fidelity verdict: **PASS**

> Faithful self-replay is demonstrated for the state/callback path required by the historical
> regression.

The historical regression (Part D1) concerns `handle_compete_mode`'s COMPETE-entry settle-latch —
exercised directly in this trace (mode transitions occurred, confirmed by both union arms changing
and 9 real `ssthresh` events). E2 is 100% exact and E3 shows first divergence = NONE across the
entire trace, covering that exact mechanism along with everything else in the manifest except
`undo_cwnd` (already separately validated). **Continuation to Part F is authorized without
qualification** — this is an unqualified PASS, not a PARTIAL requiring the "only rare/non-central
callbacks remain unvalidated" carve-out.

## Reproduction

```
python3 user/replay_e2.py raw/covegas_replay/primary/rep1.ccr raw/covegas_replay/primary/rep1.meta.json
python3 user/replay_e3.py raw/covegas_replay/primary/rep1.ccr raw/covegas_replay/primary/rep1.meta.json
```

## Relevant commits

`b0aac41` (ABI v2 design), `84efbe3` (recorder+parser+model), and this report's own commit (E1
primary trace, E2/E3 engines, this report).

Mandatory Phase-1 regression: reverified clean before this commit.
