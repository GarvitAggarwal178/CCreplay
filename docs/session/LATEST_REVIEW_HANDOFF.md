# CCReplay — Latest Session Review Handoff

**One-file review packet.** A reviewer who already understands CCReplay's architecture should be
able to audit this session by reading only this file. Individual reports, data files, scripts,
source files, and git history remain authoritative for their respective evidence; this file is a
self-contained snapshot. Every future bounded CCReplay session replaces this file.

---

## 1. SESSION IDENTITY

```text
SESSION:                 A3 scanner control-flow correction + workload phase-alignment audit
                         (round-2 correction to the just-completed A3 predicate audit)
DATE:                    2026-09-05
STARTING COMMIT:         d9677dc  "docs+audit: A3 divergence predicate + evidence reconciliation round 2"
ENDING COMMIT:           <this session's commit>  (see §13 / §18)
TASK STATUS:             COMPLETE — offline, read-only; STOP for project-level review
FORMAL VERDICTS CHANGED: NO   (CUBIC R3 = PARTIAL, CoVegas self-replay = PASS, historical case = INCOMPLETE)
NEW NETWORK CAPTURES:    NO
NEW DIFFERENTIAL REPLAY: NO
```

Two earlier commits in the same overall work stream:

- `bb0fb3e` — "docs: add authoritative CCReplay current-state handoff" (created `docs/CURRENT_STATE.md`,
  full-46 CUBIC clock attribution, historical-trigger denominator corrections, CoVegas `undo_cwnd`
  Outcome-A classification, CoVegas ktime dataflow trace).
- `d9677dc` — round-1 A3 predicate audit (derived Predicate D from source, built
  `user/scan_historical_a3.py` and `data/audit_src/analyze_historical_a3_archive.py`, scanned the
  three CoVegas traces, validated against the historical archive positive).

**Exact bounded goal of this session:** independent review found two implementation issues in the
round-1 A3 scanner. Fix both, without new captures / differential replay / other evaluation:

1. **Missing cwnd-limited gate.** The real CoVegas `cong_avoid` path checks
   `tcp_is_cwnd_limited(...)` *before* `handle_minrtt_probe()` and mode dispatch; the round-1
   scanner omitted this, inspecting an over-inclusive event set. Add the gate in the correct
   position; re-derive Predicate D's prerequisites; re-run; report before/after counts; record the
   correction (do not silently replace round-1 output).
2. **Predicate-H time-alignment not proven.** The schedule (`CLOCK_REALTIME`, `date +%s.%N`) and the
   event stream (`CLOCK_MONOTONIC`, `bpf_ktime_get_ns`) have not been shown to share a zero point.
   Search artifacts for a common anchor; if none, establish a defensible offset bound and classify
   Predicate H only where the phase is invariant over that bound.

Plus: apply the same time-origin reasoning to the historical archive; add a clock qualification for
Predicate D (jiffies stays bracketed); and finish a short list of documentation reconciliations.

---

## 2. BINDING CLAIM BOUNDARY

> CCReplay answers what a congestion-control implementation computes at a recorded callback
> boundary. It does not claim what network trajectory or performance that implementation would have
> produced.

Load-bearing semantic rules for this session:

- Mode B injects recorded shared TCP boundary state at every callback; controller-private state
  evolves; Linux TCP between callbacks is not simulated.
- "Exact" = exact semantic equality under the declared comparison schema. No general `byte-exact` /
  `bit-exact`.
- An oracle is never weakened to obtain PASS.
- **Predicate H (historical off-period *symptom* trigger) and Predicate D (A3 *implementation*
  divergence condition) are related but not identical.** This session must not conflate them, and
  must not claim the historical A3 regression has been localized (the buggy-vs-fixed differential
  replay has not run and is not authorized).
- CUBIC `tcp_jiffies32` is a bracketed quantity (`clock_jiffies32_before` / `_after`), not an
  injected exact value. No classification may silently pick the endpoint that gives a desired
  answer.

---

## 3. PRECOMMITTED / PRE-EXISTING CRITERIA

All three predicates were fixed in `data/historical_a3_predicate_audit.md` **before** any scan
result was produced (round 1, committed `d9677dc`; round 2 only *added* condition §4.0 and the
alignment-robustness qualifier — it did not relax any condition or change any threshold).

### Predicate H — historical off-period symptom trigger (committed `d9677dc`, refined this session)

> A `cong_avoid` event with `priv_pre_mode == DELAY` and `priv_post_mode == COMPETE` (a real
> DELAY→COMPETE transition on that event) whose wall-clock time falls in a cross-traffic OFF
> period — **asserted only if the phase is invariant over the event/schedule clock-offset bracket
> (§10)**; otherwise `ALIGNMENT-LIMITED`, not H.

### Predicate D — A3 implementation-divergence condition (source-derived; §5 below)

> A `cong_avoid` event where, evaluating the deterministic control flow on the recorded PRE state +
> recorded controller-visible clocks, conditions §4.0–§4.5 all hold **and** the v4 guard §5 is
> FALSE (`priv_pre_dlv_rate_bps >= (priv_pre_dlv_rate_max * 3) / 4`).
>
> §4.0 cwnd-limited · §4.1 `handle_minrtt_probe` returns 0 · §4.2 `priv_pre_mode == COMPETE` ·
> §4.3 `priv_pre_dlv_rate_compete == 0` · §4.4 `(u32)(clock_jiffies32_before −
> priv_pre_compete_enter_jiffies) >= 250` · §4.5 `priv_pre_dlv_rate_bps != 0`.
>
> On a Predicate-D event, reconstructed-v3 (unconditional latch → `cubic_growth`) and fixed-v4
> (`revert_to_delay` → `return`) produce different declared results / semantic state.

### Same-episode H+D rule (committed `d9677dc`, not revised)

> For the historical regression to be trigger-positive in the strongest sense, one COMPETE episode
> must contain both Predicate H (its DELAY→COMPETE entry during an OFF period) and Predicate D (a
> later guard-failing settle-latch evaluation in that same episode).

### Interpretation matrix (from the task prompt, fixed before results)

```text
CASE 1  H + D in the same episode (in a current v2 trace)  -> HISTORICAL DIFF CANDIDATE = YES (do not run)
CASE 2  D present, not linked to an OFF-period H            -> A3 MECHANISM-DIFF CANDIDATE = YES; HISTORICAL = NO
CASE 3  H present but D does not fail                       -> trigger-like episode present, differential condition absent
CASE 4  neither present                                     -> NO EXISTING DIFF CANDIDATE
```

No criterion, threshold, or matrix branch was changed after seeing results.

---

## 4. FILES CHANGED

### `git diff --stat` (this session, on top of `d9677dc`)

```text
 REPORT_DEVELOPMENT_SESSION_INDEX.md                |   3 +-
 REPORT_EVIDENCE_RECONCILIATION_AND_A3_PREDICATE_AUDIT.md | 133 ++++++-
 data/audit_src/analyze_historical_a3_archive.py    |  55 ++-
 data/historical_a3_archive_analysis.json           |  38 +-   (generated)
 data/historical_a3_existing_trace_scan.json        | 234 +++++----   (generated)
 data/historical_a3_existing_trace_scan.md          | 215 +++++-----   (generated)
 data/historical_a3_predicate_audit.md              | 103 ++++-
 docs/CURRENT_STATE.md                              |  10 +
 user/scan_historical_a3.py                         | 441 ++++++++--------
 9 files changed, 873 insertions(+), 359 deletions(-)
 (+ this file, docs/session/LATEST_REVIEW_HANDOFF.md, new)
```

### Change table

| file | purpose of change | class |
| --- | --- | --- |
| `user/scan_historical_a3.py` | add cwnd-limited gate before `handle_minrtt_probe`; add artifact-derived event/schedule offset bracket + phase-robustness classification; add settle-gate jiffies-bracket sensitivity; emit before/after count table | **analysis-script semantic change** (offline scanner only — not recorder/parser/model) |
| `data/audit_src/analyze_historical_a3_archive.py` | anchor schedule to `cubic_rep1_start_ts`; add time-alignment note + robust-phase classification + nearest-boundary distances | analysis-script semantic change (offline, read-only) |
| `data/historical_a3_predicate_audit.md` | add §4.0 (cwnd-limited), §7 (time alignment), clock qualification, alignment-robust Predicate-H definition | docs |
| `REPORT_EVIDENCE_RECONCILIATION_AND_A3_PREDICATE_AUDIT.md` | append "Round-2 correction" section | docs |
| `docs/CURRENT_STATE.md` | §10: note Predicate H/D absent, H shown robust to offset bracket | docs |
| `REPORT_DEVELOPMENT_SESSION_INDEX.md` | split round-1 / round-2 rows | docs |
| `data/historical_a3_*.json`, `data/historical_a3_existing_trace_scan.md` | regenerated scanner outputs | generated (summarized in §8/§9) |

**No recorder / parser / replay-model / trace-format file was changed.** `bpf/*`, `user/ccr_*.py`,
`user/covegas_model.py`, `user/replay_*.py` are untouched.

### Semantic diff hunk — `user/scan_historical_a3.py` (the cwnd-limited gate)

```python
 from user.covegas_model import (
-    pre_from_event, private_pre_from_event, handle_minrtt_probe,
+    pre_from_event, private_pre_from_event, handle_minrtt_probe, tcp_is_cwnd_limited,
     u32, RATE_SETTLE_MS, CONFIG_HZ, CCR_CB_CONG_AVOID,
 )
...
+def cwnd_limited(e):
+    pre = pre_from_event(e)
+    return tcp_is_cwnd_limited(pre["snd_cwnd"], pre["snd_ssthresh"],
+                               pre["max_packets_out"], pre["is_cwnd_limited"])
...
     for e in dom:
         if e["callback_id"] != CCR_CB_CONG_AVOID:
             continue
+
+        # GATE 0 (NEW): cwnd-limited, exactly as the model's cong_avoid path
+        # checks BEFORE handle_minrtt_probe / dispatch.
+        if not cwnd_limited(e):
+            counts["not_cwnd_limited"] += 1
+            continue
+        counts["cwnd_limited_pass"] += 1
+
         ca = private_pre_from_event(e)
         pre = pre_from_event(e)
         ktime_now = e["clock_ktime_ns_before"]
         jiffies_now = e["clock_jiffies32_before"]
         probe_ran, _, _ = handle_minrtt_probe(dict(ca), pre, ktime_now, jiffies_now)
         if probe_ran:
             continue
+        counts["minrtt_probe_skipped"] += 1
         if ca["mode"] != MODE_COMPETE:
             continue
+        counts["compete_dispatch"] += 1
         if ca["dlv_rate_compete"] != 0:
             continue   # rate-jump revert branch: identical in v3 and v4
+        counts["dlv_rate_compete_zero_block"] += 1
         ej = u32(u32(jiffies_now) - ca["compete_enter_jiffies"])
         if not (ej >= SETTLE_THRESHOLD_JIFFIES and ca["dlv_rate_bps"]):
             continue
+        counts["settle_time_gate_reached"] += 1
+        # jiffies bracket sensitivity of the settle-time gate
+        ej_after = u32(u32(e["clock_jiffies32_after"]) - ca["compete_enter_jiffies"])
+        gate_flips = (ej >= SETTLE_THRESHOLD_JIFFIES) != (ej_after >= SETTLE_THRESHOLD_JIFFIES)
+        ...
         if guard_passes(ca):
             counts["guard_passes"] += 1
             continue
+        counts["guard_failures"] += 1        # Predicate D
```

### Semantic diff hunk — offset bracket / phase robustness

```python
OFFSET_LOWER_PAD_S = -0.05   # absorbs `date` exec time + monotonic-vs-realtime slew

# in scan_trace():
offset_hi = (dom[0]["ts_ns"] - hdr.creation_ts_ns) / 1e9   # rigorous upper bound on the offset
offset_lo = OFFSET_LOWER_PAD_S
on_periods = build_schedule(prefix)    # anchored to cubic_rep1_start_ts.txt (date +%s.%N)

# for each DELAY->COMPETE transition at event-relative time t:
lo, hi = t + offset_lo, t + offset_hi
phase_bracketed(lo, hi, on_periods)    # 'ON' / 'OFF' iff whole [lo,hi] in one phase, else 'ALIGNMENT-LIMITED'
# Predicate H asserted only for phase_bracketed == 'OFF'
```

---

## 5. RELEVANT SOURCE / MODEL / SCANNER EXCERPTS

### 5.1 CoVegas `cong_avoid` dispatch (the control flow leading into the A3 decision)

```text
FILE:        ~/cn-spike/covegas/src/covegas.bpf.c   (the only committed version — the selected FIXED/v4 reference)
LINE RANGE:  ~846-860  (covegas_cong_avoid entry)
COMMIT:      repo HEAD bab7ab7; file last touched at b5bc0be "v4"  (docs/PROVENANCE.md)
```

```c
    __u64 now = bpf_ktime_get_ns();
    ...
    if (!tcp_is_cwnd_limited(sk))          /* GATE 0  -- new in the round-2 scanner */
        return;                            /* (in the CCReplay recorder: before seq alloc / record) */
    if (handle_minrtt_probe(tp, ca, now))  /* GATE 1 */
        return;
    if (ca->mode == MODE_COMPETE)          /* dispatch */
        handle_compete_mode(tp, ca, acked);
    else
        handle_delay_mode(tp, ca, ack, acked);
```

CCReplay recorder — same gate, made explicit and hoisted above recording:

```text
FILE:        bpf/covegas_wrapper.bpf.c
LINE RANGE:  ~737-761  (ccr_covegas_cong_avoid)
```

```c
SEC("struct_ops")
void BPF_PROG(ccr_covegas_cong_avoid, struct sock *sk, __u32 ack, __u32 acked)
{
    ...
    __u64 seq, now = bpf_ktime_get_ns();     /* single shared read (see ktime section, §11 / prior handoff) */
    struct ccr_event_v2 *e = NULL;

    if (!tcp_is_cwnd_limited(sk))
        return;                              /* NOT recorded -- no seq allocated */
    ...
    if (!handle_minrtt_probe(tp, ca, now)) {
        if (ca->mode == MODE_COMPETE)
            handle_compete_mode(tp, ca, acked);
        else
            handle_delay_mode(tp, ca, ack, acked);
    }
    ...
}
```

### 5.2 `handle_compete_mode` — the A3 settle-latch (v4)

```text
FILE:        ~/cn-spike/covegas/src/covegas.bpf.c
LINE RANGE:  697-715   (byte-identical in bpf/covegas_wrapper.bpf.c lines 424-443)
```

```c
static void handle_compete_mode(struct tcp_sock *tp, struct covegas *ca, __u32 acked)
{
    if (ca->dlv_rate_compete == 0) {
        __u32 elapsed_jiffies = tcp_jiffies32 - ca->compete_enter_jiffies;

        if (elapsed_jiffies >= (RATE_SETTLE_MS * HZ) / 1000 && ca->dlv_rate_bps) {
            if (ca->dlv_rate_bps < (ca->dlv_rate_max * 3) / 4) {
                ca->dlv_rate_compete = ca->dlv_rate_bps;          /* LATCH -- v3 and v4 agree here */
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

**Reconstructed v3** (`data/historical_regression_selection.md`): the guard is replaced by an
unconditional latch — `if (elapsed_jiffies >= ... && ca->dlv_rate_bps) { ca->dlv_rate_compete =
ca->dlv_rate_bps; }`. A1 and A2 stay at v4 (A3 isolated). **Divergence occurs iff the guard
expression is FALSE** while the settle-latch block is entered (`dlv_rate_compete == 0`, settle time
elapsed, `dlv_rate_bps != 0`): v4 reverts + returns, v3 latches + falls to `cubic_growth`.

### 5.3 `handle_minrtt_probe` (GATE 1 — determines whether the mode dispatch runs)

```text
FILE:        ~/cn-spike/covegas/src/covegas.bpf.c
LINE RANGE:  606-662   (mirrored: user/covegas_model.py handle_minrtt_probe, lines 293-330)
```

Returns non-zero if `ca->minrtt_probing` (PRE) is set, or if
`now - ca->last_minrtt_probe_ns >= period_ns` where `period_ns = MINRTT_PERIOD_MS*1e6` (10 s) in
the Predicate-D pre-state (`mode==COMPETE && dlv_rate_compete==0`). Returns 0 (dispatch runs) iff
`priv_pre_minrtt_probing == 0` **and** `clock_ktime_ns_before - priv_pre_last_minrtt_probe_ns < 10e9`.
`now` is the exact `clock_ktime_ns_before` value (single shared read; established in the prior
handoff / `REPORT_COVEGAS_REPLAY_FIDELITY.md`).

### 5.4 `tcp_is_cwnd_limited` (GATE 0)

```text
FILE:        user/covegas_model.py
LINE RANGE:  222-229   (matches the kernel's static inline; the CCReplay recorder calls the real kfunc)
```

```python
def tcp_in_slow_start(cwnd, ssthresh):
    return cwnd < ssthresh

def tcp_is_cwnd_limited(cwnd, ssthresh, max_packets_out, is_cwnd_limited_bit):
    if tcp_in_slow_start(cwnd, ssthresh):
        return cwnd < 2 * max_packets_out
    return bool(is_cwnd_limited_bit)
```

Model cong_avoid entry (`user/covegas_model.py` lines 523-533) — the gate is checked *first*, with
an early return that leaves state unchanged, then `handle_minrtt_probe`, then dispatch:

```python
if cb == CCR_CB_CONG_AVOID:
    if not tcp_is_cwnd_limited(pre["snd_cwnd"], pre["snd_ssthresh"],
                               pre["max_packets_out"], pre["is_cwnd_limited"]):
        out = {... POST == PRE ...}
        return out, ca
    probe_ran, next_ca, cwnd_override = handle_minrtt_probe(ca, pre, ktime_now, jiffies_now)
    ...
    elif next_ca["mode"] == MODE_COMPETE:
        post_cwnd, post_cwnd_cnt, next_ca = handle_compete_mode(next_ca, pre, event["in_acked"], jiffies_now)
```

### 5.5 Model `handle_compete_mode` (what the scanner's guard check mirrors)

```text
FILE:        user/covegas_model.py
LINE RANGE:  360-379
```

```python
def handle_compete_mode(ca, pre, acked, jiffies_now):
    ca = dict(ca); cwnd = pre["snd_cwnd"]; cwnd_cnt = pre["snd_cwnd_cnt"]
    if ca["dlv_rate_compete"] == 0:
        elapsed_jiffies = u32(u32(jiffies_now) - ca["compete_enter_jiffies"])
        if elapsed_jiffies >= (RATE_SETTLE_MS * CONFIG_HZ) // 1000 and ca["dlv_rate_bps"]:
            if ca["dlv_rate_bps"] < (ca["dlv_rate_max"] * 3) // 4:
                ca["dlv_rate_compete"] = ca["dlv_rate_bps"]
            else:
                cwnd, ca = revert_to_delay(ca, pre, jiffies_now)
                return cwnd, cwnd_cnt, ca
    elif ca["dlv_rate_bps"] > (RATE_JUMP_NUM * ca["dlv_rate_compete"]) // RATE_JUMP_DEN:
        cwnd, ca = revert_to_delay(ca, pre, jiffies_now)
        return cwnd, cwnd_cnt, ca
    cwnd2, cwnd_cnt2, ca = cubic_growth(ca, pre, acked, jiffies_now)
    return cwnd2, cwnd_cnt2, ca
```

`RATE_SETTLE_MS = 1000`, `CONFIG_HZ = 250` → settle threshold = **250 jiffies**.

---

## 6. ANALYSIS / DETECTOR IMPLEMENTATION

Full script: `user/scan_historical_a3.py` (offline, read-only; ~300 lines). Committed with this
session. Complete decision logic:

**Connection selection:** `select_dominant_connection(events)` (from `user/ccr_trace.py`, the
validated ADR-016 selector) — picks the socket with the most events; the other socket (1 stray
event per trace, the iperf3 control channel) is excluded. Events sorted by `seq`.

**Predicate D, per `cong_avoid` event of the dominant connection:**

```text
reconstruct ca  = {f: e["priv_pre_"+f] for f in ALL_PRIVATE_FIELDS}
reconstruct pre = pre_from_event(e)     # pre_snd_cwnd, pre_snd_ssthresh, ... pre_srtt_us
ktime_now   = e["clock_ktime_ns_before"]     # exact controller-consumed value
jiffies_now = e["clock_jiffies32_before"]

GATE 0  if not tcp_is_cwnd_limited(cwnd, ssthresh, max_packets_out, is_cwnd_limited): skip
GATE 1  if handle_minrtt_probe(dict(ca), pre, ktime_now, jiffies_now)[0]: skip
GATE 2  if ca["mode"] != MODE_COMPETE: skip
GATE 3  if ca["dlv_rate_compete"] != 0: skip     # rate-jump branch, identical v3/v4
GATE 4  ej = u32(u32(jiffies_now) - ca["compete_enter_jiffies"])
        if not (ej >= 250 and ca["dlv_rate_bps"]): skip
        # jiffies bracket sensitivity:
        ej_after = u32(u32(e["clock_jiffies32_after"]) - ca["compete_enter_jiffies"])
        gate_flips = (ej >= 250) != (ej_after >= 250)      # tracked; 0 across all traces
GUARD   if ca["dlv_rate_bps"] < (ca["dlv_rate_max"] * 3) // 4:  guard_passes += 1 ; skip
        else:  guard_failures += 1   ->  PREDICATE D
```

**Predicate H, per DELAY→COMPETE transition (`priv_pre_mode==0 && priv_post_mode==1`):**

```text
t   = (e["ts_ns"] - first_dominant_event["ts_ns"]) / 1e9          # CLOCK_MONOTONIC-relative
offset_hi = (first_dominant_event["ts_ns"] - header.creation_ts_ns) / 1e9   # rigorous upper bound
offset_lo = -0.05
on_periods = [(cN_start - c1_start, cN_stop - c1_start) for N in 1..3]      # cubic_rep1_start anchor
phase_bracketed([t+offset_lo, t+offset_hi], on_periods):
    'ON'  iff every sampled point (endpoints + any interior schedule edge) is ON
    'OFF' iff every sampled point is OFF
    'ALIGNMENT-LIMITED' otherwise
PREDICATE H  iff phase_bracketed == 'OFF'
```

**COMPETE episodes** are bracketed by (DELAY→COMPETE entry seq, next COMPETE→DELAY exit seq).
`H_AND_D_IN_SAME_EPISODE` iff a guard-failing event's episode-entry seq equals a Predicate-H
event's seq.

**Assumptions (explicit in the script):** (a) `CLOCK_MONOTONIC` and `CLOCK_REALTIME` advance at the
same rate to within ~0.5 ms/s over a ~10 s window (true absent a clock step; `CLOCK_MONOTONIC` is
never stepped); (b) the recorder's `creation_ts_ns` is captured before the covegas iperf3 process
starts (driver-script order — recorder launched, waited for attach, then covegas launched); (c) the
first dominant `init` callback is after the covegas process starts. (a)+(b)+(c) give the rigorous
`offset_hi`.

Historical-archive analyzer: `data/audit_src/analyze_historical_a3_archive.py` (read-only; reads
`~/cn-spike/covegas/raw/partC_v4/Ph500_B5x_rep2_*`). Same guard arithmetic; schedule anchored to
`cubic_rep1_start_ts`; robustness reported vs. ±4.0 s allowance (no monotonic anchor in the CSV).

---

## 7. INPUT DATA ACCOUNTING

### Current CoVegas v2 traces (analyzed; not modified)

| trace | raw events | dominant-conn events | other (excluded) | drops | seq gaps | workload | build/config |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `raw/covegas_replay/primary/rep1.ccr` | 63,330 | 63,329 | 1 | 0 | 0 | intermittent (covegas 120 s; cubic cross-traffic 20 s on / 20 s off ×3) | Gate-3-R2 topology; `HOLD_MS=500` default; `CONFIG_HZ=250` |
| `raw/covegas_replay/primary/rep2.ccr` | 62,900 | 62,899 | 1 | 0 | 0 | " | " |
| `raw/covegas_replay/primary/rep3.ccr` | 64,050 | 64,049 | 1 | 0 | 0 | " | " |

`cong_avoid` events (dominant): rep1 31,348 · rep2 31,151 · rep3 31,683. `mode` transitions: 6 per
trace (3 DELAY→COMPETE, 3 COMPETE→DELAY). All traces `validate_run_v2` pass (previously committed
`_validation.json`).

Trace header fields used this session: `creation_ts_ns` (`CLOCK_MONOTONIC`, from
`clock_gettime(CLOCK_MONOTONIC)` at `user/ccr_recorder_covegas.c:60`, written at
`user/ccr_recorder_covegas.c:124`).

### Historical read-only archive

```text
SOURCE PATH:              ~/cn-spike/covegas/raw/partC_v4/Ph500_B5x_rep2_ringbuf.csv  (+ *_start_ts / *_stop_ts / *_covegas_iperf3.json)
SOURCE PROVENANCE:        ~/cn-spike repo (read-only per CLAUDE.md); HEAD 022c2e2; partC_v4 = REPORT_COVEGAS_V4.md Part B2 intermittent sweep
READ-ONLY INTEGRITY:      ~/cn-spike shows only the pre-existing baseline `M CLAUDE.md` (documented, not caused by CCReplay work); no partC_v4 file touched
COLUMNS AVAILABLE:        ts_ns, srtt_us, min_rtt_us, recent_min_us, cwnd, queue_est, detect_count,
                          dlv_rate_bps, dlv_rate_compete, dlv_rate_max, mode, probing
FIELDS REQUIRED BUT ABSENT (for full Predicate-D reconstruction):
                          compete_enter_jiffies, tcp_jiffies32 (only ts_ns monotonic), last_minrtt_probe_ns, probe_action_start_ns
                          (only a `probing` boolean is present)
CSV rows: 33,912   span: 120.047 s
```

---

## 8. RESULTS

### 8.1 Current-trace scan (`data/historical_a3_existing_trace_scan.md`)

| trace | H present | H alignment-limited | D present | H+D same episode | all D settle-gate exact |
| --- | --- | --- | --- | --- | --- |
| rep1 | **NO** | NO | **NO** | NO | YES |
| rep2 | **NO** | NO | **NO** | NO | YES |
| rep3 | **NO** | NO | **NO** | NO | YES |

DELAY→COMPETE transitions and their bracketed phase (schedule anchored to `cubic_rep1_start_ts`;
offset bracket per trace shown in §10):

| trace | seq | t_event (s) | schedule window [lo,hi] (s) | phase (bracketed) | nearest boundary (s) |
| --- | ---: | ---: | --- | --- | ---: |
| rep1 | 418 | 1.49 | [1.44, 1.79] | ON | 1.61 |
| rep1 | 19995 | 42.23 | [42.18, 42.53] | ON | 1.66 |
| rep1 | 44100 | 84.29 | [84.24, 84.59] | ON | 3.03 |
| rep2 | 418 | 2.02 | [1.97, 2.32] | ON | 2.15 |
| rep2 | 19694 | 42.90 | [42.85, 43.20] | ON | 2.41 |
| rep2 | 41478 | 83.07 | [83.02, 83.37] | ON | 2.04 |
| rep3 | 424 | 1.49 | [1.44, 1.76] | ON | 1.60 |
| rep3 | 21021 | 42.40 | [42.35, 42.68] | ON | 1.77 |
| rep3 | 44373 | 84.15 | [84.10, 84.43] | ON | 2.84 |

All 9 transitions are **robustly ON**: nearest-boundary distance (1.6–3.0 s) far exceeds the
offset-bracket width (0.35 s). No transition is `ALIGNMENT-LIMITED`.

### 8.2 Predicate D — code-path-reached vs. divergent-condition-not-occurred

The scan **does** reach the divergent code path: 3 settle-latch guard evaluations per trace (one per
COMPETE episode). All **pass** — the divergent condition (guard FALSE) never occurs. This is
"code path reached but divergent condition did not occur," not "code path never reached."

### 8.3 Historical archive (`data/historical_a3_archive_analysis.json`)

| quantity | value |
| --- | --- |
| documented spurious DELAY→COMPETE | t ≈ 65.51 s, phase = **OFF (robust)**, nearest boundary **4.11 s** (survives a ±4.0 s allowance) |
| matching revert (COMPETE→DELAY) | t ≈ 66.51 s — **0.998 s** after entry (≈ `RATE_SETTLE_MS`) |
| `dlv_rate_compete` latched in that episode | **never** (max 0 across the episode) |
| v4 guard at the revert row | `dlv_rate_bps 1,194,436` vs `¾·dlv_rate_max = ¾·1,197,147 = 897,860` → **1,194,436 ≥ 897,860 → guard FALSE → revert** |
| `HISTORICAL_PREDICATE_H_CONFIRMED_FROM_ARCHIVE` | **YES**, robust |
| `HISTORICAL_PREDICATE_D_DIRECT_VALIDATION` | **PARTIAL** — guard expression evaluable & FALSE; §4.1 (`handle_minrtt_probe`) and §4.4 (settle-time gate) **not** reconstructable from the CSV columns |

### 8.4 Replay-gate regressions (unchanged)

```text
Reno v0     R1 / R2  (rep1,rep2,rep3)   -> 0 mismatches / first divergence NONE
CUBIC v1    R3A                          -> 236,042 CLOCK_STABLE events 0 mismatches; 46 CLOCK_AMBIGUOUS, 4 mismatches; non_ambiguous_first_mismatch = null  (PARTIAL, unchanged)
CUBIC v1    R3B                          -> first divergence in every trace is CLOCK_AMBIGUOUS only  (PARTIAL, unchanged)
CoVegas v2  E2                           -> 190,277 events, 4,982,990 field comparisons, 0 mismatches
CoVegas v2  E3                           -> first divergence NONE, all 3 traces
```

---

## 9. IMPORTANT INTERMEDIATE COUNTS (cong_avoid control-flow funnel, round 2)

| stage | rep1 | rep2 | rep3 |
| --- | ---: | ---: | ---: |
| `cong_avoid` events (dominant) | 31,348 | 31,151 | 31,683 |
| not cwnd-limited (skipped at GATE 0) | **0** | **0** | **0** |
| cwnd-limited pass | 31,348 | 31,151 | 31,683 |
| minrtt-probe skipped (GATE 1 == 0) | 31,089 | 30,909 | 31,422 |
| COMPETE dispatch (GATE 2) | 5,733 | 5,441 | 5,716 |
| `dlv_rate_compete == 0` block entered (GATE 3) | 312 | 319 | 300 |
| settle-time gate reached / guard evaluated (GATE 4) | **3** | **3** | **3** |
| guard passes | 3 | 3 | 3 |
| guard failures → **Predicate D** | **0** | **0** | **0** |
| settle-gate jiffies-bracket flips | 0 | 0 | 0 |

**Round 1 → round 2:** COMPETE dispatch (5733/5441/5716), settle-block (312/319/300), guard
evaluated (3/3/3), guard pass (3/3/3), guard fail (0/0/0) — **identical**. The cwnd-limited gate
removes 0 events (the recorder already filtered on the kernel's `tcp_is_cwnd_limited(sk)` before
emitting any record; `not_cwnd_limited = 0`). The correction is to control-flow fidelity, recorded
not silently applied.

Where candidate events disappear: 31,348 → 5,733 at the minrtt-probe + mode gates (most
`cong_avoid` events are DELAY-mode or probe-skipped); 5,733 → 312 because `dlv_rate_compete` is
non-zero for most of each COMPETE episode (latched after the first ~1 s); 312 → 3 because the
settle-time gate (`elapsed >= 250 jiffies`) is satisfied only once per episode (the pre-settle
window contributes the other ~100 events/episode).

---

## 10. CLOCK / TIMING / ALIGNMENT AUDIT

### Predicate D (settle-time gate §4.4)

- **Clock:** `tcp_jiffies32`, captured as `clock_jiffies32_before` / `clock_jiffies32_after`
  (bracketed, not injected — same hazard class as CUBIC ADR-018).
- **Method:** the scanner evaluates `elapsed_jiffies >= 250` under **both** endpoints and reports
  `settle_gate_jiffies_bracket_flips`. **0 flips** across all 3 traces → every scanned
  classification is exactly resolved. All other Predicate-D conditions use recorded PRE state or
  the exact `clock_ktime_ns_before`.

### Predicate H (workload phase)

- **Event clock:** `CLOCK_MONOTONIC` (`bpf_ktime_get_ns()`), event `ts_ns`.
- **Header `creation_ts_ns`:** `CLOCK_MONOTONIC` (`clock_gettime(CLOCK_MONOTONIC)`,
  `user/ccr_recorder_covegas.c:60`).
- **Schedule clock:** `CLOCK_REALTIME` (`date +%s.%N` for `cubic_rep{1,2,3}_{start,stop}_ts.txt`;
  iperf3 `start.timestamp.timesecs` is `CLOCK_REALTIME` and 1-second-quantized).
- **Common anchor:** **NONE.** No artifact records both clock domains at one instant.
- **Timestamp origins:** event stream zeroed at `first_dominant_event.ts_ns` (monotonic); schedule
  zeroed at `cubic_rep1_start_ts` (realtime).
- **Bounded offset** `Δ = first_dominant_event_wall − cubic_rep1_start_wall`:
  - upper bound (rigorous): `Δ < (first_dominant_event.ts_ns − header.creation_ts_ns)/1e9` =
    **0.298 s (rep1) / 0.295 s (rep2) / 0.276 s (rep3)** — the recorder starts before the covegas
    process, and the first callback is after it; monotonic vs realtime rate difference over ~10 s
    is < ~15 ms.
  - lower bound: `Δ ≥ 0` (first `init` callback follows connection setup, which follows the
    `date +%s.%N` that captured `cubic_rep1_start_ts`); `−0.05 s` pad for `date` exec + slew.
  - **bracket used: `Δ ∈ [−0.05, +0.30] s`.**
- **Distance of classified events from phase boundaries:** 1.60–3.03 s (all 9 transitions).
- **Does classification change under the uncertainty interval?** **No** — 1.6 s ≫ 0.35 s bracket
  width. All 9 DELAY→COMPETE transitions robustly ON; Predicate H robustly absent.
- **Historical archive:** no monotonic anchor in the CSV → no rigorous `Δ'` upper bound.
  Robustness reported vs. a deliberately generous ±4.0 s allowance; the ~65.51 s event is 4.11 s
  from the nearest boundary → still robustly OFF. Physical offset is sub-second
  (`covegas_start_ts` to `cubic_rep1_start_ts` = 0.0035 s; first telemetry row follows connection
  setup).

---

## 11. FAILURES / CORRECTIONS DURING THE SESSION

### Correction A — round-1 scanner omitted the cwnd-limited gate

```text
ISSUE:            user/scan_historical_a3.py (round 1) called handle_minrtt_probe() and mode
                  dispatch without first applying tcp_is_cwnd_limited(...), which the real
                  cong_avoid path (model lines 523-524; recorder bpf/covegas_wrapper.bpf.c) checks
                  first with an early return.
HOW FOUND:        independent review of the round-1 predicate audit.
WHY IT MATTERED:  the scanner inspected an over-inclusive event set; on a different trace this
                  could count settle-latch evaluations for events the real control flow would have
                  early-returned.
FIX:              added GATE 0 (cwnd_limited(e)) before handle_minrtt_probe; added condition §4.0 to
                  Predicate D in data/historical_a3_predicate_audit.md; added not_cwnd_limited /
                  cwnd_limited_pass counters.
DID IT INVALIDATE PREVIOUS OUTPUT:  no numeric change (not_cwnd_limited = 0 in all 3 traces --
                  the recorder already filters on the kernel's tcp_is_cwnd_limited(sk) before
                  emitting any record). Round-1 counts preserved in the before/after table, not
                  silently replaced.
RESULT AFTER FIX: Predicate D still absent in all 3 traces; control flow now matches the
                  implementation.
```

### Correction B — Predicate-H time alignment assumed, not proven

```text
ISSUE:            round 1 (via check_historical_trigger.py) implicitly assumed the event clock and
                  the cross-traffic schedule share a zero point, and used the 1-second-quantized
                  iperf3 timesecs.
HOW FOUND:        independent review.
WHY IT MATTERED:  the first DELAY->COMPETE transition (~1.5 s) is close to the first ON-period
                  boundary; an unbounded offset could in principle flip its phase.
FIX:              searched artifacts -> no common monotonic/realtime anchor exists. Derived a
                  rigorous offset upper bound from (first_event.ts_ns - header.creation_ts_ns)
                  and a lower bound of ~0; classify Predicate H only where the phase is invariant
                  over [t-0.05, t+0.30]; report nearest-boundary distance and ALIGNMENT-LIMITED
                  where not invariant.
DID IT INVALIDATE PREVIOUS OUTPUT:  no -- Predicate H was NO in round 1 and is NO in round 2, now
                  shown robust (all transitions 1.6-3.0 s from any boundary).
RESULT AFTER FIX: Predicate H robustly absent in all 3 current traces; historical ~65.51 s event
                  robustly OFF (4.11 s margin).
```

### Correction C — Predicate-D over-claimed as "exactly observable"

```text
ISSUE:            round 1 said "PREDICATE_D_DIRECTLY_OBSERVABLE_FROM_TRACE = YES" without
                  qualifying that tcp_jiffies32 stays bracketed.
FIX:              added the clock-qualification paragraph to data/historical_a3_predicate_audit.md;
                  scanner reports settle_gate_jiffies_bracket_flips (0 across all traces =>
                  every scanned classification exactly resolved); the "directly observable"
                  phrase now means "required state/inputs are represented by ABI v2", not
                  "every gate is a non-bracketed exact value".
RESULT:           no classification changed; the claim is now correctly scoped.
```

### No other failures

No compile failure, no verifier issue (no BPF built this session), no parser bug, no model
mismatch, no test regression.

---

## 12. DOCUMENTATION RECONCILIATION

| stale statement | location | corrected statement | corrected? |
| --- | --- | --- | --- |
| Predicate D "directly observable" (unqualified) | round-1 `data/historical_a3_predicate_audit.md` | "required state/inputs represented by ABI v2; `tcp_jiffies32` stays bracketed; settle-gate exactly classifiable when both endpoints agree (0 flips observed)" | **yes** |
| Predicate-H phase assumed aligned; 1-s-quantized anchor | round-1 scanner / `check_historical_trigger.py` | explicit `Δ ∈ [−0.05,+0.30] s` bracket; anchor `cubic_rep1_start_ts`; `ALIGNMENT-LIMITED` where not invariant | **yes** |
| scanner control flow (no cwnd-limited gate) | round-1 `user/scan_historical_a3.py` | GATE 0 added; §4.0 in predicate audit | **yes** |
| CoVegas `undo_cwnd` "already separately VALIDATED via Part B" | `REPORT_COVEGAS_REPLAY_FIDELITY.md` (fixed in `bb0fb3e`) | Outcome A — function-level evidence via shared `tcp_reno_undo_cwnd`; CoVegas ABI-v2 path unexercised | yes (prior commit; re-verified) |
| "1 of 9 runs", "~11%/run", "P(0/3)≈70%" | historical-trigger docs (fixed in `bb0fb3e`) | 3 runs / 9 off-period boundaries / 1 trigger; `P(0 in 9) = (8/9)^9 ≈ 34.6%`, rough binomial sensitivity | yes (prior commit; re-verified) |
| 4-event clock table unscoped | `REPORT_CUBIC_CLOCK_BOUNDARY_INVESTIGATION.md` (fixed in `bb0fb3e`) | Table 2a = 4 production-convention mismatches; Table 2b = all 46 (`2/4/40/0`) | yes (prior commit; re-verified) |

**Recurring-hazard statements re-verified unchanged this session:** CUBIC R3 = **PARTIAL** (not
upgraded); full-46 clock attribution = `MATCHES_BEFORE_ONLY 2 / MATCHES_AFTER_ONLY 4 / MATCHES_BOTH
40 / MATCHES_NEITHER 0`; the ~780 ns observation window is **inferred from tick-collision
probability**, not directly measured; CoVegas `undo_cwnd` = Outcome A; CoVegas `clock_ktime_ns_before`
= exact controller-consumed value for `init`/`cong_avoid`, `_after` diagnostic-only; historical
trigger denominator = **boundaries, not runs**; no `~11%/run`; no `P(0/3)≈70%`; no general
`byte-exact`/`bit-exact`; historical CoVegas case = **INCOMPLETE**, not FAIL; **no historical A3
localization claim** (the buggy-vs-fixed diff has not run).

---

## 13. REGRESSION / INTEGRITY VALIDATION

```text
AUTOMATED TESTS:   python3 -m unittest discover -s tests   ->  Ran 40 tests ... OK   (26 v0 + 14 v1)

RENO v0:           for r in rep1 rep2 rep3:
                     python3 user/replay_r1.py raw/r0/$r.ccr raw/r0/$r.meta.json   -> PASS  (0 mismatches)
                     python3 user/replay_r2.py raw/r0/$r.ccr raw/r0/$r.meta.json   -> PASS  (first divergence NONE)

CUBIC v1:          python3 user/replay_r3a.py raw/cubic_replay/primary/rep{1,2,3}.ccr <+meta>
                     -> total_mismatches 4 ; clock_stable_mismatched 0 ; non_ambiguous_first_mismatch null   (PARTIAL, unchanged)
                   python3 user/replay_r3b.py <same>
                     -> pass_first_divergence_is_only_clock_ambiguous: true   (PARTIAL, unchanged)

COVEGAS v2:        python3 user/replay_e2.py raw/covegas_replay/primary/rep{1,2,3}.ccr <+meta>
                     -> "pass": true ; total_mismatches 0
                   python3 user/replay_e3.py <same>
                     -> "pass": true ; first_divergence null

SOURCE REPO INTEGRITY:
                   ~/cn-spike  git rev-parse --short HEAD -> 022c2e2
                               git status --porcelain | grep '^ M' -> " M CLAUDE.md"  (1; pre-existing baseline, documented in docs/PROVENANCE.md)
                   no file under ~/cn-spike/covegas/raw/partC_v4/ modified (read-only analysis only)

WORKING TREE (~/ccreplay after commit):
                   clean except the standing untracked exceptions:
                     ?? docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md   (task-instructions, never committed)
                     ?? instructions.md                               (stray lowercase, never committed)
                   docs/session/LATEST_REVIEW_HANDOFF.md is committed (this file).
```

No mandatory regression was skipped.

---

## 14. GIT ORDERING / PRECOMMIT EVIDENCE

```text
Predicate definitions committed:   d9677dc  (data/historical_a3_predicate_audit.md, round 1)
Round-2 correction commit:         <this session's commit>
Ordering:                          predicate definitions PRECEDE this session's scan results.
```

Round 2 **added** condition §4.0 (cwnd-limited) and the alignment-robustness qualifier to the
predicate definition; it did **not** relax any condition, change the guard expression, change the
250-jiffy threshold, or change the same-episode rule. The interpretation matrix (CASE 1–4) was
fixed in the task prompt before any result. `data/historical_regression_predictions.md` (the
historical buggy-vs-fixed precommit) is untouched and unresolved by design — no diff has run.

---

## 15. ADVERSARIAL SELF-CHECK

```text
Did this session redefine a criterion after seeing an unfavorable result?
  NO. §4.0 was ADDED (a real omitted control-flow gate), not a redefinition to change an outcome;
  it removes 0 events. The alignment qualifier makes an implicit assumption explicit and bracketed;
  it does not move any transition across a phase boundary.

Did this session weaken an oracle?
  NO. No replay oracle touched. All replay-gate regressions re-run and unchanged.

Did this session change a prediction after results?
  NO. data/historical_regression_predictions.md untouched; predicate thresholds unchanged.

Did this session infer an unrecorded state value?
  NO. Current-trace Predicate D uses only recorded PRE state + clock_ktime_ns_before (exact) +
  both jiffies bracket endpoints. For the historical archive, §4.1 and §4.4 are explicitly reported
  as NOT reconstructable from the CSV -- not inferred; Predicate D there stays PARTIAL.

Did this session treat a diagnostic timestamp as an exact controller input?
  NO. clock_ktime_ns_after is not used. clock_jiffies32 is treated as bracketed and the settle-gate
  is checked under both endpoints (0 flips). creation_ts_ns is used only to bound an offset, not as
  a controller input.

Did this session conflate historical symptom H with implementation divergence D?
  NO. They are defined separately, scanned separately, and the same-episode rule is reported
  separately. Result: both absent in current traces (CASE 4).

Did this session use a denominator inconsistent with the underlying trials?
  NO. Historical trigger denominator is stated as off-period boundaries (9 from 3 HOLD_MS=500 runs),
  re-verified; the (8/9)^9 sensitivity figure is labelled rough/binomial/independence-assumption.

Did this session claim counterfactual network behavior from replay?
  NO. No throughput/RTT/queue claim. Predicate D is a statement about what two implementations
  compute at a recorded boundary.

Did this session convert INCOMPLETE into FAIL or PASS without new evidence?
  NO. Historical CoVegas case remains INCOMPLETE. CUBIC R3 remains PARTIAL. CoVegas self-replay
  remains PASS.
```

---

## 16. CURRENT AUTHORITATIVE RESULT

```text
PREDICATE H:   DELAY->COMPETE transition on a cong_avoid event, wall-clock time in a cross-traffic
               OFF period, robust over the event/schedule offset bracket Δ ∈ [-0.05, +0.30] s.

PREDICATE D:   cong_avoid event; source-derived control flow reaches handle_compete_mode's
               settle-latch guard (cwnd-limited; handle_minrtt_probe==0; mode==COMPETE;
               dlv_rate_compete==0; elapsed_jiffies >= 250 under BOTH jiffies bracket endpoints;
               dlv_rate_bps != 0) AND the v4 guard is FALSE
               (dlv_rate_bps >= (dlv_rate_max*3)/4).

H+D SAME-EPISODE RULE:  a guard-failing settle-latch event whose COMPETE episode was entered by a
               Predicate-H (OFF-period) DELAY->COMPETE transition.

rep1:  H = NO (robust)   D = NO   H+D = NO
rep2:  H = NO (robust)   D = NO   H+D = NO
rep3:  H = NO (robust)   D = NO   H+D = NO
       (per trace: 3 COMPETE episodes, all entered ON; 3 settle-latch guard evaluations, all pass;
        0 settle-gate jiffies-bracket flips)

HISTORICAL ARCHIVE (Ph500_B5x_rep2, read-only):
       Predicate H  = confirmed, robust (DELAY->COMPETE t≈65.51 s, OFF-period 2, 4.11 s margin)
       Predicate D  = PARTIAL (guard expression evaluable and FALSE at the t≈66.51 s revert;
                      dlv_rate_compete never latched; revert 0.998 s after entry;
                      §4.1 and §4.4 NOT reconstructable from the archived CSV columns)
       -> validates the detector; does NOT provide a v2 differential-replay candidate.

CURRENT CASE CLASSIFICATION:  CASE 4 — neither Predicate H nor Predicate D present in any current
                              v2 trace.

HISTORICAL DIFF AUTHORIZED BY EVIDENCE:  NO
A3 AUXILIARY MECHANISM DIFF AVAILABLE:   NO
```

---

## 17. EXACT NEXT DECISION

```text
NEXT PROJECT-LEVEL DECISION (requires external review — no option executed this session):

A. Authorize another predeclared HOLD_MS=500 historical-trigger capture campaign aimed at a
   trigger-positive Replay ABI v2 trace (Predicate H present in an OFF period). Only such a trace
   can support either the historical buggy-vs-fixed differential replay OR an auxiliary A3
   mechanism-localization diff -- the three existing traces support neither.

B. Freeze the historical CoVegas A3 case as INCOMPLETE (trigger-availability blocker, not a
   failure; CoVegas self-replay PASS and CUBIC R3 PARTIAL are both unaffected) and move to
   professor-demo packaging of the completed differential-debugger / checkpoint-reproducer results
   (N4-N6).

C. Another option supported by this session's evidence (e.g. a longer / multi-rep single capture,
   or a predeclared decision to accept the historical-archive same-episode H+D as sufficient
   qualitative evidence that the A3 mechanism is real, without a CCReplay v2 differential replay).

NO OPTION EXECUTED IN THIS SESSION.
```

---

## 18. COPY-PASTE REVIEW SUMMARY

```text
CCReplay — A3 scanner control-flow correction + phase-alignment audit (round 2)
date 2026-09-05 | starting commit d9677dc | offline, read-only | STOP for review

FORMAL VERDICTS (unchanged this session):
  CUBIC R3                     PARTIAL   (literal "R3B first divergence = NONE" not met;
                                         residual = CLOCK_AMBIGUOUS only; ATTRIBUTED_AND_CHARACTERIZED)
  CoVegas self-replay (E1-E3)  PASS      (190,277 events, 4,982,990 comparisons, 0 mismatches;
                                         stateful first divergence NONE on all 3 traces)
  Historical CoVegas A3 case   INCOMPLETE (trigger not reproduced; buggy-vs-fixed diff NOT run/authorized)

CUBIC full-46 clock attribution: MATCHES_BEFORE_ONLY 2 / AFTER_ONLY 4 / BOTH 40 / NEITHER 0
  (4-event table = production-convention mismatches only; ~780 ns window = inferred, not measured)
CoVegas undo_cwnd:  Outcome A (function-level evidence via shared tcp_reno_undo_cwnd; ABI-v2 path unexercised; 0 events)
CoVegas ktime:      clock_ktime_ns_before = exact controller-consumed value (init/cong_avoid); _after diagnostic-only

THIS SESSION — two round-1 scanner issues corrected:
  1. cwnd-limited gate added BEFORE handle_minrtt_probe (matches user/covegas_model.py:523-524 and
     bpf/covegas_wrapper.bpf.c). Effect: 0 events removed (recorder pre-filters on kernel
     tcp_is_cwnd_limited(sk)); control-flow fidelity fix, recorded not silently replaced.
  2. Predicate-H time alignment: NO common monotonic/realtime anchor exists. Rigorous offset bracket
     Δ ∈ [-0.05, +0.30] s from (first_event.ts_ns - header.creation_ts_ns). All DELAY->COMPETE
     transitions robustly ON (nearest boundary 1.6-3.0 s >> 0.35 s bracket).
  3. Predicate-D clock qualification: tcp_jiffies32 stays bracketed; settle-time gate checked under
     BOTH endpoints; 0 flips across all 3 traces => every scanned classification exactly resolved.

A3 PREDICATE DEFINITIONS (committed d9677dc; round 2 added §4.0, relaxed nothing):
  Predicate H = DELAY->COMPETE cong_avoid event in a cross-traffic OFF period (robust over Δ bracket)
  Predicate D = cong_avoid event; control flow reaches handle_compete_mode settle-latch
                (cwnd-limited; !minrtt_probe; mode==COMPETE; dlv_rate_compete==0; elapsed>=250 jiffies
                 both endpoints; dlv_rate_bps!=0) AND v4 guard FALSE (dlv_rate_bps >= (dlv_rate_max*3)/4)
  Same-episode rule: guard-failing event whose COMPETE episode was entered by an OFF-period H.

SCAN OF THE 3 EXISTING CoVegas v2 TRACES (user/scan_historical_a3.py):
  rep1  H=NO(robust)  D=NO  H+D=NO   | 3 COMPETE episodes (all entered ON); 3 settle-guard evals, all pass
  rep2  H=NO(robust)  D=NO  H+D=NO   | funnel: cong_avoid 31151 -> compete_dispatch 5441 -> settle-block 319 -> guard-eval 3 -> pass 3
  rep3  H=NO(robust)  D=NO  H+D=NO   |
  cwnd-limited failures: 0/0/0   settle-gate jiffies flips: 0/0/0

HISTORICAL ARCHIVE (~/cn-spike/covegas/raw/partC_v4/Ph500_B5x_rep2_ringbuf.csv, read-only):
  Predicate H  CONFIRMED, robust  (DELAY->COMPETE t≈65.51s, OFF-period 2, nearest boundary 4.11s)
  Predicate D  PARTIAL           (guard expr evaluable & FALSE at t≈66.51s revert:
                                  dlv_rate_bps 1,194,436 >= 3/4·1,197,147 = 897,860;
                                  dlv_rate_compete never latched; revert 0.998s after entry;
                                  settle-time gate + minrtt-probe gate NOT reconstructable from CSV columns)
  -> validates the detector; not a v2 differential-replay candidate.

INTERPRETATION: CASE 4 — neither predicate present in any current trace.
  HISTORICAL DIFF CANDIDATE AVAILABLE: NO
  A3 MECHANISM-DIFF CANDIDATE AVAILABLE: NO

REGRESSIONS: unittest 40/40 OK | Reno R1/R2 PASS | CUBIC R3A/R3B unchanged PARTIAL |
             CoVegas E2 0 mismatches | CoVegas E3 first divergence NONE
SOURCE REPOS: ~/cn-spike at 022c2e2, only pre-existing baseline `M CLAUDE.md`; partC_v4 untouched
NEW NETWORK CAPTURES: NO | HISTORICAL DIFF RUN: NO
COMMIT: <this session's commit>  | WORKING TREE: clean except standing untracked exceptions
        (docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md, instructions.md)

NEXT DECISION (external review; nothing executed):
  A. authorize a predeclared HOLD_MS=500 capture campaign for a trigger-positive v2 trace
  B. freeze historical A3 case as INCOMPLETE, move to demo packaging (N4-N6)
  C. another evidence-supported option
```

---

*For external review, send only:* `docs/session/LATEST_REVIEW_HANDOFF.md`
