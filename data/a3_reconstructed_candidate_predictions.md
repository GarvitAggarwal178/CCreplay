# A3 Reconstructed-v3 Candidate — Precommitted Predictions

**Committed BEFORE `user/covegas_model_v3_latch.py` exists** (Phase 2 of
`docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md`). Git ordering is provable: this file's commit
precedes the `feat(a3): add reconstructed v3 settle-latch candidate` commit. Not rewritten after
results — results are appended to `data/a3_reconstructed_candidate_diff.md` /
`data/a3_guard_ratio_analysis.md` / the reports, not into this file.

`A3_TRACK_BLOCKED = NO` (Phase 1). `MINRTT_RETURN_ZERO_STATE_PRESERVATION = CONFIRMED`.

---

## 2.1 Existing recorded traces — fixed/v4 vs reconstructed-v3-A3

Predicate D is absent in all three current traces (`data/historical_a3_existing_trace_scan.md`,
rounds 1–3). Therefore:

```text
fixed-v4  vs  reconstructed-v3-A3   (stateful, existing ccreplay diff path)
  rep1 -> NO DIVERGENCE
  rep2 -> NO DIVERGENCE
  rep3 -> NO DIVERGENCE
```

This is **scanner / module / debugger cross-validation**. It is NOT: historical regression
reproduction; evidence the historical bug is absent; counterfactual network execution.

## 2.2 Synthetic module positive control

**Precommitted source event: `raw/covegas_replay/primary/rep1.ccr`, `seq = 608`** (first COMPETE
episode's settle-latch evaluation, t ≈ 2.485 s). Selected because it already reaches the settle-latch
guard with the v4 guard TRUE (`data/a3_settle_latch_events.json`, row 1).

Confirmed real prerequisites at this event (all from recorded PRE state + recorded clocks):

| prerequisite | value | holds? |
| --- | --- | --- |
| cwnd-limited | `tcp_is_cwnd_limited(...)` true | yes |
| `handle_minrtt_probe` returns 0 | `priv_pre_minrtt_probing = 0`, `now − last_minrtt_probe_ns < 10e9` | yes |
| `mode == COMPETE` | `priv_pre_mode = 1` | yes |
| `dlv_rate_compete == 0` | `priv_pre_dlv_rate_compete = 0` | yes |
| settle gate under **both** jiffies endpoints | `elapsed_jiffies = 250 / 250` `>= 250` | yes (no flip) |
| `dlv_rate_bps != 0` | `priv_pre_dlv_rate_bps = 231866` | yes |
| **original v4 guard TRUE** | `231866 < (566686 * 3) // 4 = 425014` | yes |

Synthetic construction: copy this event's full private PRE state; change **exactly one field**:

```text
synthetic_ca["dlv_rate_bps"] = synthetic_ca["dlv_rate_max"]        # 231866 -> 566686
```

Validity (from the pipeline): original `dlv_rate_bps != 0` ⟹ `dlv_rate_max > 0`; setting current
rate = recorded max preserves `dlv_rate_bps <= dlv_rate_max`; all other Predicate-D prerequisites
unchanged; the v4 guard is guaranteed FALSE because `dlv_rate_max >= (3/4)*dlv_rate_max`
(`566686 >= 425014`).

```text
ALL OTHER SYNTHETIC PRIVATE FIELDS CHANGED = NONE
```

**Precommitted expected outputs** (invoking `transition()` with this explicit private PRE state and
the otherwise-unchanged real event, once through fixed/v4 and once through reconstructed-v3):

```text
fixed-v4:
  post mode              = DELAY   (revert_to_delay)
  post dlv_rate_compete  = 0

reconstructed-v3:
  post mode              = COMPETE
  post dlv_rate_compete  = 566686  (= synthetic dlv_rate_bps)

SEMANTIC DIVERGENCE = YES
```

Other POST fields may also differ because the two branches execute `revert_to_delay()` vs.
`cubic_growth()`. This is MODULE-WIRING / CANDIDATE-SEMANTICS VALIDATION ONLY — not a real trace,
not historical evidence, not a new replay mode.

## 2.3 Future historical candidate criterion

A historical candidate requires **Predicate H AND Predicate D IN THE SAME COMPETE EPISODE**.

Do **not** assert `H ⟹ D`.

Allowed hypothesis (not a prediction of necessity):

> The archived positive suggests that a spurious off-period COMPETE episode can leave
> `dlv_rate_bps` close to `dlv_rate_max`, making failure of the v4 `< 0.75·max` latch guard more
> plausible. The archived positive had a guard-row ratio of approximately
> `1,194,436 / 1,197,147 ≈ 0.9977`. Whether a newly captured H episode also produces D is
> empirical.

The 9 existing (ON-period) settle-latch rows have ratios 0.24–0.41 — all well below 0.75, all
guard-PASS.

## 2.4 Future historical-diff prediction (precommitted NOW, before any capture)

Let `D_hist` = the Predicate-D event in the same COMPETE episode as the qualifying H;
`D_first` = the earliest Predicate-D event anywhere in the trace.

**If a qualifying H+D trace is obtained AND `D_hist == D_first`:**

```text
fixed-v4  vs  reconstructed-v3   (stateful ccreplay diff)
EXPECTED FIRST DIVERGENCE = D_hist   (the historical same-episode Predicate-D cong_avoid event)
EXPECTED CALLBACK         = cong_avoid
EXPECTED STATE DIFFERENCE = priv_post_mode (DELAY vs COMPETE), priv_post_dlv_rate_compete
                            (0 vs the latched dlv_rate_bps), plus every field revert_to_delay()
                            writes vs. every field cubic_growth() writes
```

**If `D_first < D_hist`:** do NOT claim full-trace first divergence localizes the historical
episode. A full diff may be reported only as `AUXILIARY FULL-TRACE A3 DIFFERENCE`, not
`HISTORICAL-FIRST-DIVERGENCE LOCALIZATION`.

## 2.5 Claim boundary (verbatim, all downstream docs)

> CCReplay answers what a congestion-control implementation computes at a recorded callback
> boundary. It does not claim what network trajectory or performance that implementation would have
> produced.
