# Reconstructed-v3 A3 Candidate — Exact Semantic Patch + Controls

Module: `user/covegas_model_v3_latch.py` (Phase 3). Predictions precommitted in
`data/a3_reconstructed_candidate_predictions.md` (commit `b8af8c1`), BEFORE this module existed.

## Exact semantic patch

The candidate is `user/covegas_model.py` (fixed/v4) with **exactly one** behaviour changed: the A3
settle-latch guard in `handle_compete_mode`.

```diff
  def handle_compete_mode(ca, pre, acked, jiffies_now):
      ca = dict(ca)
      cwnd = pre["snd_cwnd"]
      cwnd_cnt = pre["snd_cwnd_cnt"]

      if ca["dlv_rate_compete"] == 0:
          elapsed_jiffies = u32(u32(jiffies_now) - ca["compete_enter_jiffies"])
          if elapsed_jiffies >= (RATE_SETTLE_MS * CONFIG_HZ) // 1000 and ca["dlv_rate_bps"]:
-             if ca["dlv_rate_bps"] < (ca["dlv_rate_max"] * 3) // 4:            # A3 guard
-                 ca["dlv_rate_compete"] = ca["dlv_rate_bps"]
-             else:
-                 cwnd, ca = revert_to_delay(ca, pre, jiffies_now)             # v4/A3 back-out
-                 return cwnd, cwnd_cnt, ca
+             ca["dlv_rate_compete"] = ca["dlv_rate_bps"]                       # v3: unconditional latch
      elif ca["dlv_rate_bps"] > (RATE_JUMP_NUM * ca["dlv_rate_compete"]) // RATE_JUMP_DEN:
          cwnd, ca = revert_to_delay(ca, pre, jiffies_now)                     # rate-jump revert -- UNCHANGED
          return cwnd, cwnd_cnt, ca

      cwnd2, cwnd_cnt2, ca = cubic_growth(ca, pre, acked, jiffies_now)
      return cwnd2, cwnd_cnt2, ca
```

- **A1** (targeted cwnd on revert) and **A2** (detection hold) live in `revert_to_delay()` /
  `handle_delay_mode()` and are **unchanged** (imported verbatim from `user.covegas_model`).
- **No changed constants.** `RATE_SETTLE_MS`, `CONFIG_HZ`, `RATE_JUMP_NUM/DEN`, thresholds — all
  imported unchanged.
- **No parser / recorder / trace-format change.**
- Everything except `handle_compete_mode` (init / cong_avoid dispatch / ssthresh / undo_cwnd /
  pkts_acked / cubic_growth / bictcp_update / update_dlv_rate / the ADR-023 comparison schema) is
  imported unchanged and used verbatim. `transition()` delegates to
  `user.covegas_model.transition` with `handle_compete_mode` locally swapped for the duration of
  the call (reversible; the base module is never persistently modified) — deliberately not a copy
  of the ~115-line base `transition()`.

## Mechanical verification (`data/audit_src/a3_candidate_controls.py` → `data/a3_candidate_controls.json`)

Normalised source comparison of the two `handle_compete_mode` bodies (docstrings / comments /
blank lines removed):

```text
lines present in v4 but not v3:
  if ca["dlv_rate_bps"] < (ca["dlv_rate_max"] * 3) // 4:
  else:
  cwnd, ca = revert_to_delay(ca, pre, jiffies_now)
  return cwnd, cwnd_cnt, ca
lines present in v3 but not v4:
  (none -- the unconditional-latch assignment ca["dlv_rate_compete"] = ca["dlv_rate_bps"]
   is the same statement, previously the guard's `if` body)

guard_is_the_only_difference:   true
transition_delegates_to_base:   true
ONLY_A3_SEMANTIC_DIFFERENCE  =  YES
```

## Phase 4.1 — synthetic positive control

Precommitted event: `raw/covegas_replay/primary/rep1.ccr` `seq=608` (first COMPETE episode
settle-latch; v4 guard TRUE). Copy private PRE state; set `dlv_rate_bps = dlv_rate_max`
(231866 → 566686); invoke `v4.transition` and `v3.transition` with that explicit state and the
otherwise-unchanged real event.

```text
source event                              raw/covegas_replay/primary/rep1.ccr seq=608
original dlv_rate_bps / dlv_rate_max       231866 / 566686   (ratio 0.409161)
synthetic dlv_rate_bps                     566686
all other synthetic private fields changed NONE

fixed/v4:  post mode = DELAY    post dlv_rate_compete = 0
v3:        post mode = COMPETE  post dlv_rate_compete = 566686

SEMANTIC DIVERGENCE = YES   (divergent fields: priv_post_mode, priv_post_dlv_rate_compete,
  post_snd_cwnd, post_snd_cwnd_cnt, priv_post_detect_count, priv_post_recent_min_us,
  priv_post_last_compete_exit_jiffies, priv_post_delay_* [revert_to_delay writes], priv_post_cubic_ack_cnt)

SYNTHETIC POSITIVE CONTROL = PASS  (matches the precommitted prediction exactly)
```

This is MODULE-WIRING / CANDIDATE-SEMANTICS VALIDATION ONLY — not a real trace, not historical
evidence, not a new replay mode.

## Phase 4.2 — fixed/fixed real-trace negatives (stateful `ccreplay_diff.py`)

| trace | fixed/v4 vs fixed/v4 | events matched |
| --- | --- | ---: |
| rep1 | **NO DIVERGENCE** | 63,329 |
| rep2 | **NO DIVERGENCE** | 62,899 |
| rep3 | **NO DIVERGENCE** | 64,049 |

## Phase 4.3 — fixed/v3 real-trace negatives

| trace | fixed/v4 vs reconstructed-v3 | events matched | first divergence |
| --- | --- | ---: | --- |
| rep1 | **NO DIVERGENCE** | 63,329 | none |
| rep2 | **NO DIVERGENCE** | 62,899 | none |
| rep3 | **NO DIVERGENCE** | 64,049 | none |

Matches the precommitted prediction (§2.1): Predicate D is absent in all three current traces, so
the reconstructed-v3 unconditional latch and the fixed/v4 guarded latch produce the identical
transition on every event.

## Phase 4.4 — interpretation

> The synthetic Predicate-D positive control demonstrates that the reconstructed-v3 module is
> active and differs at the selected A3 branch. The three unmodified recorded traces independently
> produce NO DIVERGENCE, matching the scanner's prediction that Predicate D is absent.

## Diff-engine note (v2 support)

`user/ccreplay_diff.py` was extended with a `trace_version == 2` dispatch branch and a
mode-dependent comparison-schema path (`comparison_fields(callback_id, pre_mode, post_mode)`,
ADR-023) used when a model module exposes `comparison_fields` instead of a flat `COMPARISON_FIELDS`
dict. `priv_post_mode` is always in the dedicated field set, so a mode disagreement between the two
modules is caught as a divergence regardless of which union arm is gated. The v0/v1 paths are
unchanged: N4 hard-negative oracle (Reno + CUBIC, NO DIVERGENCE) and N5 bug1 (DIVERGENCE at
seq=1705, `ssthresh`, `result`) re-verified; `unittest` 40/40.

```text
ALL_CONTROLS_PASS = YES
A3_TRACK_BLOCKED  = NO
```
