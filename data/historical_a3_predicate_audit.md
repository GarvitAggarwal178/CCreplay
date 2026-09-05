# CoVegas A3 Settle-Latch Divergence Predicate — Source Derivation

Derives, from the actual selected source, the exact condition under which the reconstructed **v3**
CoVegas build (unconditional settle-latch) and the fixed **v4** build (guarded settle-latch, "A3")
diverge. This is **Predicate D** — distinct from **Predicate H**, the historical off-period
symptom trigger (defined at the end).

**Read-only sources inspected (not modified):**

- `~/cn-spike/covegas/src/covegas.bpf.c` — the only committed version of this file, i.e. the
  selected FIXED (v4) reference (`data/historical_regression_selection.md`).
- `bpf/covegas_wrapper.bpf.c` — CCReplay's recorder, algorithm logic copied near-verbatim (ADR-022).
- `user/covegas_model.py` — CCReplay's userspace replay model.

---

## 1. Exact callback containing the A3 decision

`cong_avoid` → `handle_compete_mode()`.

`~/cn-spike/covegas/src/covegas.bpf.c` `covegas_cong_avoid` (the `.cong_avoid` entry, lines
~846–860):

```c
	__u64 now = bpf_ktime_get_ns();
	...
	if (handle_minrtt_probe(tp, ca, now))
		return;                       /* probe active/started -> no mode dispatch this call */
	if (ca->mode == MODE_COMPETE)
		handle_compete_mode(tp, ca, acked);
	else
		handle_delay_mode(tp, ca, ack, acked);
```

The CCReplay recorder (`bpf/covegas_wrapper.bpf.c` lines 763–768) and model
(`user/covegas_model.py` lines 533–542) reproduce this dispatch exactly.

The A3 decision is **only** in `handle_compete_mode`; it is not evaluated in any other callback.

## 2. Exact `handle_compete_mode` body (v4, byte-identical in `covegas.bpf.c` and `bpf/covegas_wrapper.bpf.c`)

`~/cn-spike/covegas/src/covegas.bpf.c` lines 697–715:

```c
static void handle_compete_mode(struct tcp_sock *tp, struct covegas *ca, __u32 acked)
{
	if (ca->dlv_rate_compete == 0) {
		__u32 elapsed_jiffies = tcp_jiffies32 - ca->compete_enter_jiffies;

		if (elapsed_jiffies >= (RATE_SETTLE_MS * HZ) / 1000 && ca->dlv_rate_bps) {
			if (ca->dlv_rate_bps < (ca->dlv_rate_max * 3) / 4) {
				ca->dlv_rate_compete = ca->dlv_rate_bps;          /* LATCH   */
			} else {
				revert_to_delay(tp, ca);                          /* v4/A3   */
				return;
			}
		}
	} else if (ca->dlv_rate_bps > (RATE_JUMP_NUM * ca->dlv_rate_compete) / RATE_JUMP_DEN) {
		revert_to_delay(tp, ca);                                          /* rate-jump revert */
		return;
	}

	cubic_growth(tp, ca, acked);
}
```

Model equivalent: `user/covegas_model.py` `handle_compete_mode()` lines 360–379 — same structure,
same integer arithmetic, `CONFIG_HZ = 250` (ground-truthed, same kernel as the CUBIC audit).

## 3. The reconstructed v3 build (from `data/historical_regression_selection.md`)

v3's source was never committed. The reconstruction replaces **only** the A3 guard with v3's
documented unconditional latch:

```c
		if (elapsed_jiffies >= (RATE_SETTLE_MS * HZ) / 1000 && ca->dlv_rate_bps) {
			ca->dlv_rate_compete = ca->dlv_rate_bps;    /* v3: unconditional, no guard */
		}
```

A1 (targeted cwnd-on-revert) and A2 (detection hold) are **left at v4** in the "buggy" build, per
`data/historical_regression_selection.md` (isolating A3 alone; A1's separate regression is out of
scope).

## 4. Exact mode/state prerequisites for the settle-latch code to be *evaluated*

Working from the recorded PRE state of a `cong_avoid` event and the recorded controller-visible
clocks (`clock_ktime_ns_before` as `now`, `clock_jiffies32_before` as `tcp_jiffies32` — the ktime
value is the *exact* one the controller consumes, see the CoVegas-ktime section of
`REPORT_COVEGAS_REPLAY_FIDELITY.md`; jiffies is bracketed, see the ambiguity note below):

0. **`tcp_is_cwnd_limited(...)` is true.** `~/cn-spike/covegas/src/covegas.bpf.c` `covegas_cong_avoid`
   dispatches to `handle_minrtt_probe`/`handle_compete_mode` only for a cwnd-limited ACK; the
   CCReplay recorder makes this explicit as an early `if (!tcp_is_cwnd_limited(sk)) return;` at the
   very top of `ccr_covegas_cong_avoid` (`bpf/covegas_wrapper.bpf.c` line ~746, *before* sequence
   allocation and recording), and `user/covegas_model.py` cong_avoid (lines 523–524) checks the same
   before `handle_minrtt_probe`. Model form
   (`user/covegas_model.py` `tcp_is_cwnd_limited`, lines 226–229):
   `cwnd < ssthresh ? cwnd < 2*max_packets_out : bool(is_cwnd_limited)`.
   Required ABI-v2 inputs: `pre_snd_cwnd`, `pre_snd_ssthresh`, `pre_max_packets_out`,
   `pre_is_cwnd_limited`.
   *Because the recorder applies the kernel's own `tcp_is_cwnd_limited(sk)` before emitting any
   `cong_avoid` record, every recorded `cong_avoid` event is already cwnd-limited; the model's
   reimplementation agrees on all of them (0 mismatches, all 3 traces — round-2 scan). This gate
   therefore removes 0 events from the current traces, but the scanner must apply it in the correct
   position so that its control flow matches the real implementation and so it stays correct on any
   future trace.*
1. **`handle_minrtt_probe(tp, ca, now)` returns 0.** From `covegas.bpf.c` lines 606–662: returns
   non-zero if `ca->minrtt_probing` (PRE) is set, or if
   `now - ca->last_minrtt_probe_ns >= period_ns` where
   `period_ns = MINRTT_PERIOD_MS·1e6` (10 s) when `!(mode==COMPETE && dlv_rate_compete!=0)` — which
   is exactly the Predicate-D pre-state (COMPETE, `dlv_rate_compete==0`). So it returns 0 iff
   `priv_pre_minrtt_probing == 0` **and** `clock_ktime_ns_before - priv_pre_last_minrtt_probe_ns < 10·10⁹`.
2. **`ca->mode == MODE_COMPETE`** (`priv_pre_mode == 1`) → dispatch to `handle_compete_mode`.
3. **`ca->dlv_rate_compete == 0`** (`priv_pre_dlv_rate_compete == 0`) → enter the settle-latch block
   (not the rate-jump `else if`).
4. **`elapsed_jiffies >= (RATE_SETTLE_MS · HZ) / 1000`**, i.e.
   `(u32)(clock_jiffies32_before − priv_pre_compete_enter_jiffies) >= (1000 · 250) / 1000 = 250`.
5. **`ca->dlv_rate_bps != 0`** (`priv_pre_dlv_rate_bps != 0`).

If 0–5 hold, the **v4 guard is evaluated**. If any of 0–5 fails, v3 and v4 do the same thing on
this event (either both early-return, both skip the latch, both take the rate-jump branch, or both
probe).

## 5. Exact v4 guard and the two outcomes

**Guard expression:** `ca->dlv_rate_bps < (ca->dlv_rate_max * 3) / 4` — all u32, integer division,
PRE values (`priv_pre_dlv_rate_bps`, `priv_pre_dlv_rate_max`).

| guard | v4 | v3 (reconstructed) | diverge? |
| --- | --- | --- | --- |
| **TRUE** (`dlv_rate_bps < ¾·dlv_rate_max`) | `dlv_rate_compete = dlv_rate_bps`; fall through to `cubic_growth` | identical | **NO** |
| **FALSE** (`dlv_rate_bps >= ¾·dlv_rate_max`) | `revert_to_delay(tp, ca)`; `return` (skips `cubic_growth`) | `dlv_rate_compete = dlv_rate_bps`; fall through to `cubic_growth` | **YES** |

## 6. Predicate D (final)

> **Predicate D holds for an observed `cong_avoid` event iff, evaluating the deterministic control
> flow on that event's recorded PRE state and recorded controller-visible clocks:
> conditions §4.0–§4.5 all hold, AND the guard §5 is FALSE
> (`priv_pre_dlv_rate_bps >= (priv_pre_dlv_rate_max * 3) / 4`).**

On a Predicate-D event, replaying the recorded PRE state through the reconstructed-v3 model and the
v4 model yields different declared results / semantic state — first differing fields:
`priv_post_mode` (DELAY vs COMPETE), `priv_post_dlv_rate_compete` (0 vs `dlv_rate_bps`), and every
field `revert_to_delay` writes vs. every field `cubic_growth` writes.

### State/inputs required to evaluate Predicate D — all present in Replay ABI v2

| needed | ABI v2 field | present |
| --- | --- | --- |
| cwnd-limited inputs (§4.0) | `pre_snd_cwnd`, `pre_snd_ssthresh`, `pre_max_packets_out`, `pre_is_cwnd_limited` | yes |
| mode (PRE) | `priv_pre_mode` | yes |
| `dlv_rate_compete` (PRE) | `priv_pre_dlv_rate_compete` | yes |
| `compete_enter_jiffies` (PRE) | `priv_pre_compete_enter_jiffies` | yes |
| `dlv_rate_bps` (PRE) | `priv_pre_dlv_rate_bps` | yes |
| `dlv_rate_max` (PRE) | `priv_pre_dlv_rate_max` | yes |
| `minrtt_probing` (PRE) | `priv_pre_minrtt_probing` | yes |
| `last_minrtt_probe_ns` (PRE) | `priv_pre_last_minrtt_probe_ns` | yes |
| `probe_action_start_ns` (PRE) | `priv_pre_probe_action_start_ns` | yes |
| `tcp_jiffies32` | `clock_jiffies32_before` **and** `clock_jiffies32_after` (bracketed, not injected) | yes |
| controller `now` (ktime) | `clock_ktime_ns_before` (exact consumed value) | yes |
| `srtt_us` (PRE) | `pre_srtt_us` | yes |
| `RATE_SETTLE_MS`, `HZ`, `MINRTT_PERIOD_MS` | build constants (1000 / 250 / 10000) | yes |

### Clock qualification (do not overstate)

Predicate D's required controller state/inputs are **represented** by ABI v2. It is **not**
"universally exactly observable" merely because every field is present: `tcp_jiffies32` remains a
*bracketed* quantity (`clock_jiffies32_before` / `_after`), not an injected exact value.

> A scanned event is **exactly classifiable** with respect to the settle-time gate (§4.4) when the
> predicate has the same truth value under **both** recorded jiffies bracket endpoints. No scanned
> classification may silently choose whichever endpoint produces the desired answer.

The scanner (`user/scan_historical_a3.py`) evaluates §4.4 under **both** `clock_jiffies32_before`
and `clock_jiffies32_after` and reports `settle_gate_jiffies_bracket_flips`. In the round-2 scan of
all three primary traces this count is **0** — every scanned settle-gate classification is exactly
resolved. All other Predicate-D conditions (§4.0, §4.1, §4.2, §4.3, §4.5, §5) use recorded PRE
state or the exact controller-consumed `clock_ktime_ns_before`, so they carry no bracket ambiguity.

## 7. Predicate-H time alignment (event clock vs cross-traffic schedule)

Classifying a DELAY→COMPETE transition as ON- or OFF-period requires placing an event on the
cross-traffic wall-clock timeline. The two clocks differ:

| quantity | clock | source |
| --- | --- | --- |
| event `ts_ns` | `CLOCK_MONOTONIC` | `bpf_ktime_get_ns()` in the recorder |
| header `creation_ts_ns` | `CLOCK_MONOTONIC` | `clock_gettime(CLOCK_MONOTONIC)` (`user/ccr_recorder_covegas.c` line 60) |
| `cubic_rep{1,2,3}_{start,stop}_ts.txt` | `CLOCK_REALTIME` | `date +%s.%N` in `scripts/covegas_run_intermittent.sh` |
| covegas iperf3 `start.timestamp.timesecs` | `CLOCK_REALTIME` | iperf3, **1-second-quantized** (`timemillisecs` is finer) |

**No artifact records both clock domains at one instant → there is no exact common anchor.**
`data/audit_src/check_historical_trigger.py` implicitly assumed the two zero points coincide (and
used the 1-second-quantized `timesecs`); that assumption is now made explicit and bracketed.

**Artifact-derived offset bracket (current traces).** Anchor the schedule to
`cubic_rep1_start_ts.txt` (`date +%s.%N`, captured in the driver script immediately after the
covegas iperf3 client is backgrounded, before cross-traffic rep1). An event at monotonic-relative
time `t_e = (ev.ts_ns − first_dominant_event.ts_ns)/1e9` sits at schedule position `t_e + Δ`,
`Δ = first_dominant_event_wall − cubic_rep1_start_wall`.

- **Upper bound (rigorous):** `Δ < (first_dominant_event.ts_ns − header.creation_ts_ns)/1e9`. The
  recorder starts (captures `creation_ts_ns`, monotonic) *before* the covegas iperf3 process is
  launched, and the first `init` callback is *after* that; both clocks advance at the same rate to
  within ~0.5 ms/s. Measured: **0.30 s / 0.29 s / 0.28 s** for rep1/rep2/rep3.
- **Lower bound:** `Δ ≥ 0` — the first `init` callback (connection setup) occurs after
  `cubic_rep1_start_ts` was captured (one `date` exec after the covegas process was backgrounded).
  A −0.05 s pad absorbs `date` exec time and slew.

So the current-trace bracket is **Δ ∈ [−0.05, +0.30] s**. A DELAY→COMPETE transition is classified
ON/OFF only if `[t_e − 0.05, t_e + 0.30]` lies entirely within one phase; otherwise
`ALIGNMENT-LIMITED`.

**Historical archive (`Ph500_B5x_rep2`).** The archived CSV carries **no** monotonic header
timestamp, so no rigorous upper bound on `Δ'` is available. Classification robustness is reported
as distance-to-nearest-boundary vs. a deliberately generous ±4.0 s allowance (the physical offset
is sub-second — first telemetry row after connection setup).

---

## Predicate H (for contrast — historical off-period symptom trigger)

> **Predicate H holds for an observed `cong_avoid` event iff `priv_pre_mode == DELAY` and
> `priv_post_mode == COMPETE` (a real DELAY→COMPETE transition on that event) AND the event's
> wall-clock time falls in a cross-traffic OFF period, *robustly over the §7 offset bracket*.** If
> the phase is not invariant over that bracket the classification is `ALIGNMENT-LIMITED`, not H.

The schedule is derived from the run's own `*_cubic_rep{1,2,3}_{start,stop}_ts.txt` files (anchor:
`cubic_rep1_start_ts.txt`). This supersedes `data/audit_src/check_historical_trigger.py`'s
implicit "zero points coincide" assumption and its use of the 1-second-quantized iperf3 `timesecs`.

## Relationship between H and D

They are related but **not** definitionally identical:

- Predicate H is about *how/when* a COMPETE episode is entered (spuriously, with no real competitor).
- Predicate D is about *what happens at the settle-latch check* inside a COMPETE episode.

A guard-failing settle-latch evaluation (D) can in principle occur in a COMPETE episode that was
entered legitimately during real competition — that would still demonstrate the v3/v4 implementation
difference, but it would **not** reproduce the historically selected off-period trigger.

For the historical regression to be trigger-positive **in the strongest sense**, one COMPETE
episode must contain **both**:

1. Predicate H — the DELAY→COMPETE entry during an OFF period; and
2. Predicate D — a later settle-latch evaluation *in that same episode* where the v4 guard fails.

This "same-episode H+D" criterion is fixed here, before the scan results, and is not revised
afterward.
