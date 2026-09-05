# CCReplay — Latest Session Review Handoff

**One-file review packet.** A reviewer who already understands CCReplay's architecture should be
able to audit this session by reading only this file. Individual reports, data files, scripts,
source files, and git history remain authoritative for their respective evidence; this file is a
self-contained snapshot. Every future bounded CCReplay session replaces this file.

---

## 1. SESSION IDENTITY

```text
SESSION:                 Predicate-H time-origin final correction (round 3)
                         -- offline correction to the round-2 A3 scanner phase-alignment audit
DATE:                    2026-09-05
STARTING COMMIT:         45aa0ff  "audit: correct A3 scanner control flow + verify workload phase alignment"
ENDING COMMIT:           <this session's commit -- see `git log --oneline -1`>
TASK STATUS:             COMPLETE -- offline, read-only; STOP for project-level review
FORMAL VERDICTS CHANGED: NO   (CUBIC R3 = PARTIAL, CoVegas self-replay = PASS, historical case = INCOMPLETE)
NEW NETWORK CAPTURES:    NO
NEW DIFFERENTIAL REPLAY: NO
```

**Work-stream commits (all same day):**

- `bb0fb3e` — created `docs/CURRENT_STATE.md`; full-46 CUBIC clock attribution (`2/4/40/0`);
  historical-trigger denominator fixes; CoVegas `undo_cwnd` Outcome-A; CoVegas ktime dataflow.
- `d9677dc` — round-1 A3 predicate audit: derived Predicate D from source; built
  `user/scan_historical_a3.py` + `data/audit_src/analyze_historical_a3_archive.py`; scanned the
  3 CoVegas traces; validated against the historical archive positive.
- `45aa0ff` — round-2: added the cwnd-limited GATE 0 to the scanner (0 event-count change; the
  recorder already pre-filters on the kernel `tcp_is_cwnd_limited(sk)`); jiffies-bracket
  settle-gate sensitivity (0 flips); an event/schedule offset bracket **stated as `[-0.05, +0.30] s`
  with the lower bound asserted, not derived**.
- **this session (round 3)** — re-derive the offset from the verified harness happens-before
  order; reclassify all 9 DELAY→COMPETE transitions; correct historical-archive terminology;
  correct statistical wording ("expected outcome").

**Exact bounded goal of this session:** independent review found the round-2 offset interval
`Δ ∈ [-0.05, +0.30] s` had an **asserted, underived lower bound**, and raised the possibility of a
**wrong sign**. Re-derive `Δ` from the actual harness execution order and artifacts; use one
coordinate convention throughout; label each inequality rigorous / coarse / none; reclassify all 9
transitions; apply the same reasoning to the historical archive; do not strengthen Predicate D;
fix the "expected outcome" statistical wording. No new captures, no differential replay, no
recorder/parser/model change.

---

## 2. BINDING CLAIM BOUNDARY

> CCReplay answers what a congestion-control implementation computes at a recorded callback
> boundary. It does not claim what network trajectory or performance that implementation would have
> produced.

Load-bearing rules this session:

- Mode B injects recorded shared TCP boundary state at every callback; controller-private state
  evolves; Linux TCP between callbacks is not simulated.
- "Exact" = exact semantic equality under the declared comparison schema. No general
  `byte-exact` / `bit-exact`.
- No oracle is weakened to obtain a PASS.
- **Predicate H (historical off-period symptom trigger) and Predicate D (A3 implementation
  divergence condition) are related but not identical** — never conflated; no claim that the
  historical A3 regression has been localized (the buggy-vs-fixed differential replay has not run
  and is not authorized).
- `tcp_jiffies32` is bracketed (`clock_jiffies32_before` / `_after`), not injected. No
  classification silently picks the endpoint that gives a desired answer.
- **Time-origin rule (this session):** an inequality is "rigorous" only if it follows from
  measured timestamps or guaranteed process ordering. Expected small startup latency is not
  evidence. Where no rigorous bound exists, say so and report a sensitivity table.

---

## 3. PRECOMMITTED / PRE-EXISTING CRITERIA

All three predicates were fixed in `data/historical_a3_predicate_audit.md` **before** any scan
result. Round 2 *added* condition §4.0 (cwnd-limited); round 3 *added* the coordinate convention,
harness happens-before, and the `ROBUST_*` / `ALIGNMENT_LIMITED` classification rule. **No round
relaxed any condition, moved any threshold, or changed the guard expression, the 250-jiffy settle
threshold, or the same-episode rule.**

### Predicate H — historical off-period symptom trigger

> A `cong_avoid` event with `priv_pre_mode == DELAY` and `priv_post_mode == COMPETE` (a real
> DELAY→COMPETE transition) whose schedule window `[t_e + offset_lo, t_e + offset_hi]` (§10) lies
> **entirely** within a cross-traffic OFF period → `ROBUST_OFF`. If the window straddles a phase
> boundary → `ALIGNMENT_LIMITED`, not H. Where no rigorous offset interval exists (the historical
> archive) H is not asserted — only a sensitivity result is reported.

### Predicate D — A3 implementation-divergence condition (source-derived; §5)

> A `cong_avoid` event where, evaluating the deterministic control flow on the recorded PRE state
> + recorded controller-visible clocks, conditions §4.0–§4.5 all hold **and** the v4 guard §5 is
> FALSE (`priv_pre_dlv_rate_bps >= (priv_pre_dlv_rate_max * 3) / 4`).
>
> §4.0 cwnd-limited · §4.1 `handle_minrtt_probe` returns 0 · §4.2 `priv_pre_mode == COMPETE` ·
> §4.3 `priv_pre_dlv_rate_compete == 0` · §4.4 `(u32)(clock_jiffies32_before −
> priv_pre_compete_enter_jiffies) >= 250` (evaluated under **both** jiffies bracket endpoints) ·
> §4.5 `priv_pre_dlv_rate_bps != 0`.

### Same-episode H+D rule

> One COMPETE episode must contain both Predicate H (its DELAY→COMPETE entry during an OFF period)
> and Predicate D (a later guard-failing settle-latch evaluation in that same episode).

### Interpretation matrix (from the task prompt; fixed before results)

```text
CASE 1  H + D in the same episode (in a current v2 trace)  -> HISTORICAL DIFF CANDIDATE = YES (do not run)
CASE 2  D present, not linked to an OFF-period H            -> A3 MECHANISM-DIFF CANDIDATE = YES; HISTORICAL = NO
CASE 3  H present but D does not fail                       -> trigger-like episode present, differential condition absent
CASE 4  neither present                                     -> NO EXISTING DIFF CANDIDATE
```

---

## 4. FILES CHANGED

### `git diff --stat` (this session, on top of `45aa0ff`)

```text
 REPORT_DEVELOPMENT_SESSION_INDEX.md                       |   3 +-
 REPORT_EVIDENCE_RECONCILIATION_AND_A3_PREDICATE_AUDIT.md  | ~120 +
 data/audit_src/analyze_historical_a3_archive.py           |  ~40 +-
 data/historical_a3_archive_analysis.json                  |  regenerated
 data/historical_a3_existing_trace_scan.json               |  regenerated
 data/historical_a3_existing_trace_scan.md                 |  regenerated
 data/historical_a3_predicate_audit.md                     |  ~70 +-
 data/historical_trigger_validation.md                     |   4 +-
 docs/CURRENT_STATE.md                                     |  ~20 +-
 user/scan_historical_a3.py                                | ~120 +-
 REPORT_HISTORICAL_COVEGAS_REGRESSION.md                   |   8 +-
 docs/session/LATEST_REVIEW_HANDOFF.md                     |  replaced (this file)
```

### Change table

| file | purpose of change | class |
| --- | --- | --- |
| `user/scan_historical_a3.py` | `derive_offset_bracket()` replaces the asserted `OFFSET_LOWER_PAD_S = -0.05`; rigorous upper + loose-derived lower + empirical Δ; `phase_over_interval()` → `ROBUST_ON` / `ROBUST_OFF` / `ALIGNMENT_LIMITED`; per-transition sensitivity table | **analysis-script semantic change** (offline scanner only) |
| `data/audit_src/analyze_historical_a3_archive.py` | `ON/OFF (robust)` → `… (unchanged under ±4s)`; `rigorous_offset_bound: NONE`; corrected summary wording | analysis-script semantic change (offline, read-only) |
| `data/historical_a3_predicate_audit.md` | §7 rewritten: coordinate convention, harness happens-before + script excerpt, rigorous-upper / loose-lower derivations, empirical Δ; Predicate-H definition tied to `ROBUST_OFF` | docs |
| `REPORT_EVIDENCE_RECONCILIATION_AND_A3_PREDICATE_AUDIT.md` | append "Round-3 correction" section | docs |
| `docs/CURRENT_STATE.md` | §10 updated (ROBUST_ON over derived interval); §9 statistical wording | docs |
| `data/historical_trigger_validation.md`, `REPORT_HISTORICAL_COVEGAS_REGRESSION.md` | statistical wording: drop "expected outcome" / "most likely" | docs |
| `REPORT_DEVELOPMENT_SESSION_INDEX.md` | add round-3 row | docs |

**No recorder / parser / replay-model / trace-format file changed.** `bpf/*`, `user/ccr_*.py`,
`user/covegas_model.py`, `user/replay_*.py` untouched.

### Semantic diff hunk — `user/scan_historical_a3.py` (offset re-derivation)

```python
-OFFSET_LOWER_PAD_S = -0.05     # <-- round-2: asserted, not derived
+TOPOLOGY_BASE_RTT_S = 0.040                       # two 20ms netem delays (docs/PROVENANCE.md)
+OFFSET_SENSITIVITY_GRID = [-1.0, -0.5, -0.3, -0.1, 0.0, 0.12, 0.30, 0.5, 1.0]
+
+def derive_offset_bracket(hdr, dom, prefix):
+    """Delta = first_dominant_event_wall - cubic_rep1_start_wall  (Delta>0 => event AFTER anchor)."""
+    first_ev = dom[0]["ts_ns"]
+    offset_hi = (first_ev - hdr.creation_ts_ns) / 1e9          # RIGOROUS upper: M_date > M0
+    c1s = read_ts(f"{prefix}_cubic_rep1_start_ts.txt")
+    c1e = read_ts(f"{prefix}_cubic_rep1_stop_ts.txt")
+    eps_date_bound = max(0.0, (c1e - c1s) - 20.0)              # cubic ran -t 20 => wall >= 20s
+    offset_lo = TOPOLOGY_BASE_RTT_S - eps_date_bound           # LOOSE lower (derived, not asserted)
+    # empirical (context only): (iperf3 timemillisecs/1000 - c1s) ~= +0.12s across reps
+    ...
+
+def phase_over_interval(sched_lo, sched_hi, on_periods):
+    # samples endpoints + any interior schedule edge; ROBUST_ON / ROBUST_OFF / ALIGNMENT_LIMITED
```

---

## 5. RELEVANT SOURCE / MODEL / SCANNER EXCERPTS

### 5.1 Harness happens-before — `scripts/covegas_run_intermittent.sh`

```sh
build/ccr_recorder_covegas "${PREFIX}.ccr" "${PREFIX}.meta.json" 125 > ...stdout 2> ...stderr &
REC_PID=$!
ATTACHED=0
for i in $(seq 1 100); do
  if sysctl net.ipv4.tcp_available_congestion_control 2>/dev/null | grep -q ccr_covegas; then
    ATTACHED=1; break
  fi
  sleep 0.1
done
[ "$ATTACHED" -ne 1 ] && { echo "STOP: recorder failed to attach"; kill "$REC_PID"; exit 4; }
echo "recorder attached"

ip netns exec ns_h1 iperf3 -c 10.0.1.1 -p 5201 -C ccr_covegas -t 120 -i 1 -J \
  > "${PREFIX}_covegas_iperf3.json" 2> "${PREFIX}_covegas_iperf3.err" &
COVEGAS_PID=$!

for i in 1 2 3; do
  date +%s.%N > "${PREFIX}_cubic_rep${i}_start_ts.txt"        # <-- schedule anchor (cross-traffic ON start)
  ip netns exec ns_h1 iperf3 -c 10.0.1.1 -p 5301 -C cubic -t 20 -i 1 -J > "${PREFIX}_cubic_rep${i}_iperf3.json" ...
  date +%s.%N > "${PREFIX}_cubic_rep${i}_stop_ts.txt"
  [ "$i" -lt 3 ] && sleep 20
done
wait $COVEGAS_PID; wait $REC_PID
```

### 5.2 Recorder — where `creation_ts_ns` is captured (`user/ccr_recorder_covegas.c`)

```text
FILE:  user/ccr_recorder_covegas.c
LINE:  60   static __u64 now_ns(void) { struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts); ... }
LINE:  93   struct covegas_wrapper_bpf *skel = covegas_wrapper_bpf__open();
LINE:  99   if (covegas_wrapper_bpf__load(skel)) { ... }
LINE: 124   hdr.creation_ts_ns = now_ns();          <-- captured AFTER bpf__load(), BEFORE bpf__attach()
LINE: 143   if (covegas_wrapper_bpf__attach(skel)) { ... }   <-- struct_ops registered here
LINE: 155   printf("ATTACHED\n");
```

Recorder event `ts_ns` = `bpf_ktime_get_ns()` (`bpf/ccr_event_v2.h:49`; also `CLOCK_MONOTONIC`).

### 5.3 Established happens-before (from 5.1 + 5.2)

```text
M0  = header.creation_ts_ns        (recorder, monotonic; after load, before attach)
  <  M_attach                      (struct_ops registered)
  <= M_seen                        (driver's `grep -q ccr_covegas` succeeds; 0.1s poll)
  <  M_cov                         (covegas iperf3 backgrounded)
  <  M_date                        (`date +%s.%N > cubic_rep1_start_ts.txt` -- next statement)
concurrently after M_cov:
     M2 = first_dominant_event.ts_ns   (data-socket `init` -- after control connect + iperf3 param exchange)
```

`M_date` and `M2` are **not** ordered by process structure alone (both follow `M_cov`); `M_date`
is one `date` exec after `M_cov`, `M2` is one full connection setup after `M_cov`.

### 5.4 `handle_compete_mode` — the A3 settle-latch (v4)

```text
FILE:  ~/cn-spike/covegas/src/covegas.bpf.c   LINE RANGE: 697-715   (byte-identical: bpf/covegas_wrapper.bpf.c 424-443)
```

```c
static void handle_compete_mode(struct tcp_sock *tp, struct covegas *ca, __u32 acked)
{
    if (ca->dlv_rate_compete == 0) {
        __u32 elapsed_jiffies = tcp_jiffies32 - ca->compete_enter_jiffies;
        if (elapsed_jiffies >= (RATE_SETTLE_MS * HZ) / 1000 && ca->dlv_rate_bps) {
            if (ca->dlv_rate_bps < (ca->dlv_rate_max * 3) / 4) {
                ca->dlv_rate_compete = ca->dlv_rate_bps;          /* LATCH -- v3 and v4 agree */
            } else {
                revert_to_delay(tp, ca);                          /* v4/A3 -- v3 does NOT do this */
                return;
            }
        }
    } else if (ca->dlv_rate_bps > (RATE_JUMP_NUM * ca->dlv_rate_compete) / RATE_JUMP_DEN) {
        revert_to_delay(tp, ca);                                  /* rate-jump revert -- v3 has this too */
        return;
    }
    cubic_growth(tp, ca, acked);
}
```

Reconstructed **v3**: the guard is replaced by an unconditional `ca->dlv_rate_compete =
ca->dlv_rate_bps;`. **Divergence iff** the guard expression is FALSE while the settle-latch block is
entered. `RATE_SETTLE_MS = 1000`, `CONFIG_HZ = 250` → threshold = **250 jiffies**.

### 5.5 `cong_avoid` control flow into the A3 decision

```c
/* ~/cn-spike/covegas/src/covegas.bpf.c covegas_cong_avoid (~846-860) */
    __u64 now = bpf_ktime_get_ns();
    if (!tcp_is_cwnd_limited(sk)) return;              /* GATE 0 */
    if (handle_minrtt_probe(tp, ca, now)) return;      /* GATE 1 */
    if (ca->mode == MODE_COMPETE) handle_compete_mode(tp, ca, acked);   /* GATE 2 */
    else handle_delay_mode(tp, ca, ack, acked);
```

`bpf/covegas_wrapper.bpf.c` `ccr_covegas_cong_avoid` applies `if (!tcp_is_cwnd_limited(sk)) return;`
at the top **before sequence allocation / recording** — so every recorded `cong_avoid` event is
already cwnd-limited. Model (`user/covegas_model.py:523-524`): same check, early return, then
`handle_minrtt_probe`, then dispatch. `tcp_is_cwnd_limited` (model, lines 226-229):
`cwnd < ssthresh ? cwnd < 2*max_packets_out : bool(is_cwnd_limited)`.

---

## 6. ANALYSIS / DETECTOR IMPLEMENTATION

Full script: `user/scan_historical_a3.py` (offline, read-only; committed this session). Decision
logic:

**Connection selection:** `select_dominant_connection(events)` (validated ADR-016 selector) — most
events wins; 1 stray control-channel event per trace excluded. Sorted by `seq`.

**Predicate D, per `cong_avoid` dominant-connection event:**

```text
GATE 0  if not tcp_is_cwnd_limited(pre_snd_cwnd, pre_snd_ssthresh, pre_max_packets_out, pre_is_cwnd_limited): skip
GATE 1  if handle_minrtt_probe(dict(ca), pre, clock_ktime_ns_before, clock_jiffies32_before)[0]: skip
GATE 2  if ca["mode"] != MODE_COMPETE: skip
GATE 3  if ca["dlv_rate_compete"] != 0: skip     # rate-jump branch: identical v3/v4
GATE 4  ej        = u32(u32(clock_jiffies32_before) - ca["compete_enter_jiffies"])
        if not (ej >= 250 and ca["dlv_rate_bps"]): skip
        ej_after  = u32(u32(clock_jiffies32_after)  - ca["compete_enter_jiffies"])
        gate_flips = (ej >= 250) != (ej_after >= 250)     # tracked; 0 across all traces
GUARD   if ca["dlv_rate_bps"] < (ca["dlv_rate_max"] * 3) // 4:  guard_passes += 1 ; skip
        else:  guard_failures += 1  ->  PREDICATE D
```

**Predicate H, per DELAY→COMPETE transition:**

```text
t   = (ev.ts_ns - first_dominant_event.ts_ns) / 1e9            # CLOCK_MONOTONIC-relative
offset_lo, offset_hi = derive_offset_bracket(hdr, dom, prefix) # see 4 / 10
on_periods = [(cN_start - c1_start, cN_stop - c1_start) for N in 1..3]   # cubic_rep1_start anchor
phase_over_interval([t+offset_lo, t+offset_hi], on_periods)
    -> ROBUST_ON  iff every sampled point (endpoints + interior schedule edges) is ON
       ROBUST_OFF iff every sampled point is OFF
       ALIGNMENT_LIMITED otherwise
PREDICATE H  iff ROBUST_OFF
plus a sensitivity row: phase(t + d) for d in {-1.0, -0.5, -0.3, -0.1, 0, +0.12, +0.3, +0.5, +1.0}
```

**Assumptions (explicit in the script):** (a) `CLOCK_MONOTONIC` and `CLOCK_REALTIME` advance at the
same rate to within ~0.5 ms/s over a ~10 s window (`CLOCK_MONOTONIC` is never stepped); (b) the
recorder captures `creation_ts_ns` before the covegas process starts (harness order, 5.1–5.3);
(c) the first data-socket `init` is after the covegas process starts, and after ≥ 1 base RTT
(the control-connection handshake must complete first).

Historical analyzer: `data/audit_src/analyze_historical_a3_archive.py` — same guard arithmetic;
schedule anchored to `cubic_rep1_start_ts`; **±4 s sensitivity only** (the CSV has no monotonic
anchor → no rigorous bound).

---

## 7. INPUT DATA ACCOUNTING

### Current CoVegas v2 traces (analyzed; not modified)

| trace | raw events | dominant-conn | other (excl) | drops | seq gaps | cong_avoid (dom) | mode transitions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `raw/covegas_replay/primary/rep1.ccr` | 63,330 | 63,329 | 1 | 0 | 0 | 31,348 | 6 (3 D→C, 3 C→D) |
| `raw/covegas_replay/primary/rep2.ccr` | 62,900 | 62,899 | 1 | 0 | 0 | 31,151 | 6 |
| `raw/covegas_replay/primary/rep3.ccr` | 64,050 | 64,049 | 1 | 0 | 0 | 31,683 | 6 |

Workload: covegas 120 s continuous; cubic cross-traffic 20 s on / 20 s off ×3. Gate-3-R2 topology,
40 ms base RTT, `HOLD_MS=500`, `CONFIG_HZ=250`. All `validate_run_v2` pass (committed
`_validation.json`).

Header fields used: `creation_ts_ns` (`CLOCK_MONOTONIC`). Schedule files:
`cubic_rep{1,2,3}_{start,stop}_ts.txt` (`date +%s.%N`, `CLOCK_REALTIME`). Context:
`covegas_iperf3.json start.timestamp.timemillisecs` (`CLOCK_REALTIME`).

### Historical read-only archive

```text
SOURCE PATH:              ~/cn-spike/covegas/raw/partC_v4/Ph500_B5x_rep2_ringbuf.csv  (+ *_start_ts / *_stop_ts / *_covegas_iperf3.json / *_covegas_start_ts.txt)
SOURCE PROVENANCE:        ~/cn-spike repo (read-only per CLAUDE.md); HEAD 022c2e2; partC_v4 = REPORT_COVEGAS_V4.md Part B2
READ-ONLY INTEGRITY:      ~/cn-spike shows only the pre-existing baseline `M CLAUDE.md`; no partC_v4 file modified
COLUMNS AVAILABLE:        ts_ns, srtt_us, min_rtt_us, recent_min_us, cwnd, queue_est, detect_count,
                          dlv_rate_bps, dlv_rate_compete, dlv_rate_max, mode, probing
FIELDS REQUIRED BUT ABSENT (full Predicate-D reconstruction):
                          compete_enter_jiffies, tcp_jiffies32 (only monotonic ts_ns), last_minrtt_probe_ns, probe_action_start_ns
CSV rows: 33,912   span: 120.047 s
covegas_start_ts -> cubic_rep1_start_ts: +0.00348 s   (covegas launched, then date, ~3.5 ms later)
```

---

## 8. RESULTS

### 8.1 Current-trace scan (`data/historical_a3_existing_trace_scan.md`)

| trace | H present | H alignment-limited | D present | H+D same episode | all D settle-gate exact |
| --- | --- | --- | --- | --- | --- |
| rep1 | **NO** | NO | **NO** | NO | YES |
| rep2 | **NO** | NO | **NO** | NO | YES |
| rep3 | **NO** | NO | **NO** | NO | YES |

**All 9 DELAY→COMPETE transitions — formal classification over the round-3 offset interval:**

| trace | seq | t_event (s) | schedule window `[t+lo, t+hi]` (s) | nearest boundary (s) | phase over interval |
| --- | ---: | ---: | --- | ---: | --- |
| rep1 | 418 | 1.49 | [+0.84, +1.79] | 1.49 | **ROBUST_ON** |
| rep1 | 19995 | 42.23 | [+41.59, +42.53] | 1.54 | **ROBUST_ON** |
| rep1 | 44100 | 84.29 | [+83.64, +84.59] | 2.91 | **ROBUST_ON** |
| rep2 | 418 | 2.02 | [+1.46, +2.32] | 2.02 | **ROBUST_ON** |
| rep2 | 19694 | 42.90 | [+42.34, +43.20] | 2.29 | **ROBUST_ON** |
| rep2 | 41478 | 83.07 | [+82.50, +83.37] | 1.91 | **ROBUST_ON** |
| rep3 | 424 | 1.49 | [+0.79, +1.76] | 1.49 | **ROBUST_ON** |
| rep3 | 21021 | 42.40 | [+41.71, +42.68] | 1.66 | **ROBUST_ON** |
| rep3 | 44373 | 84.15 | [+83.46, +84.43] | 2.73 | **ROBUST_ON** |

Per-trace offset interval: rep1 `[-0.644, +0.298]`, rep2 `[-0.569, +0.295]`, rep3 `[-0.696, +0.276]`.

**Sensitivity table** — phase of each DELAY→COMPETE transition at fixed `Δ` (all 9 rows identical):

| Δ (s) | -1.0 | -0.5 | -0.3 | -0.1 | 0 | +0.12 | +0.3 | +0.5 | +1.0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| phase | ON | ON | ON | ON | ON | ON | ON | ON | ON |

The earliest transition (t ≈ 1.49 s) stays ON down to `Δ ≈ -1.49 s` — robust far beyond the
derived interval.

### 8.2 Predicate D — code path reached, divergent condition did not occur

3 settle-latch guard evaluations per trace (one per COMPETE episode); **all pass**. This is "code
path reached but divergent condition (guard FALSE) did not occur," not "code path never reached."

### 8.3 Historical archive (`data/historical_a3_archive_analysis.json`)

| quantity | value |
| --- | --- |
| documented spurious DELAY→COMPETE | t ≈ 65.51 s, phase = OFF at face value, **unchanged under ±4 s**, nearest boundary **4.11 s** |
| matching revert (COMPETE→DELAY) | t ≈ 66.51 s — **0.998 s** after entry (≈ `RATE_SETTLE_MS`) |
| `dlv_rate_compete` latched in that episode | **never** (max 0) |
| v4 guard at the revert row | `dlv_rate_bps 1,194,436` vs `¾·dlv_rate_max = 897,860` → **guard FALSE → revert** |
| rigorous cross-clock offset bound | **NONE** (CSV has no monotonic anchor) |
| `HISTORICAL_PREDICATE_H` | documented off-period transition; OFF classification **unchanged under ±4 s sensitivity** (not a robustness claim) |
| `HISTORICAL_PREDICATE_D` | **PARTIAL** — guard expression evaluable and FALSE; §4.1 and §4.4 **not** reconstructable from the CSV columns |

### 8.4 Replay-gate regressions (unchanged this session)

```text
Reno v0     R1 / R2  (rep1,rep2,rep3)   -> 0 mismatches / first divergence NONE
CUBIC v1    R3A                          -> 236,042 CLOCK_STABLE events 0 mismatches; 46 CLOCK_AMBIGUOUS, 4 mismatches; non_ambiguous_first_mismatch null  (PARTIAL, unchanged)
CUBIC v1    R3B                          -> first divergence in every trace CLOCK_AMBIGUOUS only  (PARTIAL, unchanged)
CoVegas v2  E2 / E3                      -> 0 mismatches / first divergence NONE
```

---

## 9. IMPORTANT INTERMEDIATE COUNTS (cong_avoid control-flow funnel — unchanged rounds 2→3)

| stage | rep1 | rep2 | rep3 |
| --- | ---: | ---: | ---: |
| `cong_avoid` events (dominant) | 31,348 | 31,151 | 31,683 |
| not cwnd-limited (skipped, GATE 0) | **0** | **0** | **0** |
| cwnd-limited pass | 31,348 | 31,151 | 31,683 |
| minrtt-probe skipped (GATE 1 == 0) | 31,089 | 30,909 | 31,422 |
| COMPETE dispatch (GATE 2) | 5,733 | 5,441 | 5,716 |
| `dlv_rate_compete == 0` block entered (GATE 3) | 312 | 319 | 300 |
| settle-time gate reached / guard evaluated (GATE 4) | **3** | **3** | **3** |
| guard passes | 3 | 3 | 3 |
| guard failures → **Predicate D** | **0** | **0** | **0** |
| settle-gate jiffies-bracket flips | 0 | 0 | 0 |

**Round 1 → 2 → 3:** every count identical. Round 2's cwnd-limited gate removed 0 events (recorder
pre-filters on the kernel `tcp_is_cwnd_limited(sk)`); round 3 changed only the offset derivation.
Where candidates disappear: 31,348 → 5,733 at the minrtt-probe + mode gates; 5,733 → 312 because
`dlv_rate_compete` is non-zero for most of each COMPETE episode; 312 → 3 because the settle-time
gate is satisfied only once per episode.

---

## 10. CLOCK / TIMING / ALIGNMENT AUDIT

### Predicate D (settle-time gate §4.4)

- **Clock:** `tcp_jiffies32`, bracketed as `clock_jiffies32_before` / `_after` (not injected).
- **Method:** `elapsed_jiffies >= 250` evaluated under **both** endpoints;
  `settle_gate_jiffies_bracket_flips` reported. **0 flips** across all 3 traces → every scanned
  classification exactly resolved. All other Predicate-D conditions use recorded PRE state or the
  exact `clock_ktime_ns_before`.

### Predicate H (workload phase) — offset definition and bound

```text
CONVENTION:   Delta = first_dominant_event_wall - cubic_rep1_start_wall
              Delta > 0  <=>  first recorded CoVegas callback is AFTER the `date` that wrote cubic_rep1_start_ts
EVENT ORIGIN:      first_dominant_event.ts_ns          (CLOCK_MONOTONIC, bpf_ktime_get_ns)
SCHEDULE ORIGIN:   cubic_rep1_start_ts                 (CLOCK_REALTIME, date +%s.%N)
COMMON ANCHOR:     NONE (no artifact records both clock domains at one instant)
```

**Harness order (5.1–5.3):** `M0 (creation_ts_ns) < M_attach <= M_seen < M_cov < M_date`, and
`M2 (first data-socket init)` concurrent-after `M_cov`.

| bound | value (rep1 / rep2 / rep3) | type | derivation |
| --- | --- | --- | --- |
| upper | **+0.298 / +0.295 / +0.276 s** | **RIGOROUS** | `Delta ≈ M2 - M_date < M2 - M0 = (first_event.ts_ns - header.creation_ts_ns)`; `M_date > M0` guaranteed by harness order; monotonic/realtime rate diff < ~1 ms/window |
| lower | **-0.644 / -0.569 / -0.696 s** | **LOOSE (derived)** | `Delta ≈ (M2 - M_cov) - eps_date >= base_RTT - eps_date_bound`; `base_RTT = 0.040 s` (topology; control handshake precedes data-socket init); `eps_date_bound = (cubic_rep1_stop - cubic_rep1_start) - 20 s` (cubic ran `-t 20`) = 0.683 / 0.609 / 0.736 s |
| empirical Δ | **+0.129 / +0.123 / +0.123 s (positive)** | context, NOT a bound | `(iperf3 timemillisecs/1000) - cubic_rep1_start_ts`; the data-socket init is at or after that instant, so true Δ ≈ +0.12..+0.20 s |

- **Previous (round-2) interval `[-0.05, +0.30]`:** sign CORRECT (Δ > 0 empirically), upper bound
  RIGOROUS, **lower bound `-0.05` ASSERTED without derivation**. Corrected interval is wider on the
  low side.
- **Distance of classified events from phase boundaries:** 1.49–2.91 s (all 9).
- **Does classification change under the interval?** **No.** Every 9 windows lie in one ON period;
  sensitivity sweep shows ON at every `Δ ∈ {-1 … +1} s`.
- **Historical archive:** no monotonic anchor → **no rigorous cross-clock offset bound.** The
  ~65.51 s event's OFF classification is "unchanged under ±4 s sensitivity" (nearest boundary
  4.11 s) — a sensitivity result, not a robustness claim.

---

## 11. FAILURES / CORRECTIONS DURING THE SESSION

### Correction (round 3) — offset lower bound asserted, not derived

```text
ISSUE:            round-2 user/scan_historical_a3.py used OFFSET_LOWER_PAD_S = -0.05 as the lower
                  edge of the event/schedule offset bracket, with no derivation. Independent review
                  flagged this and raised the possibility of a wrong sign (reading the round-1
                  "ON1 starts at ~0.33s" figure as first_event - cubic_start).
HOW FOUND:        independent review.
WHY IT MATTERED:  the first DELAY->COMPETE transition (~1.5 s) is ~1.5 s from the ON-period start;
                  an unbounded / mis-signed offset could in principle flip its phase.
FIX:              (1) fixed one coordinate convention: Delta = first_event_wall - cubic_rep1_start_wall.
                  (2) established the harness happens-before from the script + recorder source.
                  (3) rigorous upper bound from (first_event.ts_ns - creation_ts_ns); loose lower
                      bound from base_RTT - ((cubic_rep1_stop - cubic_rep1_start) - 20 s).
                  (4) empirical Delta ~= +0.12..+0.20 s from the iperf3 timemillisecs (context only).
                  (5) ROBUST_ON/ROBUST_OFF only over the derived interval; sensitivity table added.
                  The "0.33 s" the reviewer cited is cubic_rep1_start - floor(iperf3 timesecs) --
                  an artifact of the 1-second flooring; against timemillisecs, cubic_rep1_start is
                  ~0.13 s BEFORE the iperf3 timestamp, so Delta > 0.
DID IT INVALIDATE PREVIOUS OUTPUT:  no. Round-2 sign was correct; the classification (Predicate H
                  absent in all 3 traces) is unchanged. Only the offset interval and its labelling
                  changed; the corrected interval is [~ -0.65, +0.30] s, and all 9 transitions are
                  ROBUST_ON over it.
RESULT AFTER FIX: Predicate H absent (ROBUST_ON x9); Predicate D absent; CASE 4 unchanged.
```

### Correction (round 3) — historical-archive "robust" terminology

```text
ISSUE:            round-2 analyze_historical_a3_archive.py labelled the ~65.51 s event
                  "OFF (robust)" based on surviving an arbitrary +-4 s allowance.
FIX:              renamed to "OFF (unchanged under +-4s)"; added rigorous_offset_bound: NONE and
                  the exact review wording. Predicate D archive stays PARTIAL.
```

### Correction (round 3) — statistical wording

```text
ISSUE:            REPORT_HISTORICAL_COVEGAS_REGRESSION.md / data/historical_trigger_validation.md /
                  docs/CURRENT_STATE.md called the 0-trigger campaign "the expected outcome" /
                  "among the single most likely outcomes".
FIX:              -> "Under the rough independence model using the historical 1/9-per-boundary rate,
                  P(0 in 9) ~= 34.6%, so observing zero is plausible and unsurprising at this
                  sample size" (not claimed as the expected or most likely count). "~11%/run"
                  also removed (denominator is boundaries, not runs).
```

### Round-1 / round-2 corrections (carried forward, unchanged)

- **cwnd-limited gate omitted** (round 2): fixed — GATE 0 added; §4.0 in the predicate doc; 0
  event-count change (recorder pre-filters).
- **Predicate-D over-claimed "directly observable"** (round 2): fixed — `tcp_jiffies32` is
  bracketed; settle-gate checked under both endpoints (0 flips).

### No other failures

No compile failure, no verifier issue (no BPF built), no parser bug, no model mismatch, no test
regression.

---

## 12. DOCUMENTATION RECONCILIATION

| stale statement | location | corrected statement | corrected? |
| --- | --- | --- | --- |
| offset lower bound `-0.05` asserted | round-2 `user/scan_historical_a3.py` / `data/historical_a3_predicate_audit.md` §7 | rigorous upper + loose-derived lower (`[~ -0.65, +0.30] s`); empirical Δ ≈ +0.12..+0.20 s | **yes (round 3)** |
| "OFF (robust)" for the ±4 s archive check | round-2 `analyze_historical_a3_archive.py` | "OFF (unchanged under ±4 s)"; `rigorous_offset_bound: NONE` | **yes (round 3)** |
| "the expected outcome" / "single most likely" for the 0-trigger campaign | `REPORT_HISTORICAL_COVEGAS_REGRESSION.md`, `data/historical_trigger_validation.md`, `docs/CURRENT_STATE.md` | "plausible and unsurprising at this sample size" under the rough independence model | **yes (round 3)** |
| "~11%/run" | `docs/CURRENT_STATE.md` §9 | "1 spurious re-entry / 9 off-period boundaries" | **yes (round 3)** |
| Predicate-H phase assumed aligned; cwnd-limited gate missing; Predicate-D over-claimed | round-1 scanner | fixed in round 2 | yes (round 2; re-verified) |
| CoVegas `undo_cwnd` "already separately VALIDATED via Part B" | `REPORT_COVEGAS_REPLAY_FIDELITY.md` | Outcome A — function-level evidence via shared `tcp_reno_undo_cwnd`; ABI-v2 path unexercised | yes (`bb0fb3e`; re-verified) |
| "1 of 9 runs", "P(0/3)≈70%" | historical-trigger docs | 3 runs / 9 boundaries / 1; `(8/9)^9 ≈ 34.6%` | yes (`bb0fb3e`; re-verified) |
| 4-event clock table unscoped | `REPORT_CUBIC_CLOCK_BOUNDARY_INVESTIGATION.md` | Table 2a (4 production mismatches) vs Table 2b (all 46: `2/4/40/0`) | yes (`bb0fb3e`; re-verified) |

**Recurring-hazard statements re-verified unchanged this session:** CUBIC R3 = **PARTIAL**;
full-46 clock attribution `MATCHES_BEFORE_ONLY 2 / AFTER_ONLY 4 / BOTH 40 / NEITHER 0`; ~780 ns
window **inferred from tick-collision probability**, not measured; CoVegas `undo_cwnd` = Outcome A;
CoVegas `clock_ktime_ns_before` = exact controller-consumed value for `init`/`cong_avoid`;
historical trigger denominator = **off-period boundaries, not runs**; no `~11%/run`; no
`P(0/3)≈70%`; no general `byte-exact`/`bit-exact`; historical CoVegas case = **INCOMPLETE**, not
FAIL; **no historical A3 localization claim**.

---

## 13. REGRESSION / INTEGRITY VALIDATION

```text
AUTOMATED TESTS:   python3 -m unittest discover -s tests   ->  Ran 40 tests ... OK   (26 v0 + 14 v1)

RENO v0:           for r in rep1 rep2 rep3: replay_r1.py / replay_r2.py  ->  PASS / first divergence NONE

CUBIC v1:          replay_r3a.py rep{1,2,3}  ->  total_mismatches 4 ; clock_stable_mismatched 0 ;
                                                 non_ambiguous_first_mismatch null   (PARTIAL, unchanged)
                   replay_r3b.py rep{1,2,3}  ->  pass_first_divergence_is_only_clock_ambiguous: true   (PARTIAL, unchanged)

COVEGAS v2:        replay_e2.py rep{1,2,3}   ->  "pass": true ; total_mismatches 0
                   replay_e3.py rep{1,2,3}   ->  "pass": true ; first_divergence null

SOURCE REPO INTEGRITY:
                   ~/cn-spike  git rev-parse --short HEAD -> 022c2e2
                               git status --porcelain | grep '^ M' -> " M CLAUDE.md"  (1; pre-existing baseline, docs/PROVENANCE.md)
                   no file under ~/cn-spike/covegas/raw/partC_v4/ modified (read-only analysis only)

WORKING TREE (~/ccreplay after commit):
                   clean except the standing untracked exceptions:
                     ?? docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md   (task-instructions, never committed)
                     ?? instructions.md                               (stray lowercase, never committed)
                   docs/session/LATEST_REVIEW_HANDOFF.md is committed (this file).
```

No mandatory regression skipped.

---

## 14. GIT ORDERING / PRECOMMIT EVIDENCE

```text
Predicate definitions committed:   d9677dc  (data/historical_a3_predicate_audit.md, round 1)
Round-2 correction commit:          45aa0ff
Round-3 correction commit:          <this session's commit>
Ordering:                           predicate definitions PRECEDE every scan result.
```

Rounds 2 and 3 **added** conditions / derivations to the predicate definition; **no round relaxed a
condition, moved a threshold, changed the guard expression, or changed the same-episode rule**. The
interpretation matrix (CASE 1–4) was fixed in the task prompt before any result.
`data/historical_regression_predictions.md` (the historical buggy-vs-fixed precommit) is untouched
and unresolved — no diff has run.

---

## 15. ADVERSARIAL SELF-CHECK

```text
Did this session redefine a criterion after seeing an unfavorable result?
  NO. The offset interval was re-derived (wider, better-justified); the predicate thresholds,
  guard expression, and same-episode rule are unchanged. The result (Predicate H absent) is the
  same as rounds 1 and 2.

Did this session weaken an oracle?
  NO. No replay oracle touched; all replay-gate regressions re-run and unchanged.

Did this session change a prediction after results?
  NO. data/historical_regression_predictions.md untouched.

Did this session infer an unrecorded state value?
  NO. Current-trace Predicate D uses recorded PRE state + clock_ktime_ns_before (exact) + both
  jiffies bracket endpoints. Historical Predicate D stays PARTIAL -- §4.1 and §4.4 reported as
  NOT reconstructable, not inferred. The empirical Delta from iperf3 timemillisecs is labelled
  "context, not a bound".

Did this session treat a diagnostic timestamp as an exact controller input?
  NO. clock_ktime_ns_after unused. clock_jiffies32 treated as bracketed. creation_ts_ns used only
  to bound an offset. iperf3 timemillisecs used only as context, not a bound.

Did this session conflate historical symptom H with implementation divergence D?
  NO. Defined separately, scanned separately, same-episode rule reported separately. Both absent
  in the current traces (CASE 4).

Did this session use a denominator inconsistent with the underlying trials?
  NO. Historical trigger denominator = 9 off-period boundaries from 3 HOLD_MS=500 runs;
  P(0 in 9) = (8/9)^9 ~= 34.6% labelled rough/binomial/independence-assumption; "expected outcome"
  wording removed.

Did this session claim counterfactual network behavior from replay?
  NO. No throughput/RTT/queue claim.

Did this session convert INCOMPLETE into FAIL or PASS without new evidence?
  NO. Historical CoVegas case = INCOMPLETE. CUBIC R3 = PARTIAL. CoVegas self-replay = PASS.

Did this session claim a "rigorous" bound that is not?
  NO. The upper offset bound is labelled RIGOROUS (from creation_ts_ns + guaranteed harness order);
  the lower bound is labelled LOOSE (derived from base RTT and the cubic-rep1 excess-over-20s);
  the empirical Delta is labelled "context, not a bound"; the historical archive is labelled
  "no rigorous cross-clock offset bound".
```

---

## 16. CURRENT AUTHORITATIVE RESULT

```text
OFFSET DEFINITION:  Delta = first_dominant_event_wall - cubic_rep1_start_wall  (Delta > 0 => event AFTER schedule anchor)
HARNESS ORDER:      M0 creation_ts_ns < M_attach <= M_seen < M_cov (covegas iperf3 &) < M_date (date > cubic_rep1_start_ts);
                    M2 (first data-socket init) concurrent-after M_cov
OFFSET INTERVAL:    Delta in [~ -0.65, +0.30] s   (upper RIGOROUS; lower LOOSE-derived; empirical Delta ~ +0.12..+0.20 s, positive)

PREDICATE H:   DELAY->COMPETE transition; schedule window [t+offset_lo, t+offset_hi] entirely in an OFF period (ROBUST_OFF).
PREDICATE D:   cong_avoid event; control flow reaches handle_compete_mode's settle-latch guard
               (cwnd-limited; handle_minrtt_probe==0; mode==COMPETE; dlv_rate_compete==0;
                elapsed_jiffies >= 250 under BOTH jiffies bracket endpoints; dlv_rate_bps != 0)
               AND the v4 guard is FALSE (dlv_rate_bps >= (dlv_rate_max*3)/4).
H+D SAME-EPISODE RULE:  guard-failing settle-latch event whose COMPETE episode was entered by a Predicate-H transition.

rep1:  H = NO (ROBUST_ON x3)   D = NO   H+D = NO
rep2:  H = NO (ROBUST_ON x3)   D = NO   H+D = NO
rep3:  H = NO (ROBUST_ON x3)   D = NO   H+D = NO
       (per trace: 3 COMPETE episodes, all entered ON; 3 settle-latch guard evaluations, all pass;
        0 settle-gate jiffies-bracket flips)

HISTORICAL ARCHIVE (Ph500_B5x_rep2, read-only):
       documented ~65.51 s off-period DELAY->COMPETE transition; OFF classification unchanged under
       a +/-4 s sensitivity analysis (nearest boundary 4.11 s); NO rigorous cross-clock offset bound.
       Predicate D = PARTIAL (v4 guard expression evaluable and FALSE at the t~=66.51 s revert;
       dlv_rate_compete never latched; §4.1 and §4.4 not reconstructable from the CSV columns).
       -> validates the detector; does NOT provide a v2 differential-replay candidate.

CURRENT CASE CLASSIFICATION:  CASE 4 -- neither Predicate H nor Predicate D present in any current v2 trace.
DID THIS CORRECTION CHANGE CASE 4:  NO.

HISTORICAL DIFF AUTHORIZED BY EVIDENCE:  NO
A3 AUXILIARY MECHANISM DIFF AVAILABLE:   NO
```

---

## 17. EXACT NEXT DECISION

```text
NEXT PROJECT-LEVEL DECISION (requires external review -- no option executed this session):

A. Authorize another predeclared HOLD_MS=500 historical-trigger capture campaign aimed at a
   trigger-positive Replay ABI v2 trace (Predicate H present in an OFF period). Only such a trace
   can support the historical buggy-vs-fixed differential replay OR an auxiliary A3
   mechanism-localization diff -- the three existing traces support neither.

B. Freeze the historical CoVegas A3 case as INCOMPLETE (trigger-availability blocker, not a
   failure; CoVegas self-replay PASS and CUBIC R3 PARTIAL both unaffected) and move to
   professor-demo packaging of the completed differential-debugger / checkpoint-reproducer results
   (N4-N6).

C. Another option supported by this session's evidence (e.g. a longer / multi-rep single capture;
   or a predeclared decision to accept the historical-archive same-episode H + guard-FALSE as
   sufficient qualitative evidence that the A3 mechanism is real, without a CCReplay v2 diff).

NO OPTION EXECUTED IN THIS SESSION.
```

---

## 18. COPY-PASTE REVIEW SUMMARY

```text
CCReplay -- Predicate-H time-origin final correction (round 3)
date 2026-09-05 | starting commit 45aa0ff | offline, read-only | STOP for review

FORMAL VERDICTS (unchanged):
  CUBIC R3                     PARTIAL   (R3B "first divergence = NONE" not met; residual CLOCK_AMBIGUOUS only)
  CoVegas self-replay (E1-E3)  PASS      (190,277 events, 4,982,990 comparisons, 0 mismatches; E3 first divergence NONE x3)
  Historical CoVegas A3 case   INCOMPLETE (trigger not reproduced; buggy-vs-fixed diff NOT run / not authorized)

CUBIC full-46 clock attribution: MATCHES_BEFORE_ONLY 2 / AFTER_ONLY 4 / BOTH 40 / NEITHER 0
  (4-event table = production-convention mismatches only; ~780 ns window inferred from tick-collision probability, not measured)
CoVegas undo_cwnd:  Outcome A (function-level via shared tcp_reno_undo_cwnd; ABI-v2 path unexercised; 0 events)
CoVegas ktime:      clock_ktime_ns_before = exact controller-consumed value (init/cong_avoid); _after diagnostic-only

THIS SESSION -- offset re-derivation:
  OFFSET DEFINITION:  Delta = first_dominant_event_wall - cubic_rep1_start_wall  (>0 => event AFTER schedule anchor)
  HARNESS ORDER:      M0 creation_ts_ns (after bpf__load, before bpf__attach) < M_attach <= M_seen
                      < M_cov (covegas iperf3 &) < M_date (date > cubic_rep1_start_ts);
                      M2 (first data-socket init) concurrent-after M_cov
  PREVIOUS INTERVAL:  [-0.05, +0.30] s  -- sign CORRECT, upper RIGOROUS, lower -0.05 ASSERTED (not derived)  -> NOT valid as stated
  CORRECTED INTERVAL: rep1 [-0.644,+0.298]  rep2 [-0.569,+0.295]  rep3 [-0.696,+0.276]  s
  BOUND TYPE:         upper = RIGOROUS (first_event.ts_ns - header.creation_ts_ns; M_date > M0 guaranteed)
                      lower = LOOSE (base_RTT 0.040 - eps_date_bound; eps_date_bound = (cubic_rep1_stop - cubic_rep1_start) - 20s)
                      empirical Delta = +0.129 / +0.123 / +0.123 s  (iperf3 timemillisecs - cubic_rep1_start; positive)

ALL 9 DELAY->COMPETE TRANSITIONS:
  rep1 seq 418  t=1.49  win [+0.84,+1.79]  nb 1.49  ROBUST_ON
  rep1 seq 19995 t=42.23 win [+41.59,+42.53] nb 1.54 ROBUST_ON
  rep1 seq 44100 t=84.29 win [+83.64,+84.59] nb 2.91 ROBUST_ON
  rep2 seq 418  t=2.02  win [+1.46,+2.32]  nb 2.02  ROBUST_ON
  rep2 seq 19694 t=42.90 win [+42.34,+43.20] nb 2.29 ROBUST_ON
  rep2 seq 41478 t=83.07 win [+82.50,+83.37] nb 1.91 ROBUST_ON
  rep3 seq 424  t=1.49  win [+0.79,+1.76]  nb 1.49  ROBUST_ON
  rep3 seq 21021 t=42.40 win [+41.71,+42.68] nb 1.66 ROBUST_ON
  rep3 seq 44373 t=84.15 win [+83.46,+84.43] nb 2.73 ROBUST_ON
  sensitivity: phase = ON at every Delta in {-1.0,-0.5,-0.3,-0.1,0,+0.12,+0.3,+0.5,+1.0} s for all 9

PREDICATE H:  rep1 NO   rep2 NO   rep3 NO   (ROBUST_ON x9; no ALIGNMENT_LIMITED)
PREDICATE D:  rep1 NO   rep2 NO   rep3 NO   (3 settle-latch guard evals per trace, all pass; 0 jiffies-bracket flips)

HISTORICAL ARCHIVE (~/cn-spike/covegas/raw/partC_v4/Ph500_B5x_rep2_ringbuf.csv, read-only):
  documented ~65.51 s off-period DELAY->COMPETE; OFF classification unchanged under +/-4 s sensitivity (nb 4.11 s)
  NO rigorous cross-clock offset bound (CSV has no monotonic anchor)
  Predicate D = PARTIAL  (v4 guard expr FALSE at t~=66.51 s revert: dlv_rate_bps 1,194,436 >= 3/4 * 1,197,147 = 897,860;
                          dlv_rate_compete never latched; revert 0.998 s after entry;
                          settle-time gate + minrtt-probe gate NOT reconstructable from the CSV columns)

STATISTICAL WORDING:  0-trigger campaign now "plausible and unsurprising at this sample size" (P(0 in 9) ~= 34.6%);
                      NOT "the expected outcome" / "most likely count"; "~11%/run" removed (denominator = boundaries)

INTERPRETATION: CASE 4 -- neither predicate present in any current trace.  DID THIS CHANGE CASE 4: NO.
  HISTORICAL DIFF CANDIDATE AVAILABLE: NO   A3 MECHANISM-DIFF CANDIDATE AVAILABLE: NO

REGRESSIONS: unittest 40/40 OK | Reno R1/R2 PASS | CUBIC R3A/R3B unchanged PARTIAL | CoVegas E2 0 mismatches | E3 first divergence NONE
SOURCE REPOS: ~/cn-spike at 022c2e2, only pre-existing baseline `M CLAUDE.md`; partC_v4 untouched
NEW NETWORK CAPTURES: NO | HISTORICAL DIFF RUN: NO
COMMIT: <this session's commit -- git log>  | WORKING TREE: clean except standing untracked exceptions
        (docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md, instructions.md)

NEXT DECISION (external review; nothing executed):
  A. authorize a predeclared HOLD_MS=500 capture campaign for a trigger-positive v2 trace
  B. freeze historical A3 case as INCOMPLETE, move to demo packaging (N4-N6)
  C. another evidence-supported option
```

---

*For external review, send only:* `docs/session/LATEST_REVIEW_HANDOFF.md`
