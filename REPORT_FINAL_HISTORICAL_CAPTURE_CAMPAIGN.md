# Final Historical Capture Campaign + Differential Replay

## Outcome: **Outcome 1 — HISTORICAL DIFFERENTIAL CANDIDATE ACQUIRED**, Branch 10A prediction **matched**

Phases 7–11 of `docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md`. Precommit:
`data/final_historical_capture_campaign.md` (`8ce243a`). Candidate module + all predictions:
`data/a3_reconstructed_candidate_predictions.md` (`b8af8c1`) — committed BEFORE
`user/covegas_model_v3_latch.py` and BEFORE the first capture.

## Configuration (exactly as precommitted — no parameter changed)

`HOLD_MS=500`; CoVegas continuous 120 s (`iperf3 -C ccr_covegas -t 120`); real kernel `cubic`
cross-traffic 20 s ON / 20 s OFF ×3; validated Gate-3-R2 topology (10 Mbit/s htb + 250000 B bfifo,
40 ms base RTT, offloads off); Replay ABI v2, fixed/v4 recorder `build/ccr_recorder_covegas`.

## Campaign attempt log

Every attempt retained (`raw/covegas_campaign/rep{1..4}.ccr` + `.meta.json` + `_validation.json`;
per-attempt analysis in `data/historical_capture_campaign_results.json`).

| attempt | valid run | trace | valid | drops | seq gaps | dominant events | D→C transitions | H (ROBUST_OFF) | D (guard-fail) | H+D same episode | outcome |
| ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | `rep1.ccr` | yes | 0 | 0 | 65,484 | 3 (all ROBUST_ON) | 0 | 0 | 0 | NEITHER |
| 2 | 2 | `rep2.ccr` | yes | 0 | 0 | 56,120 | 7 (all ROBUST_ON) | 0 | 0 | 0 | NEITHER |
| 3 | 3 | `rep3.ccr` | yes | 0 | 0 | 60,620 | 3 (all ROBUST_ON) | 0 | 0 | 0 | NEITHER |
| 4 | 4 | `rep4.ccr` | yes | 0 | 0 | 68,424 | 5 (4 ROBUST_ON, **1 ROBUST_OFF**) | **1** | **1** | **1** | **H+D_SAME_EPISODE** |

```text
TOTAL ATTEMPTS:        4      (cap 12)
VALID RUNS:            4      (cap 9)
INVALID RUNS:          0
VALID BOUNDARIES:      12     (cap 27)
H EVENTS:              1
D EVENTS:              1
H+D SAME EPISODE:      1
STOP REASON:           H_AND_D_IN_SAME_EPISODE = YES  (Phase-7 stop rule -- never continue after first acquisition)
```

Per-episode guard ratios across the 4 attempts (all ON-period episodes): 0.097 – 0.711, all
guard-PASS. Attempt 2's episode `seq=1627` had the highest ON-period ratio observed (0.711) and
still passed. The **one OFF-period episode** (attempt 4, `seq=9533`) had ratio **0.9959** and
FAILED the guard — the same mechanism the archived historical positive showed (ratio ≈ 0.998).

## The acquired H+D episode (attempt 4, `raw/covegas_campaign/rep4.ccr`)

```text
trace sha256:  1aeabe0283e3f0a52936391dde18ec86093c524b4f90cad319b901ef067d65de
validate_run_v2: pass (drops 0, gapless, dominant 99.999%, manifest/schema/counters all OK)
cross-traffic ON periods (rel cubic_rep1_start): [(0.0, 20.69), (40.69, 61.35), (81.35, 102.01)]
event/schedule offset interval: Δ ∈ [-0.646, +0.252] s  (upper rigorous, lower loose -- as §7 of data/historical_a3_predicate_audit.md)
```

| | value |
| --- | --- |
| **Predicate H** — DELAY→COMPETE transition | `seq=9533`, t = 25.489 s, schedule window `[24.84, 25.74]` ⊂ OFF-period 1 `[20.69, 40.69]` → **ROBUST_OFF** |
| **Predicate D** — settle-latch guard evaluation | `seq=10421`, t = 26.486 s (**0.997 s after H**, ≈ `RATE_SETTLE_MS`), `dlv_rate_bps = 1,192,908`, `dlv_rate_max = 1,197,822`, **ratio 0.9959** ≥ 0.75 → **v4 guard FAILS** |
| settle-time gate | `elapsed_jiffies = 250 / 250` under **both** `clock_jiffies32_before` and `_after` → no bracket flip; exactly classifiable |
| `dlv_rate_compete` in the episode | never latched under v4 (v4 reverts) |
| same episode? | D's `episode_entry_seq = 9533` = H's seq → **YES** |

`D_COUNT = 1` for the whole trace ⇒ **`D_hist == D_first`** ⇒ Branch 10A.

## Phase 10A — historical differential replay

```text
python3 user/ccreplay_diff.py raw/covegas_campaign/rep4.ccr raw/covegas_campaign/rep4.meta.json \
  --reference user.covegas_model --candidate user.covegas_model_v3_latch
```

(stateful `ccreplay_diff.py`; the candidate `user/covegas_model_v3_latch.py` was built at `27fd795`
with positive + negative controls, all PASS.)

```text
n events (dominant):                 68,424
matched events before divergence:    10,420
RESULT:                              DIVERGENCE

========= FIRST DIVERGENCE =========
EVENT INDEX:  10420
SEQ:          10421          <-- D_hist  (== D_first)
CALLBACK:     cong_avoid
clock:        clock_jiffies32_before == _after (31324139)  -- CLOCK_STABLE, not clock-ambiguous
------------------------------------------------------------------
controller-owned state diff:
  post_snd_cwnd                   reference(v4) 37    candidate(v3) 65
  post_snd_cwnd_cnt               reference(v4) 576   candidate(v3) 578
private-state diff:
  priv_post_mode                  reference(v4) 0 (DELAY)   candidate(v3) 1 (COMPETE)
  priv_post_dlv_rate_compete      reference(v4) 0           candidate(v3) 1,192,908  (= the latched dlv_rate_bps)
  priv_post_detect_count          reference(v4) 0           candidate(v3) 4
  priv_post_recent_min_us         reference(v4) 4294967295  candidate(v3) 56911
  priv_post_last_compete_exit_jiffies, priv_post_delay_window_start_ack,
  priv_post_delay_cwnd_at_window_start, priv_post_delay_rtts_in_window,
  priv_post_delay_detect_hold_until   -- all differ (v4 ran revert_to_delay(); v3 ran cubic_growth())
====================================
```

### Precommitted prediction vs. result (`data/a3_reconstructed_candidate_predictions.md` §2.4)

| precommitted | observed | match |
| --- | --- | --- |
| `EXPECTED FIRST DIVERGENCE = D_hist` | `seq=10421` = D_hist | **yes** |
| `EXPECTED CALLBACK = cong_avoid` | `cong_avoid` | **yes** |
| state diff: `priv_post_mode` DELAY vs COMPETE | v4 DELAY (0), v3 COMPETE (1) | **yes** |
| state diff: `priv_post_dlv_rate_compete` 0 vs latched `dlv_rate_bps` | v4 0, v3 1,192,908 | **yes** |
| "plus every field `revert_to_delay()` writes vs. every field `cubic_growth()` writes" | `post_snd_cwnd`, `priv_post_detect_count`, `priv_post_delay_*`, … all differ | **yes** |

```text
HISTORICAL DIFFERENTIAL REPLAY = PASS
```

**Narrow sense only:**

> On the recorded fixed/v4 callback stream, reconstructed-v3 first differs from fixed/v4 at the
> precommitted Predicate-D event (`seq=10421`, `cong_avoid`) in the historical off-period COMPETE
> episode entered at `seq=9533`.

**Not claimed:** the candidate's alternate throughput; alternate RTT; a recreated 120 s network
outcome; that the first divergence caused every later performance symptom.

> CCReplay answers what a congestion-control implementation computes at a recorded callback
> boundary. It does not claim what network trajectory or performance that implementation would have
> produced.

## Optional historical suffix reproducer

`user/ccreplay_checkpoint.py` (extended for v2 like `ccreplay_diff.py`; N6 v1 regression unchanged):

```text
python3 user/ccreplay_checkpoint.py raw/covegas_campaign/rep4.ccr \
  --reference user.covegas_model --candidate user.covegas_model_v3_latch --interval 2000

FULL TRACE DIVERGENCE:   event_index=10420 seq=10421 callback=cong_avoid
CHECKPOINT:              event_index=10000 seq=10001
REPLAYED SUFFIX LENGTH:  420   (events 10001..10420, every one, in order)
REPRODUCED DIVERGENCE:   event_index=10420 seq=10421   -- identical
```

Reproducer, not minimization — events `[0, 10000]` are accounted for by the saved checkpoint state.

## Phase 11 — close

```text
HISTORICAL NETWORK ACQUISITION CLOSED SUCCESSFULLY
```

No further historical network campaign is authorized. Hard termination clauses
(`data/historical_case_freeze_decision.md`): no run 10, no > 12 total attempts, no longer trace, no
`HOLD_MS`/threshold change, no new historical workload, no post-hoc H/D redefinition.

## Probability note (permitted sensitivity statement only)

> If boundaries were IID with `p = 1/9` purely as a sensitivity assumption, the chance of observing
> at least one Predicate-H event in 27 boundaries would be `1 − (8/9)^27 ≈ 95.8%`.

This is not a formal power guarantee and does not describe same-episode H+D acquisition probability;
D has additional prerequisites and no H+D occurrence probability has been estimated. The campaign is
not "95%-powered". One H+D episode was acquired on valid run 4 (of a 9-run / 12-attempt cap).

## Source repo integrity

`~/cn-spike` at `022c2e2`, only the pre-existing baseline `M CLAUDE.md`; `~/cn-spike/covegas`,
`~/cn` untouched. Topology torn down after the campaign.
