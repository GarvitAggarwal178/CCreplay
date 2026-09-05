# CCReplay — Final Integrated Session — Review Handoff

**One-file review packet**, assembled incrementally as the session runs (not reconstructed at the
end). A reviewer who understands CCReplay's architecture should be able to audit the whole session
from this file. Individual reports / data files / scripts / git history remain authoritative for
their evidence.

---

## SESSION IDENTITY

```text
SESSION:                 Final Integrated Session (OVERNIGHT_EVIDENCE_PIPELINE.md, phases 0-18) + post-success closure
DATE:                    2026-09-05  (post-success closure 2026-09-06)
STARTING COMMIT:         263ca60  "audit: re-derive Predicate-H time-origin offset from harness order"
ENDING COMMIT:           substantive content is at  d6c5b9c  "closure(a3): post-success evidence closure".
                         This handoff file is committed as the immediately following HEAD -- run
                         `git log --oneline -1` for its hash; it contains only this file.
FORMAL VERDICTS AT START: Reno v0 PASS | CUBIC v1 R3 PARTIAL | CUBIC clock residual ATTRIBUTED_AND_CHARACTERIZED
                          | CoVegas v2 self-replay PASS | Historical CoVegas A3 INCOMPLETE
FORMAL VERDICT CHANGES:   Historical CoVegas A3 reconstructed-regression case study:
                          INCOMPLETE (trigger not reproduced) -> PASS  (b8b0a33 + d6c5b9c).
                          Defined precisely: on a newly acquired ABI-v2 fixed/v4 callback stream
                          containing the predeclared historical off-period A3 condition, the
                          precommitted reconstructed-v3 candidate first diverged from fixed/v4 at
                          the precommitted same-episode Predicate-D callback. SEPARATE gate from
                          CoVegas v2 self-replay fidelity (PASS) -- not merged.
                          All other verdicts unchanged (CUBIC R3 re-verified PARTIAL, twice).
NEW NETWORK CAPTURES:     YES -- 4 attempts / 4 valid runs / 12 valid boundaries (cap 12 / 9 / 27);
                          stopped on first same-episode H+D. Topology torn down afterward.
NEW DIFFERENTIAL REPLAY:  YES -- Phase 10A: fixed/v4 vs reconstructed-v3 on raw/covegas_campaign/rep4.ccr.
```

### Commit trail (start → end)

```text
263ca60  (start)
0269774  phase0(abi)      -- ABI compatibility matrix CLEAN
72ec44a  phase1(covegas)  -- control-flow audit, A3_TRACK_BLOCKED = NO
b8af8c1  test(a3)         -- PRECOMMIT reconstructed candidate + campaign predictions
27fd795  feat(a3)         -- reconstructed v3 settle-latch candidate
7b9637a  test(a3)         -- candidate controls + guard-ratio analysis
2f3a1e1  feat(demo)       -- deterministic professor demo package (N4/N5/N6)
8ce243a  test(a3)         -- PRECOMMIT final capped historical acquisition campaign
6245a04  test(a3)         -- per-capture campaign analyzer
f0b3ea1  exp(a3)          -- final historical capture campaign, Outcome 1 (H+D run 4)
b8b0a33  exp(a3)          -- historical differential replay PASS (Branch 10A) + close
7fb7af5  feat(demo)       -- optional historical A3 add-on + full regression
56b539b  docs(session)    -- handoff assembly + adversarial self-check (phases 16-18)
d6c5b9c  closure(a3)      -- POST-SUCCESS evidence closure (ABI/tests/verdict/caveats)
<HEAD>   docs(session)    -- this handoff (post-success closure section)
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
→ 16 git ordering → 17 handoff assembly + adversarial self-check → 18 terminal summary. (13 and 14
are optional/forbidden respectively — see below.) The full commit trail is under SESSION IDENTITY
above.

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
`result`), `unittest` 40/40 all re-verified *at this phase*. **[Superseded by the POST-SUCCESS
CONSISTENCY CLOSURE section: this v2 diff path now also has 7 permanent tests
(`tests/test_ccreplay_diff_v2.py`), suite 40 → 47, and a named provenance limitation.]**

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

`data/a3_guard_ratio_analysis.md`. The 9 *original-primary-trace* eligible settle-latch evaluations
(one per COMPETE episode, all ON-period): ratio `dlv_rate_bps/dlv_rate_max` range **0.2402 –
0.4092**, all PASS the v4 `< 0.75` guard. Archived off-period positive: 0.9977 → FAIL.
**[Post-success closure expands this: the campaign added 17 more ON-period evaluations, extending
the ON range to 0.097 – 0.711 (max 0.7108, still < 0.75), plus the qualifying OFF-period H+D
episode at 0.9959 (FAIL). See CLOSURE item 7.]** Mechanism-consistent empirical evidence; **not**
proof that workload phase causally determines the ratio, and **not** `ON ⇒ PASS` / `OFF ⇒ FAIL` /
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
**Historical CoVegas A3 reconstructed-regression case study: INCOMPLETE → PASS** — a **separate
gate** from CoVegas v2 self-replay fidelity (PASS), not merged. CUBIC R3 still PARTIAL; CoVegas v2
self-replay still PASS; Reno v0 still PASS. (See the POST-SUCCESS CONSISTENCY CLOSURE section below
for the precise PASS definition and the two mandatory caveats.)

## PHASE 12 — OPTIONAL HISTORICAL DEMO

`scripts/demo/demo_04_historical_a3.sh` — `fixed/v4` vs `reconstructed-v3` on
`raw/covegas_campaign/rep4.ccr`; prints the OFF-period H entry (`seq=9533`), the same-episode
Predicate-D event (`seq=10421`), and the first divergence at `seq=10421` (`cong_avoid`):
`priv_post_mode` DELAY↔COMPETE, `priv_post_dlv_rate_compete` 0↔1,192,908, + the
`revert_to_delay`-vs-`cubic_growth` field set. Discloses `reconstructed-v3` is a reconstruction,
not original v3 source; no throughput/RTT/counterfactual claim. `demo_00_run_all.sh` appends it
only when the trace is present; `README.md` + `data/demo/DEMO_NUMBERS.md` updated. Full package
re-rehearsed: **EXIT 0, wall-clock 2.9 s, peak RSS 362 MB** (all 4 steps PASS).

## PHASE 13 — PERFORMANCE

```text
SKIPPED — lower priority than demo/regression/handoff under session budget
          (Phase 13 is explicitly optional and "drop first under time pressure").
```

## PHASE 15 — FULL REGRESSION SUITE (run at candidate-impl time and again at the end)

*(Phase-15 snapshot; the authoritative post-closure run — 47 tests, + the v2 checkpoint reproducer
and final ABI matrix — is in CLOSURE item 14.)*

```text
python3 -m unittest discover -s tests                         -> Ran 40 tests ... OK   (later: 47/47 after +7 v2 tests)
Reno v0   replay_r1.py / replay_r2.py  rep1/rep2/rep3         -> PASS / first divergence NONE
CUBIC v1  replay_r3a.py  (rep1,rep2,rep3)                     -> total_mismatches 4 ; clock_stable_mismatched 0 ;
                                                                 non_ambiguous_first_mismatch null   (R3 = PARTIAL, unchanged)
CUBIC v1  replay_r3b.py  (rep1,rep2,rep3)                     -> pass_first_divergence_is_only_clock_ambiguous: true   (PARTIAL, unchanged)
CoVegas v2 replay_e2.py  (rep1,rep2,rep3)                     -> "pass": true ; total_mismatches 0
CoVegas v2 replay_e3.py  (rep1,rep2,rep3)                     -> "pass": true ; first_divergence null   (PASS, unchanged)
reconstructed-v3 does NOT alter fixed/v4:
  v4.handle_compete_mode.__module__ == "user.covegas_model"   (the transition() swap is reversible)
N4 hard-negative:  ccreplay_diff Reno vs Reno   -> NO DIVERGENCE ;  CUBIC vs CUBIC -> NO DIVERGENCE
N5 bug1:           ccreplay_diff cubic vs cubic_model_bug_ssthresh -> DIVERGENCE seq=1705
demo:             bash scripts/demo/demo_00_run_all.sh        -> EXIT 0
source integrity: ~/cn-spike  git rev-parse --short HEAD -> 022c2e2
                              git status --porcelain | grep '^ M' -> " M CLAUDE.md"  (pre-existing baseline)
                  ~/cn-spike/covegas, ~/cn  untouched;  raw/covegas_campaign/ topology torn down after the campaign
working tree:     clean except the standing untracked exceptions
                  (docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md, instructions.md)
```

## PHASE 16 — COMMIT ORDERING (provable)

```text
263ca60  (start)
0269774  phase0(abi): ABI compatibility matrix -- CLEAN
72ec44a  phase1(covegas): control-flow audit -- A3_TRACK_BLOCKED = NO
b8af8c1  test(a3): PRECOMMIT reconstructed candidate + final campaign predictions   <-- before any A3 impl
27fd795  feat(a3): reconstructed v3 settle-latch candidate                          <-- after b8af8c1
7b9637a  test(a3): candidate positive/negative controls + guard-ratio analysis
2f3a1e1  feat(demo): deterministic professor demo package (N4/N5/N6)
8ce243a  test(a3): PRECOMMIT final capped historical acquisition campaign           <-- before any capture
6245a04  test(a3): per-capture campaign analyzer (tooling)
f0b3ea1  exp(a3): final historical capture campaign -- Outcome 1, H+D acquired (run 4)
b8b0a33  exp(a3): historical differential replay PASS (branch 10A) + close
7fb7af5  feat(demo): optional historical A3 add-on + full regression (Phase 12/15)
56b539b  docs(session): handoff assembly + adversarial self-check (phases 16-18)
d6c5b9c  closure(a3): POST-SUCCESS evidence closure (ABI/tests/verdict/caveats)
<HEAD>   docs(session): this handoff (post-success closure section) -- run `git log --oneline -1`
```

Precommit commits (`b8af8c1`, `8ce243a`) **precede** their result-generating work. All post-success
closure commits (`d6c5b9c`, this one) come **after** every historical prediction/result commit. No
prediction/precommit commit was amended after result generation.

## PHASE 17 — ADVERSARIAL SELF-CHECK

```text
Did any criterion change after results?
  NO. Predicate H / D / same-episode rule and the guard expression / 250-jiffy threshold were
  fixed in data/historical_a3_predicate_audit.md (round 1, d9677dc) and
  data/a3_reconstructed_candidate_predictions.md (b8af8c1). Rounds 2/3 ADDED conditions (cwnd gate,
  offset derivation); this session added nothing to them. The Phase-10A prediction (b8af8c1 sec 2.4)
  was matched, not adjusted.

Was any oracle weakened?
  NO. Exact semantic equality throughout; all replay-gate regressions unchanged.

Was any prediction rewritten?
  NO. data/historical_regression_predictions.md got an APPENDED "RESULTS" section; the D2
  predictions above it are byte-unchanged. data/a3_reconstructed_candidate_predictions.md unchanged.

Was H conflated with D?
  NO. Separate definitions, separate scans, separate same-episode test. Reported independently in
  every attempt record.

Was H => D falsely asserted?
  NO. data/a3_guard_ratio_analysis.md and the campaign report state explicitly it is
  mechanism-consistent evidence, not proof phase determines the ratio. Attempts 1-3 had H=0, D=0;
  attempt 2 had 7 ON-period episodes all guard-PASS.

Was a synthetic event presented as real trace evidence?
  NO. The Phase-4.1 synthetic positive control is labelled "MODULE-WIRING / CANDIDATE-SEMANTICS
  VALIDATION ONLY" everywhere. The Phase-10A result uses the real captured trace
  raw/covegas_campaign/rep4.ccr.

Was historical archive evidence presented as Replay ABI-v2 diff evidence?
  NO. The archived CSV (Ph500_B5x_rep2) is used only for the guard-ratio comparison and detector
  validation; the differential replay ran on the newly captured v2 trace.

Was counterfactual network behavior claimed?
  NO. Every historical-diff statement is bounded to "what the implementation computes at the
  recorded callback boundary" + the verbatim claim boundary. No alternate throughput / RTT / queue
  state / recreated 120 s outcome.

Was CUBIC R3 upgraded?
  NO. R3 = PARTIAL, re-verified in Phase 15.

Was CoVegas undo_cwnd overstated?
  NO. Still Outcome A (0 ABI-v2 trace invocations; function-level evidence only). Not touched.

Was the run cap exceeded?
  NO. 4 total attempts / 4 valid runs / 12 valid boundaries -- caps are 12 / 9 / 27. Stopped on the
  first same-episode H+D per the Phase-7 stop rule.

Were campaign parameters altered?
  NO. HOLD_MS=500, Gate-3-R2 topology, bfifo 250000, 40 ms RTT, 20/20 x3 cross-traffic, ABI v2
  fixed/v4 -- unchanged across all 4 attempts (scripts/covegas_run_intermittent.sh, no edits).

Was probability-of-H confused with probability-of-H+D?
  NO. Only the permitted sensitivity statement (1-(8/9)^27 ~= 95.8% for >=1 H in 27 boundaries) is
  used, immediately followed by "not a power guarantee and does not describe same-episode H+D
  acquisition probability".

Was checkpoint+suffix called minimization?
  NO. "Reproducer, not minimization" stated in every checkpoint context; events before the
  checkpoint are "accounted for by the saved state", the suffix is replayed "in full, in order".
```

## PHASE 18 — TERMINAL SUMMARY

Printed to the terminal at session end (integrated-session and post-success-closure summaries).

---

## POST-SUCCESS CONSISTENCY CLOSURE

Final OFFLINE closure after the historical acquisition success. **No new capture, no new
experiment, no change to Predicate H / D / campaign criteria / historical candidate / replay
oracle.** Commit `d6c5b9c` (comes *after* all historical prediction/result commits — none altered).

### 1. Stale Phase-0 matrix — explanation

At Phase 0, `user/ccreplay_diff.py` supported v0/v1 and **rejected v2 cleanly**
(`ValueError: unsupported trace_version 2`). Phase 3 then *added* Replay-ABI-v2 support to the
differential debugger, and Phase 10 to `ccreplay_checkpoint.py`. So the Phase-0 matrix is
historically correct for that code state but stale for the final repository. Both are preserved.

### 2. Initial vs final ABI matrix (`REPORT_ABI_COMPATIBILITY_MATRIX.md`, `data/abi_compat_matrix.json`)

| boundary / trace | Phase-0 (initial) | FINAL (post-v2) |
| --- | --- | --- |
| `ccr_trace.parse_trace` (v0) | v0 ACCEPTED, v1/v2 REJECTED_CLEANLY | same |
| `ccr_trace_v1.parse_trace_v1` (v1) | v1 ACCEPTED, v0/v2 REJECTED_CLEANLY | same |
| `ccr_trace_v2.parse_trace_v2` (v2) | v2 ACCEPTED, v0/v1 REJECTED_CLEANLY | same |
| `ccreplay_diff._detect_version_and_parse` | v0/v1 ACCEPTED, **v2 REJECTED_CLEANLY** | **v0/v1/v2 all ACCEPTED_CORRECTLY** |
| `validate_run` / `_v1` / `_v2` (own version) | all ACCEPTED (pass=True) | same |

```text
PHASE-0 MISPARSED CELLS: 0        FINAL_MISPARSED_CELLS: 0
```

FINAL v2 differential regression (run inside the audit): `fixed/v4` vs `fixed/v4` → NO DIVERGENCE;
`fixed/v4` vs `reconstructed-v3` → NO DIVERGENCE on `rep1/rep2/rep3`; `fixed/v4` vs
`reconstructed-v3` on `raw/covegas_campaign/rep4.ccr` → DIVERGENCE, first divergence `seq=10421`,
`cong_avoid`. All 14 committed traces re-validate consistent with their committed
`_validation.json`.

### 3. NAMED LIMITATION — v2 diff path implemented in the result-producing session

> The Replay-ABI-v2 differential-debugger path was implemented during the same integrated session
> that produced the CoVegas differential result. Its correctness therefore does not have the same
> prior independent validation history as the older v0/v1 path. Mitigations: the precommitted
> synthetic positive control; `fixed-v4`/`fixed-v4` hard negatives; `fixed-v4`/`reconstructed-v3`
> negatives on three Predicate-D-absent traces; final ABI/version-dispatch regression;
> `tests/test_ccreplay_diff_v2.py` (7 permanent tests); exact agreement with the precommitted
> historical first-divergence prediction.

Disclosed in `docs/CURRENT_STATE.md`, `REPORT_ABI_COMPATIBILITY_MATRIX.md`, the historical
case-study report, `data/demo/DEMO_NUMBERS.md`, and this file — not buried only in git history. It
is a provenance caveat, not an invalidation.

### 4. Permanent v2 debugger tests — `tests/test_ccreplay_diff_v2.py` (7 tests)

| # | test | asserts |
| --- | --- | --- |
| 3.1 | version dispatch | a v2 trace → `hdr.trace_version == 2`, v2 `CALLBACK_NAMES`, v2 `select_dominant_connection` |
| 3.2 | mode-dependent schema | `covegas_model` has no flat `COMPARISON_FIELDS`; `diff_trace` calls `comparison_fields(cb, pre_mode, post_mode)` ≥ 1×; DELAY-arm ≠ COMPETE-arm field lists |
| 3.3 | v2 hard negative | `fixed/v4` vs `fixed/v4` on `rep1.ccr` → NO DIVERGENCE (all events matched) |
| 3.4a | v2 reconstructed-v3 positive | `fixed/v4` vs `reconstructed-v3` on `rep4.ccr` → first divergence `seq=10421`, `cong_avoid`, 10,420 matched; `priv_post_mode` DELAY/COMPETE, `priv_post_dlv_rate_compete` 0/1192908 |
| 3.4b | pre_mode ≠ post_mode | at the Predicate-D event `comparison_fields` is called with `pre_mode != post_mode` (different union-arm selection) |
| 6.1 | CoVegas v2 checkpoint reproducer | `run_with_checkpoints` → divergence `seq=10421`; suffix from nearest checkpoint reproduces identical `event_index`/`seq`/`diff_fields` |
| 6.2 | CUBIC N6 checkpoint regression | divergence event 1704 / seq 1705; checkpoint at 1500; suffix length 204 |

### 5. Final test count

```text
OLD TEST COUNT: 40
NEW TEST COUNT: 47   (+7 tests/test_ccreplay_diff_v2.py)
ALL TESTS PASS: YES  (unittest discover -s tests -> Ran 47 tests ... OK, ~4.3 s)
```

### 6. Historical trace retention + hash

```text
raw/covegas_campaign/rep4.ccr        git-tracked  42,697,344 bytes
raw/covegas_campaign/rep4.meta.json  git-tracked  724 bytes
raw/covegas_campaign/rep4_validation.json  git-tracked (validate_run_v2 pass)
SHA256(rep4.ccr) = 1aeabe0283e3f0a52936391dde18ec86093c524b4f90cad319b901ef067d65de
  recomputed -> HASH MATCH = YES
```

The headline historical result does **not** depend on an untracked local file. A fresh-shell
`bash scripts/demo/demo_04_historical_a3.sh` locates the trace through the committed repository
path and reproduces the divergence.

### 7. Guard-ratio analysis expanded (`data/a3_guard_ratio_analysis.md`)

```text
ORIGINAL PRIMARY 9:                 range 0.2402 - 0.4092   (all PASS)
FINAL CAMPAIGN ON-PERIOD (n = 17):  0.0970 0.1458 0.1463 0.1540 0.2533 0.2617 0.2619 0.2620
                                    0.2655 0.2783 0.3377 0.3428 0.4251 0.4449 0.4574 0.6506 0.7108  (all PASS)
                                    range 0.0970 - 0.7108 ; MAX ON VALUE 0.7108 (< 0.75 threshold)
QUALIFYING OFF-PERIOD H+D:          0.9959   (FAIL -> revert)
ARCHIVED HISTORICAL POSITIVE:       ~0.9977  (FAIL)
INTERPRETATION: mechanism-consistent empirical evidence; NOT proof that workload phase causally
  determines the ratio; NOT  ON => PASS / OFF => FAIL / H => D.
```

### 8. CUBIC N6 regression — `CUBIC_N6_REGRESSION = PASS` (test 6.2; also re-verified in the demo)

### 9. CoVegas v2 checkpoint regression — `COVEGAS_V2_CHECKPOINT_REGRESSION = PASS` (test 6.1)

Suffix-replay divergence (`callback`, `diff_fields`, ref/candidate values) identical to the
full-trace differential output under the declared schema. Reproducer, not minimization.

### 10. Formal reconstructed-regression PASS definition

> **Historical CoVegas A3 reconstructed-regression case study = PASS.** PASS means: on a newly
> acquired Replay-ABI-v2 fixed/v4 callback stream containing the predeclared historical off-period
> A3 condition, the precommitted reconstructed-v3 candidate first diverged from fixed/v4 at the
> precommitted same-episode Predicate-D callback.
>
> Candidate provenance: the buggy candidate is a documented reconstruction of v3's A3 settle-latch
> behaviour from committed v4 source + historical project evidence; original committed v3 source is
> unavailable — a reconstructed-regression case study, not replay of literal original-v3 source.
>
> Debugger-path provenance: Replay-ABI-v2 support in the differential debugger was implemented
> during the same integrated session (see item 3).

Kept as a **separate gate**:

```text
Reno v0 replay fidelity:                                    PASS
CUBIC v1 R3 replay fidelity:                                PARTIAL
CoVegas v2 self-replay fidelity:                            PASS
Historical CoVegas A3 reconstructed-regression case study:  PASS   <-- NOT merged with CoVegas self-replay
```

### 11. Demo `snd_cwnd` presentation caveat

`post_snd_cwnd 37 vs 65` at the first divergence is labelled a **computed boundary value** (each
implementation's output at that recorded callback under the same recorded input state — v4 ran
`revert_to_delay()`, v3 ran `cubic_growth()`), explicitly *not* an alternate cwnd / throughput /
RTT / loss / queue trajectory. Added to `REPORT_FINAL_HISTORICAL_CAPTURE_CAMPAIGN.md`,
`scripts/demo/README.md`, `data/demo/DEMO_NUMBERS.md`, and the `demo_04_historical_a3.sh` output.

### 12. Public Predicate-H wording

Current-facing docs say: *"the run-4 DELAY→COMPETE transition at `seq=9533` was classified inside a
cross-traffic OFF period under the established alignment interval; the classification also remains
OFF under the documented sensitivity analysis."* No new time-origin work; `ROBUST_OFF` is retained
only in the internal scanner output.

### 13. Handoff integrity / placeholder audit

```text
HANDOFF_PLACEHOLDERS_REMAINING = 0   (the two former `<...>` fields -- ENDING COMMIT and the
  copy-paste summary's "end" -- now carry real hashes: content commit d6c5b9c, and the note that
  this file is committed as the immediately following HEAD.)
HANDOFF_CORRUPTED_FIELDS_FOUND = 0   (SESSION IDENTITY, prediction/implementation commits,
  synthetic-control values, all original + campaign ratios, campaign counts, H/D seqs, D ratio,
  first-divergence event, formal verdict lines, source-integrity lines, working tree -- all read
  back from disk and checked against source files, not memory.)
```

### 14. Final regression suite (post-closure, item 5 + item 12 of the closure task)

```text
unittest discover -s tests                                  -> Ran 47 tests ... OK
Reno v0   R1/R2  rep1/rep2/rep3                              -> PASS / first divergence NONE
CUBIC v1  R3A                                               -> 0 CLOCK_STABLE mismatches, 4 CLOCK_AMBIGUOUS,
                                                                non_ambiguous_first_mismatch null  (R3 = PARTIAL)
CUBIC v1  R3B                                               -> pass_first_divergence_is_only_clock_ambiguous: true  (PARTIAL)
CoVegas v2 E2 / E3                                          -> 0 mismatches / first divergence NONE  (PASS)
N4 hard-negative (Reno vs Reno)                             -> NO DIVERGENCE
N5 bug1 (cubic vs cubic_model_bug_ssthresh)                 -> DIVERGENCE seq=1705
v2 fixed/fixed negative (rep1)                              -> NO DIVERGENCE
v2 fixed/v3 negatives rep1/rep2/rep3                        -> NO DIVERGENCE x3
v2 fixed/v3 positive (campaign rep4)                        -> DIVERGENCE seq=10421 cong_avoid
CUBIC N6 checkpoint reproducer                              -> PASS  (checkpoint 1500 -> divergence 1704 -> suffix 204)
CoVegas v2 checkpoint reproducer                            -> PASS  (checkpoint 10000 -> divergence 10420 -> suffix 420)
FINAL ABI compatibility matrix                              -> CLEAN, FINAL_MISPARSED_CELLS = 0
deterministic demo (demo_00_run_all.sh)                     -> EXIT 0, wall-clock 3.07 s
```

### 15. Final commit hashes

```text
b8af8c1  A3 candidate / historical prediction precommit   (unaltered)
27fd795  candidate implementation                          (unaltered)
8ce243a  final capture campaign precommit                  (unaltered)
f0b3ea1  campaign result                                   (unaltered)
b8b0a33  historical differential result                    (unaltered)
7fb7af5  optional historical demo + full regression
56b539b  integrated-session handoff assembly
d6c5b9c  POST-SUCCESS evidence closure (ABI/tests/verdict/caveats)   <-- substantive closure content
<HEAD>   this handoff (post-success closure section)        -- run `git log --oneline -1`
```

### 16. Working tree / source integrity

```text
~/cn-spike           git HEAD 022c2e2 ; only the pre-existing baseline  M CLAUDE.md
~/cn-spike/covegas   clean (untouched)
~/cn                 clean (untouched)
netns                torn down (ip netns list empty)
~/ccreplay working tree: clean except the standing untracked exceptions
  ??  docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md   (task-instructions -- never committed)
  ??  instructions.md                               (stray lowercase -- never committed)
  (neither deleted)
```

### Evidence evolution (do not delete the original Phase-0 result)

```text
Phase 0:               ccreplay_diff (final-at-that-time) rejected v2 cleanly
Phase 3:               v2 support implemented
same session:          precommitted synthetic positive + real negatives validate the candidate path
campaign:              real H+D acquired (valid run 4)
historical diff:       precommitted first-divergence prediction matched exactly
post-success closure:  final-code ABI matrix (both preserved) + 7 permanent automated v2 regressions
```

---

## COPY-PASTE REVIEW SUMMARY

```text
CCReplay -- Final Integrated Session (OVERNIGHT_EVIDENCE_PIPELINE.md, phases 0-18) + post-success closure
start 263ca60  ->  content commit d6c5b9c (this handoff is the immediately following HEAD)
NEW NETWORK CAPTURES: YES (4 attempts)   NEW DIFFERENTIAL REPLAY: YES (Phase 10A)

FORMAL VERDICTS:
  Reno v0 replay fidelity                                    PASS      (unchanged)
  CUBIC v1 R3 replay fidelity                                PARTIAL   (unchanged -- re-verified twice; not upgraded)
  CUBIC clock residual                                       ATTRIBUTED_AND_CHARACTERIZED  (unchanged; full-46 = 2/4/40/0)
  CoVegas v2 self-replay fidelity                            PASS      (unchanged)
  Historical CoVegas A3 reconstructed-regression case study  PASS      <-- verdict change (INCOMPLETE -> PASS)
                                                                          SEPARATE gate; NOT merged with CoVegas self-replay

PHASE 0   ABI COMPATIBILITY = CLEAN (0 MISPARSED); FINAL post-v2 matrix also CLEAN (0 MISPARSED); both preserved
PHASE 1   MINRTT_RETURN_ZERO_STATE_PRESERVATION = CONFIRMED ; scanner control-flow audit: no gate omitted ; A3_TRACK_BLOCKED = NO
PHASE 2   predictions precommit b8af8c1 (before any A3 impl / capture)
PHASE 3   user/covegas_model_v3_latch.py ; ONLY_A3_SEMANTIC_DIFFERENCE = YES
PHASE 4   synthetic positive control PASS (rep1 seq=608) ; fixed/fixed NO DIVERGENCE x3 ; fixed/v3 NO DIVERGENCE x3 (original traces)
PHASE 5   guard ratios (26 ON-period evals: original 9 + campaign 17) 0.097-0.711 all PASS ; OFF-period H+D 0.9959 FAIL ; archived 0.9977
PHASE 6   deterministic professor demo (N4/N5/N6) -- BANKED before network
PHASE 7   campaign precommit 8ce243a (before first capture; caps 9 valid / 27 boundaries / 12 attempts)
PHASE 8   4 attempts / 4 valid runs / 12 valid boundaries / 0 invalid ; run1-3 NEITHER, run4 H+D_SAME_EPISODE -> STOP
          acquired raw/covegas_campaign/rep4.ccr (sha256 1aeabe02...  HASH MATCH = YES ; git-tracked)
          H = DELAY->COMPETE seq=9533 t=25.489s  classified OFF-period under the alignment interval; also OFF under sensitivity
          D = settle-latch guard FAIL seq=10421 t=26.486s  ratio 1,192,908/1,197,822 = 0.9959  elapsed_jiffies 250/250 (both endpoints)
          same episode ; D_COUNT = 1 -> D_hist == D_first -> Branch 10A
PHASE 9   OUTCOME CLASS 1 -- HISTORICAL DIFFERENTIAL CANDIDATE ACQUIRED
PHASE 10A ccreplay_diff  fixed/v4 vs reconstructed-v3  ->  FIRST DIVERGENCE event 10420 / seq 10421 / cong_avoid (CLOCK_STABLE)
          priv_post_mode 0(DELAY) vs 1(COMPETE) ; priv_post_dlv_rate_compete 0 vs 1,192,908
          post_snd_cwnd 37 vs 65 = COMPUTED BOUNDARY VALUE (not an alternate trajectory) ; + priv_post_detect_count / delay_*
          10,420 events matched before divergence ; == matches precommit b8af8c1 sec 2.4 in every particular
          -> Historical CoVegas A3 reconstructed-regression case study = PASS
          suffix reproducer: checkpoint@10000 + 420-event suffix -> identical divergence
PHASE 11  HISTORICAL NETWORK ACQUISITION CLOSED SUCCESSFULLY (no further campaign authorized)
PHASE 12  demo_04_historical_a3.sh added ; full package re-rehearsed EXIT 0 / 3.07 s
PHASE 13  SKIPPED (performance -- lowest priority)
PHASE 15/closure  FINAL regression: unittest 47/47 (was 40; +7 test_ccreplay_diff_v2.py) ; Reno R1/R2 PASS ;
          CUBIC R3A/R3B PARTIAL unchanged ; CoVegas E2/E3 PASS ; N4 NO DIVERGENCE ; N5 bug1 DIVERGENCE seq 1705 ;
          v2 fixed/fixed + fixed/v3 x3 NO DIVERGENCE ; v2 fixed/v3 rep4 DIVERGENCE seq 10421 ;
          CUBIC N6 + CoVegas v2 checkpoint reproducers PASS ; FINAL ABI matrix CLEAN ; demo EXIT 0 ;
          ~/cn-spike 022c2e2 (only pre-existing M CLAUDE.md) ; ~/cn-spike/covegas + ~/cn untouched

NAMED LIMITATION: the Replay-ABI-v2 differential-debugger path (ccreplay_diff.py + ccreplay_checkpoint.py) was
  implemented in the same session that produced the historical result. Mitigations: precommitted synthetic positive
  control ; fixed/fixed + fixed/v3 negatives ; final ABI regression ; 7 permanent automated tests ; exact match to the
  precommitted first-divergence prediction. Provenance caveat, not an invalidation.

NARROW CLAIM (verbatim): "On the recorded fixed/v4 callback stream, reconstructed-v3 first differs from fixed/v4 at the
  precommitted Predicate-D event (seq=10421, cong_avoid) in the historical off-period COMPETE episode entered at seq=9533."
  NOT alternate throughput / RTT / queue state, NOT a recreated network outcome.
  reconstructed-v3 = v4 committed source with only the A3 guard reverted (documented reconstruction, not original v3 source).

NEXT PROJECT PRIORITY: final report framing + prior-art / novelty audit (especially vs DETER). Other un-run work
  (separate methodology): formal recorder non-interference TOST ; Replay ABI field ablation ; prior-art broadening.

FOR EXTERNAL REVIEW SEND ONLY: docs/session/LATEST_REVIEW_HANDOFF.md
```
