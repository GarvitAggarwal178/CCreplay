# CCReplay — Final Integrated Session — Review Handoff

**One-file review packet**, assembled incrementally as the session runs (not reconstructed at the
end). A reviewer who understands CCReplay's architecture should be able to audit the whole session
from this file. Individual reports / data files / scripts / git history remain authoritative for
their evidence.

---

## SESSION IDENTITY

```text
SESSION:                 Final Integrated Session  (docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md, phases 0-18)
DATE:                    2026-09-05
STARTING COMMIT:         263ca60  "audit: re-derive Predicate-H time-origin offset from harness order"
ENDING COMMIT:           <filled at Phase 18>
FORMAL VERDICTS AT START: Reno v0 PASS | CUBIC v1 R3 PARTIAL | CUBIC clock residual ATTRIBUTED_AND_CHARACTERIZED
                          | CoVegas v2 self-replay PASS | Historical CoVegas A3 INCOMPLETE
FORMAL VERDICT CHANGES:   <none unless a qualifying result is obtained; tracked per phase>
NEW NETWORK CAPTURES:     <tracked at Phase 8>
NEW DIFFERENTIAL REPLAY:  <tracked at Phase 10>
```

### Binding claim boundary (verbatim, used in all current-facing docs)

> CCReplay answers what a congestion-control implementation computes at a recorded callback
> boundary. It does not claim what network trajectory or performance that implementation would have
> produced.

### Authorized scope

Offline: ABI compat matrix; CoVegas control-flow audit; reconstructed-v3 A3-only candidate +
positive/negative controls + guard-ratio analysis; deterministic professor-demo package; full
regression suite. Network: ONE capped historical capture campaign (`HOLD_MS=500`, validated
Gate-3-R2 topology, ABI v2, fixed/v4) — `MAX_VALID_RUNS=9`, `MAX_VALID_BOUNDARIES=27`,
`MAX_TOTAL_ATTEMPTS=12`; STOP on first same-episode H+D. Optional: replay performance
characterization (dropped first under time pressure). **Forbidden:** upgrade CUBIC R3; call the
historical case FAIL; claim A3 localization without a qualifying diff; general byte/bit exactness;
claim ~780 ns measured; claim CoVegas `undo_cwnd` ABI-v2 trace validation; change `HOLD_MS`/workload
params; exceed the cap; arbitrary event deletion; weaken an oracle; redefine H/D after results;
rewrite predictions; modify `~/cn-spike` / `~/cn` / `~/cn-spike/covegas`.

### Planned phase order

0 ABI compat matrix → 1 CoVegas control-flow audit → 2 precommit A3 predictions → 3 reconstructed-v3
candidate → 4 positive/negative controls → 5 guard-ratio analysis → 6 professor demo package →
7 precommit capture campaign → 8 capture campaign → 9 outcome matrix → 10 conditional historical
diff → 11 freeze/close → 12 optional historical demo → 13 optional performance → 15 full regression
→ 16 git ordering → 17 handoff assembly + adversarial self-check → 18 terminal summary.

### Commit trail (in order)

```text
263ca60  (start)
<phase commits appended here>
```

---

## PHASE 0 — ABI COMPATIBILITY MATRIX

**Result: `ABI_COMPATIBILITY = CLEAN` — 0 `MISPARSED` cells.** Full report:
`REPORT_ABI_COMPATIBILITY_MATRIX.md`; data: `data/abi_compat_matrix.json`; script:
`data/audit_src/abi_compat_matrix.py`.

| boundary | v0 trace | v1 trace | v2 trace |
| --- | --- | --- | --- |
| `ccr_trace.parse_trace` (v0) | ACCEPTED_CORRECTLY | REJECTED_CLEANLY (`unknown trace_version 1`) | REJECTED_CLEANLY (`unknown trace_version 2`) |
| `ccr_trace_v1.parse_trace_v1` (v1) | REJECTED_CLEANLY (`unknown trace_version 0`) | ACCEPTED_CORRECTLY | REJECTED_CLEANLY (`unknown trace_version 2`) |
| `ccr_trace_v2.parse_trace_v2` (v2) | REJECTED_CLEANLY (`unknown trace_version 0`) | REJECTED_CLEANLY (`unknown trace_version 1`) | ACCEPTED_CORRECTLY |
| `ccreplay_diff._detect_version_and_parse` | ACCEPTED_CORRECTLY | ACCEPTED_CORRECTLY | REJECTED_CLEANLY (`ValueError: unsupported trace_version 2`) |
| `validate_run` / `_v1` / `_v2` (own version) | ACCEPTED_CORRECTLY (`pass=True`) | ACCEPTED_CORRECTLY (`pass=True`) | ACCEPTED_CORRECTLY (`pass=True`) |

Committed-trace re-verification: all 10 committed `.ccr` (3× v0, 4× v1, 3× v2) re-parse and
re-validate; recomputed `pass` == committed `pass` for every one. `unittest` 40/40 OK.

Design note: there is no single auto-dispatching parser — each replay entrypoint hardcodes the
parser for its ABI version; `ccreplay_diff` peeks the header and dispatches v0/v1 (v2 rejected
cleanly). No `MISPARSED` path exists at any official boundary.

`ABI_COMPATIBILITY = CLEAN → continue.`

---

## PHASE 1 — COVEGAS CONTROL-FLOW AUDIT

Full audit: `data/covegas_control_flow_audit_phase1.md`.

### 1.1 `handle_minrtt_probe()` return-zero state preservation

Path table (`user/covegas_model.py:293-330`; identical branch structure in
`bpf/covegas_wrapper.bpf.c:349-398` and `~/cn-spike/covegas/src/covegas.bpf.c:606-662`):

| path | condition | writes | return |
| --- | --- | --- | --- |
| P1 | probing AND probe elapsed | min_rtt_us, epoch_start (COMPETE+epoch), minrtt_probing←0, last_minrtt_probe_ns | **True** |
| P2 | probing AND not elapsed | none | **True** |
| P3 | not probing AND period elapsed | cwnd_before_minrtt_probe, minrtt_probe_min_us, minrtt_probing←1, probe_action_start_ns, dlv_rate_max | **True** |
| P4 | not probing AND period not elapsed | none | **False** (the only False path) |

Every write path returns True; the only False path (P4) performs no assignment.
```text
MINRTT_RETURN_ZERO_STATE_PRESERVATION = CONFIRMED
```
The model wraps `ca = dict(ca)` at entry (caller's `ca` never mutated); scanner passes `dict(ca)`
and, on `probe_ran == False`, proceeds with its original `ca` == model's `next_ca` (P4). Scanner
not rewritten to carry an equivalent object.

### 1.2 Predicate-D scanner control-flow audit

6-gate comparison (cwnd-limited → handle_minrtt_probe → mode dispatch → dlv_rate_compete branch →
settle-time gate [both jiffies endpoints] → 3/4 guard) against `handle_compete_mode:360-379`:
**every gate matches; no earlier gate omitted; integer arithmetic (`u32`, `//`) matches;
`RATE_SETTLE_MS=1000`, `CONFIG_HZ=250` → threshold 250 jiffies.** Time-origin investigation not
reopened (accepted result carried).

```text
A3_TRACK_BLOCKED = NO   -> proceed to Phase 2
```

## PHASE 2 — A3 PRECOMMIT

`data/a3_reconstructed_candidate_predictions.md` committed at **`b8af8c1`** — BEFORE
`user/covegas_model_v3_latch.py` existed (git ordering provable). Key precommits:

- 2.1 existing traces: fixed/v4 vs reconstructed-v3 → NO DIVERGENCE ×3 (cross-validation, not
  historical reproduction).
- 2.2 synthetic positive control: source event `raw/covegas_replay/primary/rep1.ccr seq=608`
  (v4 guard TRUE, ratio 231866/566686=0.409); mutate exactly `dlv_rate_bps ← dlv_rate_max`;
  predicted fixed post mode=DELAY / dlv_rate_compete=0, v3 post mode=COMPETE /
  dlv_rate_compete=566686, DIVERGENCE=YES.
- 2.3 historical candidate = H AND D same episode; do NOT assert H⟹D. Archived ratio ≈ 0.9977.
- 2.4 historical-diff prediction (if H+D obtained and `D_hist == D_first`): first divergence =
  `D_hist`, callback `cong_avoid`; else no localization claim.

Supporting: `data/a3_settle_latch_events.json` — the 9 settle-latch guard evaluations, all
guard-PASS.

## PHASE 3 — RECONSTRUCTED-v3 CANDIDATE

`user/covegas_model_v3_latch.py`. Exact semantic patch (`data/a3_reconstructed_candidate_diff.md`):
the A3 guard `if dlv_rate_bps < ¾·dlv_rate_max { latch } else { revert; return }` becomes an
unconditional `dlv_rate_compete = dlv_rate_bps`. A1/A2 unchanged; no changed constants; no
parser/recorder change. `transition()` delegates to `covegas_model.transition` with
`handle_compete_mode` locally swapped (reversible).

Mechanical verification (`data/a3_candidate_controls.json`): normalised source comparison — lines
removed from v4 are exactly `if …< ¾·max:`, `else:`, `revert_to_delay(…)`, `return …`; nothing else
changed; `transition` delegates. **`ONLY_A3_SEMANTIC_DIFFERENCE = YES`.**

`user/ccreplay_diff.py` extended: `trace_version == 2` dispatch + mode-dependent `comparison_fields`
path (used when a module exposes `comparison_fields` not `COMPARISON_FIELDS`). v0/v1 paths
unchanged — N4 hard-negative (Reno + CUBIC NO DIVERGENCE), N5 bug1 (DIVERGENCE seq=1705 `ssthresh`
`result`), `unittest` 40/40 all re-verified.

## PHASE 4 — CANDIDATE CONTROLS

| control | result |
| --- | --- |
| 4.1 synthetic positive (rep1 seq=608, `dlv_rate_bps←dlv_rate_max`) | **PASS** — fixed post mode=DELAY / dlv_rate_compete=0; v3 post mode=COMPETE / dlv_rate_compete=566686; DIVERGENCE=YES; all other synthetic private fields changed = NONE — matches precommit exactly |
| 4.2 fixed/v4 vs fixed/v4 (rep1/2/3) | **NO DIVERGENCE ×3** (63,329 / 62,899 / 64,049 events) |
| 4.3 fixed/v4 vs reconstructed-v3 (rep1/2/3) | **NO DIVERGENCE ×3** — matches precommit (Predicate D absent) |

`ALL_CONTROLS_PASS = YES`. Interpretation: the synthetic control proves the v3 module is active and
differs at the A3 branch; the 3 unmodified traces independently produce NO DIVERGENCE, matching the
scanner's Predicate-D-absent prediction.

## PHASE 5 — GUARD-RATIO ANALYSIS

`data/a3_guard_ratio_analysis.md`. All 9 current eligible settle-latch evaluations (one per COMPETE
episode, all ON-period): ratio `dlv_rate_bps/dlv_rate_max` range **0.2402 – 0.4092**, all **PASS**
the v4 `< 0.75` guard. Archived off-period positive: **0.9977 → FAIL**. Mechanism-consistent
empirical evidence; **not** proof that workload phase causally determines the ratio, and **not**
`H ⟹ D`.

## PHASE 6 — PROFESSOR DEMO PACKAGE

`scripts/demo/` (5 files) + `data/demo/` (`DEMO_NUMBERS.md`, rehearsal logs, checkpoint file).
Deterministic, offline, no network, no UI. Presenter guide: `scripts/demo/README.md`.

| script | what it shows | rehearsal result |
| --- | --- | --- |
| `demo_01_negative_control.sh` | `user.cubic_model` vs itself, `raw/cubic_replay/primary/rep1.ccr` | **NO DIVERGENCE**, 78,688 events, exit 0 |
| `demo_02_first_divergence.sh` | `user.cubic_model` vs `user.cubic_model_bug_ssthresh` (+1 ssthresh) | **FIRST DIVERGENCE** event 1704 / seq 1705 / `ssthresh` / `result` (ref 145, cand 146), exit 0 |
| `demo_03_checkpoint_reproducer.sh` | reproduce that divergence from checkpoint@1500 + 204-event suffix | REPRODUCED, IDENTICAL RESULT = True, exit 0 |
| `demo_00_run_all.sh` | runs 1→2→3 | **EXIT 0**, wall-clock **1.56 s**, peak RSS 240 MB (`data/demo/demo_rehearsal_stdout.txt` / `_stderr.txt`) |

All demo outputs agree with the committed N4 / N5 / N6 reports. `data/demo/DEMO_NUMBERS.md` cites a
repository source path for every value (Reno / CUBIC / N4-N6 / CoVegas / historical status). No
demo step depends on a new capture; the optional `demo_04_historical_a3.sh` exists only if Phase
10A succeeds.

Phase-6 gate: ABI compat was CLEAN (Phase 0) and N4/N5/N6 evidence is intact → demo package is
BANKED regardless of what the A3 network track does.

## PHASE 7 — CAMPAIGN PRECOMMIT

`data/final_historical_capture_campaign.md` committed at **`8ce243a`** — BEFORE the first capture.
Caps: `MAX_VALID_RUNS=9`, `MAX_VALID_BOUNDARIES=27`, `MAX_TOTAL_ATTEMPTS=12`. Stop on first
`H_AND_D_IN_SAME_EPISODE`. Config exactly preserved (`HOLD_MS=500`, Gate-3-R2, ABI v2, fixed/v4).

## PHASE 8 — CAMPAIGN + PHASE 9 OUTCOME

Full report: `REPORT_FINAL_HISTORICAL_CAPTURE_CAMPAIGN.md`. Per-attempt data:
`data/historical_capture_campaign_results.json`. Analyzer: `data/audit_src/campaign_analyze_one.py`.

| attempt | valid run | trace | valid | drops | gaps | dom events | D→C | H (ROBUST_OFF) | D (guard-fail) | H+D | outcome |
| ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | `rep1.ccr` | yes | 0 | 0 | 65,484 | 3 | 0 | 0 | 0 | NEITHER |
| 2 | 2 | `rep2.ccr` | yes | 0 | 0 | 56,120 | 7 | 0 | 0 | 0 | NEITHER |
| 3 | 3 | `rep3.ccr` | yes | 0 | 0 | 60,620 | 3 | 0 | 0 | 0 | NEITHER |
| 4 | 4 | `rep4.ccr` | yes | 0 | 0 | 68,424 | 5 (1 **ROBUST_OFF**) | **1** | **1** | **1** | **H+D_SAME_EPISODE** |

```text
TOTAL ATTEMPTS 4 (cap 12) | VALID RUNS 4 (cap 9) | INVALID 0 | VALID BOUNDARIES 12 (cap 27)
H 1 | D 1 | H+D SAME EPISODE 1 | STOP: H_AND_D_IN_SAME_EPISODE = YES (never continue after first)
OUTCOME CLASS: 1 -- HISTORICAL DIFFERENTIAL CANDIDATE ACQUIRED
```

Acquired episode (`raw/covegas_campaign/rep4.ccr`, sha256 `1aeabe02…`):
- **Predicate H** — DELAY→COMPETE `seq=9533`, t=25.489 s, window `[24.84, 25.74]` ⊂ OFF-period 1
  `[20.69, 40.69]` → **ROBUST_OFF**.
- **Predicate D** — settle-latch guard eval `seq=10421`, t=26.486 s (**0.997 s after H**),
  `dlv_rate_bps=1,192,908 / dlv_rate_max=1,197,822` → **ratio 0.9959 ≥ 0.75 → v4 guard FAILS**;
  `elapsed_jiffies=250/250` under both jiffies endpoints (no flip); same episode as H.
- `D_COUNT = 1` → **`D_hist == D_first`** → Branch 10A.
- Guard ratios across all 4 attempts: ON-period episodes 0.097–0.711 (all PASS); the one
  OFF-period episode 0.9959 (FAIL) — same mechanism as the archived historical positive (~0.998).

## PHASE 10A — HISTORICAL DIFFERENTIAL REPLAY

```text
python3 user/ccreplay_diff.py raw/covegas_campaign/rep4.ccr raw/covegas_campaign/rep4.meta.json \
  --reference user.covegas_model --candidate user.covegas_model_v3_latch
```

```text
matched events before divergence: 10,420
FIRST DIVERGENCE: event_index 10420 / seq 10421 / cong_avoid   (== D_hist == D_first; CLOCK_STABLE)
  priv_post_mode                 v4 = 0 (DELAY)      v3 = 1 (COMPETE)
  priv_post_dlv_rate_compete     v4 = 0             v3 = 1,192,908  (latched dlv_rate_bps)
  post_snd_cwnd                  v4 = 37            v3 = 65
  + priv_post_detect_count, priv_post_recent_min_us, priv_post_last_compete_exit_jiffies,
    priv_post_delay_*  -- v4 ran revert_to_delay(); v3 ran cubic_growth()
```

**Matches the precommitted prediction (`data/a3_reconstructed_candidate_predictions.md` §2.4,
`b8af8c1`) in every particular** → `HISTORICAL DIFFERENTIAL REPLAY = PASS` (narrow sense):

> On the recorded fixed/v4 callback stream, reconstructed-v3 first differs from fixed/v4 at the
> precommitted Predicate-D event (`seq=10421`, `cong_avoid`) in the historical off-period COMPETE
> episode entered at `seq=9533`.

Not claimed: alternate throughput / RTT / queue state / a recreated network outcome.

Optional historical suffix reproducer (`user/ccreplay_checkpoint.py`, extended for v2; N6 v1
regression unchanged): checkpoint@event 10000 + **420-event suffix** (events 10001..10420)
reproduces the identical divergence.

## PHASE 11 — CLOSE

`data/historical_case_freeze_decision.md`: **`HISTORICAL NETWORK ACQUISITION CLOSED SUCCESSFULLY`**.
No further historical network campaign authorized (hard-termination clauses). Formal verdict change:
**Historical CoVegas A3: INCOMPLETE → CLOSED SUCCESSFULLY** (narrow-sense differential-replay PASS).
CUBIC R3 still PARTIAL; CoVegas v2 self-replay still PASS; Reno v0 still PASS.

## PHASE 12 — OPTIONAL HISTORICAL DEMO

_(appended after Phase 12)_

## PHASE 13 — PERFORMANCE

_(appended or SKIPPED)_

## PHASE 15 — FULL REGRESSION SUITE

_(appended)_

## PHASE 17 — ADVERSARIAL SELF-CHECK

_(appended)_

## PHASE 18 — TERMINAL SUMMARY

_(appended)_
