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

### Coordinate convention (one throughout)

`Δ = first_dominant_event_wall − cubic_rep1_start_wall`.  `Δ > 0` ⇔ the first recorded CoVegas
callback is **after** the `date +%s.%N` that wrote `cubic_rep1_start_ts`. An event at
monotonic-relative time `t_e = (ev.ts_ns − first_dominant_event.ts_ns)/1e9` sits at schedule
position `t_e + Δ` (schedule anchored to `cubic_rep1_start_ts`).

### Harness happens-before (verified — `scripts/covegas_run_intermittent.sh`, `user/ccr_recorder_covegas.c`)

```text
M0   header.creation_ts_ns captured   (ccr_recorder_covegas.c:124 -- AFTER bpf__load(), BEFORE bpf__attach())
  <  M_attach   (covegas_wrapper_bpf__attach -> struct_ops registered -> "ccr_covegas" visible)
  <= M_seen     (driver: `sysctl ... | grep -q ccr_covegas` succeeds; poll loop, sleep 0.1)
  <  M_cov      (driver: `iperf3 -c ... -C ccr_covegas -t 120 ... &`  -- covegas client backgrounded)
  <  M_date     (driver: `date +%s.%N > cubic_rep1_start_ts.txt`  -- the very next statement)
and concurrently, after M_cov:
     M2 = first_dominant_event.ts_ns   (data-socket `init` callback -- after control connect + param exchange)
```

Script excerpt:

```sh
build/ccr_recorder_covegas "${PREFIX}.ccr" "${PREFIX}.meta.json" 125 > ... &
REC_PID=$!
for i in $(seq 1 100); do
  if sysctl net.ipv4.tcp_available_congestion_control 2>/dev/null | grep -q ccr_covegas; then ATTACHED=1; break; fi
  sleep 0.1
done
...
ip netns exec ns_h1 iperf3 -c 10.0.1.1 -p 5201 -C ccr_covegas -t 120 -i 1 -J > "${PREFIX}_covegas_iperf3.json" ... &
COVEGAS_PID=$!
for i in 1 2 3; do
  date +%s.%N > "${PREFIX}_cubic_rep${i}_start_ts.txt"
  ip netns exec ns_h1 iperf3 -c 10.0.1.1 -p 5301 -C cubic -t 20 -i 1 -J > ...
  date +%s.%N > "${PREFIX}_cubic_rep${i}_stop_ts.txt"
  [ "$i" -lt 3 ] && sleep 20
done
```

### Bounds on Δ (current traces)

- **Upper bound — RIGOROUS:** `Δ ≈ M2 − M_date`. Since `M_date > M0` (guaranteed by harness order),
  `M2 − M_date < M2 − M0 = (first_dominant_event.ts_ns − header.creation_ts_ns)`. Monotonic and
  realtime advance at the same rate to within ~0.5 ms/s over this ~10 s window (`CLOCK_MONOTONIC` is
  never stepped). **Measured: +0.298 / +0.295 / +0.276 s** for rep1/rep2/rep3.
- **Lower bound — LOOSE (derived, not asserted):** `Δ ≈ (M2 − M_cov) − ε_date`.
  - `M2 − M_cov ≥ 1 base RTT = 0.040 s`: the CoVegas **control** connection's TCP handshake must
    complete before iperf3 param exchange before the data socket's `connect()` → `init`. Base RTT
    is the topology constant (two 20 ms netem delays, `docs/PROVENANCE.md`; confirmed by early-trace
    `pre_srtt_us ≈ 40000`).
  - `ε_date < (cubic_rep1_stop_ts − cubic_rep1_start_ts) − 20 s`: the cubic-rep1 flow ran `-t 20`,
    so its wall time is ≥ 20 s; `(stop − start) = ε_date2 + cubic_wall`, `cubic_wall ≥ 20`, and
    `ε_date ≈ ε_date2` (same command). Value: **≈ 0.68 / 0.61 / 0.74 s** for rep1/rep2/rep3.
  - So `Δ > 0.040 − 0.68 ≈ −0.64 s` (rep1). This bound is loose because `ε_date_bound` also
    absorbs the cubic flow's own setup/teardown.
- **Empirical Δ (context only, not a bound):** `(covegas_iperf3.json start.timestamp.timemillisecs
  / 1000) − cubic_rep1_start_ts ≈ +0.12 s` for all three reps. The data-socket `init` is at or
  after that instant, so the true `Δ` is **≈ +0.12 … +0.20 s (positive)**.

**Current-trace offset interval: `Δ ∈ [≈ −0.65, +0.30] s`** (upper rigorous, lower loose).
`ROBUST_ON` / `ROBUST_OFF` is asserted for a DELAY→COMPETE transition only if
`[t_e + offset_lo, t_e + offset_hi]` lies entirely within one phase; a per-transition sensitivity
table over `Δ ∈ {−1.0 … +1.0}` is reported separately. The round-2 bracket `[−0.05, +0.30]` had
the correct **sign** (`Δ > 0` empirically) and a rigorous upper bound, but its lower bound `−0.05`
was **asserted without derivation**; the corrected interval is wider on the low side.

**Historical archive (`Ph500_B5x_rep2`).** The archived CSV carries **no** monotonic header
timestamp → **no rigorous cross-clock offset bound exists**. The ~65.51 s event is documented
historically as an off-period DELAY→COMPETE transition, and its OFF classification remains
unchanged under a ±4 s sensitivity analysis (nearest boundary 4.11 s). This is a sensitivity
result, not a robustness claim.

---

## Predicate H (for contrast — historical off-period symptom trigger)

> **Predicate H holds for an observed `cong_avoid` event iff `priv_pre_mode == DELAY` and
> `priv_post_mode == COMPETE` (a real DELAY→COMPETE transition on that event) AND its schedule
> window `[t_e + offset_lo, t_e + offset_hi]` (§7) lies entirely within a cross-traffic OFF
> period (`ROBUST_OFF`).** If the window straddles a phase boundary the classification is
> `ALIGNMENT_LIMITED`, not H. Where no rigorous offset interval exists (the historical archive), H
> is not asserted — only a sensitivity result is reported.

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
