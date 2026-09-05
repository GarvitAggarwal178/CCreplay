# Evidence Reconciliation + Historical Trigger / A3 Divergence Predicate Audit

## Status: COMPLETE — offline, read-only. No network capture, no buggy-vs-fixed differential replay.

Bounded offline validation session. Purpose: (1) reconcile stale evidence language; (2) derive the
A3 settle-latch divergence predicate from source; (3) distinguish it from the historical off-period
trigger; (4) scan the three existing CoVegas traces for both; (5) validate the detector against the
archived historical positive as far as the archived telemetry permits. Then STOP for project-level
review.

**No formal gate verdict changed.** CUBIC `R3 = PARTIAL`. CoVegas self-replay `PASS`. Historical
case study `INCOMPLETE`.

---

## Part A — evidence reconciliation

Most of the required reconciliation was already applied in commit `bb0fb3e`
(`docs: add authoritative CCReplay current-state handoff`). This session completed the remainder.

### Corrections made this session

| # | file | change |
| --- | --- | --- |
| A1 | `docs/CURRENT_STATE.md` §5 (clock-boundary row), §7, §14 | Made the **full-46** two-sided attribution the primary current-facing figure (`MATCHES_BEFORE_ONLY=2`, `MATCHES_AFTER_ONLY=4`, `MATCHES_BOTH=40`, `MATCHES_NEITHER=0`), explicitly labelling the older 4-event table as *the four production-convention mismatches only*. Replaced any "necessarily saw" framing with semantic-compatibility wording. |
| A4 | `docs/CURRENT_STATE.md` §4, §14 | Standardised the union's mode-selected arm as **COMPETE-arm** in prose, with a one-line note that the source union member is literally named `cubic` (COMPETE mode borrows CUBIC's growth law) and `u.cubic.*` remains the code identifier — **no serialized field / parser key / struct member renamed.** |
| A6 | `REPORT_DEVELOPMENT_SESSION_INDEX.md` "Parts D–F summary" | Corrected the historical `HOLD_MS=500` denominator from "~11%/run, P(0/3)≈70%" to **3 runs / 9 off-period boundaries / 1 spurious entry**, current campaign **3 runs / 9 boundaries / 0**, rough sensitivity `P(0 in 9) = (8/9)^9 ≈ 34.6%`. |

### Already reconciled in `bb0fb3e` (verified still correct this session)

- `docs/LIMITATIONS.md` #13: `byte-exact` → `with exact semantic equality`. (#14 already avoids
  "irreducible".)
- `REPORT_CUBIC_REPLAY_VALIDATION.md` "Failures and deviations" item 3: `undo_cwnd` now recorded as
  *originally UNVALIDATED, subsequently VALIDATED via the targeted auxiliary trace* — no longer left
  as an open "not remediated" item; explicitly "does not change the R3 verdict."
- `REPORT_CUBIC_CLOCK_BOUNDARY_INVESTIGATION.md` §2: split into **Table 2a** (four
  production-convention mismatches) and **Table 2b** (all 46 `CLOCK_AMBIGUOUS` events), with the
  full recomputation (`data/audit_src/clock_boundary_attribution_all_ambiguous.py` →
  `data/cubic_clock_boundary_attribution_all_ambiguous.json`).
- `REPORT_COVEGAS_REPLAY_FIDELITY.md`: the stale "`undo_cwnd`×0 (already separately VALIDATED via
  Part B's auxiliary trace)" line corrected — a new "`undo_cwnd` coverage audit" section classifies
  it **Outcome A** (function semantics independently supported via the shared `tcp_reno_undo_cwnd`
  helper; the CoVegas ABI-v2 recorder/model path itself unexercised in the primary traces); a new
  "CoVegas `bpf_ktime_get_ns()` semantics" section records that for `init`/`cong_avoid`,
  `clock_ktime_ns_before` **is** the exact controller-consumed value (single shared read),
  `clock_ktime_ns_after` diagnostic-only.
- `data/historical_trigger_validation.md`, `REPORT_HISTORICAL_COVEGAS_REGRESSION.md`: "1 of 9 runs"
  → "3 runs / 9 boundaries / 1"; `(8/9)^3 ≈ 70%` → `(8/9)^9 ≈ 34.6%`, both labelled *rough binomial
  sensitivity under an independence assumption, not an estimated trigger distribution*.

### Stale statements deliberately retained (as historical, annotated not erased)

- The literal strings "1 of 9 runs" / "`(8/9)^3 ≈ 70%`" survive **inside the correction text** of
  `data/historical_trigger_validation.md`, `REPORT_HISTORICAL_COVEGAS_REGRESSION.md`,
  `REPORT_DEVELOPMENT_SESSION_INDEX.md`, and `docs/CURRENT_STATE.md` §12/§14 — quoted so a reader
  who saw the old figure elsewhere can see exactly what changed and why. Per the task: annotate,
  do not pretend the stale statement never existed.
- `REPORT_PHASE1_RENO_REPLAY_VALIDATION.md` §H's "15 fields" CUBIC reconnaissance — pre-R3
  speculation, already corrected by ADR-019 (17 members / 16 semantic); left as the honest
  historical record of what was predicted before R3.
- `REPORT_DEVELOPMENT_SESSION_INDEX.md` "N2/N3 summary" still says `undo_cwnd` UNVALIDATED — this
  is the state *as of that phase*; the very next section ("Parts A–C summary") records it closed.
  Section ordering already conveys the supersession.
- `data/historical_regression_predictions.md` — **not touched** (per task A8). The precommit stays
  visibly intact; no claim appended that CCReplay has already localised the historical regression.

---

## Part B — Predicate D, derived from source

Full derivation with source line references: `data/historical_a3_predicate_audit.md`. Summary:

**Predicate H — historical off-period trigger:** a `cong_avoid` event with `priv_pre_mode == DELAY`
and `priv_post_mode == COMPETE` whose wall-clock time falls in a cross-traffic OFF period.

**Predicate D — A3 implementation-divergence condition** (from
`~/cn-spike/covegas/src/covegas.bpf.c` lines 697–715, byte-identical in `bpf/covegas_wrapper.bpf.c`
and mirrored in `user/covegas_model.py` lines 360–379): a `cong_avoid` event where, on the recorded
PRE state + recorded controller-visible clocks:

1. `handle_minrtt_probe` returns 0 (`priv_pre_minrtt_probing == 0` and
   `clock_ktime_ns_before − priv_pre_last_minrtt_probe_ns < 10·10⁹`);
2. `priv_pre_mode == COMPETE`;
3. `priv_pre_dlv_rate_compete == 0`;
4. `(u32)(clock_jiffies32_before − priv_pre_compete_enter_jiffies) >= (RATE_SETTLE_MS·HZ)/1000 = 250`;
5. `priv_pre_dlv_rate_bps != 0`;
6. **v4 guard FALSE:** `priv_pre_dlv_rate_bps >= (priv_pre_dlv_rate_max * 3) / 4`.

On a Predicate-D event, reconstructed-v3 (unconditional latch → `cubic_growth`) and v4
(`revert_to_delay` → `return`) diverge; first differing fields: `priv_post_mode`,
`priv_post_dlv_rate_compete`, and everything `revert_to_delay` vs `cubic_growth` writes.

**Fields required to evaluate Predicate D** — all present in Replay ABI v2 (table in
`data/historical_a3_predicate_audit.md` §6):

```text
PREDICATE_D_DIRECTLY_OBSERVABLE_FROM_TRACE = YES
```

Jiffies-ambiguity caveat on condition 4: `tcp_jiffies32` is bracketed, not injected; the 250-jiffy
threshold is only sensitive to the 1-jiffy before/after gap for an event sitting exactly on it. The
scanner rechecks condition 4 with `clock_jiffies32_after` and flags flips — none occurred.

---

## Part C — scan of the three existing CoVegas traces

Scanner: `user/scan_historical_a3.py` (offline, read-only; reuses `user/covegas_model.py` helpers
and `data/audit_src/check_historical_trigger.py`'s phase mapping). Full output:
`data/historical_a3_existing_trace_scan.md` / `.json`.

| trace | dom events | cong_avoid | DELAY→COMPETE | …during OFF (Pred H) | COMPETE→DELAY | settle-latch guard evals | guard-pass | guard-fail (Pred D) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rep1 | 63,329 | 31,348 | 3 | **0** | 3 | 3 | 3 | **0** |
| rep2 | 62,899 | 31,151 | 3 | **0** | 3 | 3 | 3 | **0** |
| rep3 | 64,049 | 31,683 | 3 | **0** | 3 | 3 | 3 | **0** |

Every trace: 3 COMPETE episodes, each entered **during an ON period** (real competitor present),
each resolving its settle-latch check by the **guard passing** (`dlv_rate_bps < ¾·dlv_rate_max` —
the settle-time rate genuinely depressed by the competitor), so the reconstructed-v3 unconditional
latch and the v4 guarded latch produce the identical transition. No jiffies-ambiguity flips on the
settle gate. No `cong_avoid` event in any of the three traces satisfies Predicate D.

```text
rep1: PREDICATE_H_PRESENT: NO   PREDICATE_D_PRESENT: NO   H_AND_D_IN_SAME_EPISODE: NO
rep2: PREDICATE_H_PRESENT: NO   PREDICATE_D_PRESENT: NO   H_AND_D_IN_SAME_EPISODE: NO
rep3: PREDICATE_H_PRESENT: NO   PREDICATE_D_PRESENT: NO   H_AND_D_IN_SAME_EPISODE: NO
```

(Predicate H = NO matches `data/historical_trigger_validation.md`'s independent earlier finding.)

---

## Part D — historical known-positive validation

Archive: `~/cn-spike/covegas/raw/partC_v4/Ph500_B5x_rep2_ringbuf.csv` (HOLD_MS=500, rep2 — the run
whose ~t=65.51s spurious off-period COMPETE entry and ~t=66.51s revert are documented in
`REPORT_COVEGAS_V4.md` Part A / B2). Read-only. Analysis:
`data/audit_src/analyze_historical_a3_archive.py` → `data/historical_a3_archive_analysis.json`.

CSV columns: `ts_ns, srtt_us, min_rtt_us, recent_min_us, cwnd, queue_est, detect_count,
dlv_rate_bps, dlv_rate_compete, dlv_rate_max, mode, probing`.

Cross-traffic ON periods (relative to covegas start, from this run's own `*_start_ts`/`*_stop_ts`):
`[(0.0, 20.69), (40.70, 61.41), (81.41, 102.09)]`.

### D1 — Predicate H

The archive shows a `DELAY→COMPETE` transition at **t = 65.51 s**, phase **OFF** (inside off-period
`[61.41, 81.41]`). This is the documented spurious entry.

```text
HISTORICAL_PREDICATE_H_CONFIRMED_FROM_ARCHIVE: YES
```

Supporting row (transition point): `mode` 0→1, `dlv_rate_bps = 1,191,791`, `dlv_rate_compete = 0`,
`dlv_rate_max = 1,194,061`, `cwnd = 43`.

### D2 — Predicate D

The COMPETE episode entered at 65.51 s **reverts at 66.51 s — 0.998 s later** (≈ `RATE_SETTLE_MS` =
1000 ms), and `dlv_rate_compete` is **0 for the entire episode** (never latched). At the revert row:
`dlv_rate_bps = 1,194,436`, `dlv_rate_max = 1,197,147`, `(3/4)·dlv_rate_max = 897,860`. So
`dlv_rate_bps (1,194,436) ≥ 897,860` → **the v4 guard expression evaluates FALSE**, i.e. it would
`revert_to_delay` — exactly matching the observed transition and the never-latched
`dlv_rate_compete`.

**However**, the archived CSV lacks `compete_enter_jiffies`, a `tcp_jiffies32` column, and the
probe timestamps (`last_minrtt_probe_ns`, `probe_action_start_ns`) — only a `probing` flag. So
conditions §4.1 (`handle_minrtt_probe` return) and §4.4 (exact `elapsed_jiffies >= 250`) **cannot be
reconstructed exactly** from the archive; the 0.998 s entry→revert wall-clock gap and the
never-latched `dlv_rate_compete` are strong corroboration but not the exact jiffies computation.

```text
HISTORICAL_PREDICATE_D_DIRECT_VALIDATION: PARTIAL
  guard expression (dlv_rate_bps vs 3/4·dlv_rate_max): directly evaluable from archive -> FALSE (revert), as documented
  settle-time gate (elapsed_jiffies >= 250):          NOT reconstructable (no jiffies / compete_enter_jiffies column)
  handle_minrtt_probe gate:                            NOT reconstructable (no probe timestamps, only a `probing` flag)
  corroborating: revert 0.998s after entry; dlv_rate_compete never latched in the episode
```

### D3 — no oracle weakening

No predicate was weakened to make the historical run count as positive. Predicate H is confirmed
directly; Predicate D's guard arithmetic is confirmed directly and its gating conditions are
reported as not-reconstructable rather than assumed satisfied.

### Detector cross-check

Applying the scanner's guard arithmetic to the historical settle row: `1,194,436 < 897,860` is
False → the scanner **would** flag this event as Predicate D if it appeared in a v2 `.ccr` trace
with the gating fields present. The detector fires correctly on the known positive's guard
condition.

---

## Part E — interpretation

For the **three existing CoVegas `.ccr` traces**: no Predicate H, no Predicate D, in any trace.

```text
INTERPRETATION CATEGORY: 4 — NEITHER EXISTS

HISTORICAL DIFF CANDIDATE AVAILABLE:      NO
A3 MECHANISM-DIFF CANDIDATE AVAILABLE:    NO
```

The existing traces contain neither the historically selected off-period trigger nor any
guard-failing A3 settle-latch evaluation. Every COMPETE episode in all three traces was entered
during genuine competition and latched a legitimately-depressed rate — precisely the case where v3
and v4 agree. Running the buggy-vs-fixed differential replay against these traces would compare two
implementations along a path where they are defined to be identical, proving nothing about the
regression.

The **historical archive** (`Ph500_B5x_rep2`) does contain an H+D-in-same-episode instance
(Predicate H confirmed directly; Predicate D's guard arithmetic confirmed directly, gating
conditions not reconstructable from the archived columns) — this validates that the predicate
definitions and the detector are correct, but the archive is not a Replay ABI v2 trace and cannot
be fed to the differential replay engine.

Obtaining a trigger-positive v2 trace is a **separate project-level decision** (more bounded
captures at `HOLD_MS=500`; or a longer / multi-rep campaign; or accepting the historical case study
as permanently `INCOMPLETE`). Not taken in this session.

---

## Explicit scope statement

**No new network capture was run. No buggy-vs-fixed historical differential replay was run.** This
session added: two offline analysis scripts (`user/scan_historical_a3.py`,
`data/audit_src/analyze_historical_a3_archive.py`), their output data files, this report, one
predicate-derivation document, and documentation reconciliation edits. No recorder, parser, or
model semantics were changed. All regression suites pass unchanged.

## Validation

```text
python3 -m unittest discover -s tests            -> 40/40 OK
Reno v0  R1/R2  (rep1/rep2/rep3)                  -> PASS / first divergence NONE
CUBIC v1 R3A    (3 primary traces)                -> 0 CLOCK_STABLE mismatches, 4 CLOCK_AMBIGUOUS (unchanged PARTIAL)
CUBIC v1 R3B    (3 primary traces)                -> first divergence only CLOCK_AMBIGUOUS (unchanged PARTIAL)
CoVegas v2 E2   (3 primary traces)                -> 0 mismatches, pass
CoVegas v2 E3   (3 primary traces)                -> first divergence NONE, pass
source repos (~/cn-spike, ~/cn-spike/covegas)     -> unmodified (only the pre-existing baseline `M CLAUDE.md` in ~/cn-spike)
```

## Reproduction

```
python3 user/scan_historical_a3.py
python3 data/audit_src/analyze_historical_a3_archive.py
python3 data/audit_src/clock_boundary_attribution_all_ambiguous.py
```

## Relevant commit

This report's own commit (adds the two scan/analysis scripts, their JSON/MD outputs,
`data/historical_a3_predicate_audit.md`, this report, and the Part A reconciliation edits to
`docs/CURRENT_STATE.md` and `REPORT_DEVELOPMENT_SESSION_INDEX.md`).
