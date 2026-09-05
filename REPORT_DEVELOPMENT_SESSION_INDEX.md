# Session Index

Chronological index of CCReplay work sessions. See `docs/REPO_WORKFLOW.md` for the convention
this table follows.

| Phase | Status | Duration | Report | Commit | Continue? |
| ----- | ------ | -------: | ------ | ------ | --------- |
| Phase 1 — recorder viability + Reno replay (R0/R1/R2) | **PASS** | one session | [REPORT_PHASE1_RENO_REPLAY_VALIDATION.md](REPORT_PHASE1_RENO_REPLAY_VALIDATION.md) | `9ebe25a` (report), `a9253dc` (purity-check fix) | Stopped by design — [docs/archive/PHASE1_R0_R2_IMPLEMENTATION_BRIEF.md](docs/archive/PHASE1_R0_R2_IMPLEMENTATION_BRIEF.md) §23: "Once R0/R1/R2 are complete, STOP. Do not continue automatically into R3." |
| N0 — recorder overhead sanity investigation | **COMPLETE** | 22:22–22:39 UTC (17 min, budget 1h) | [REPORT_RECORDER_OVERHEAD_SANITY_CHECK.md](REPORT_RECORDER_OVERHEAD_SANITY_CHECK.md) | `a89a39c` | Yes — proceed to N1 (CUBIC capability + contract audit) |
| N1 — CUBIC capability + contract audit | **COMPLETE** | 22:41–23:10 UTC (29 min, budget 3h) | [data/cubic_replay_capability_audit.md](data/cubic_replay_capability_audit.md), [data/cubic_replay_contract_predictions.md](data/cubic_replay_contract_predictions.md), [data/cubic_replay_callback_manifest.md](data/cubic_replay_callback_manifest.md), [data/cubic_replay_callback_coverage_plan.md](data/cubic_replay_callback_coverage_plan.md), [data/cubic_replay_kernel_source_correction.md](data/cubic_replay_kernel_source_correction.md) | `958ea88`, `9b51caf`, `346ed0d` | Yes — proceed to N2/N3 (Replay ABI v1 + CUBIC recorder) |
| N2/N3 — Replay ABI v1 + CUBIC recorder + R3A/R3B replay | **PARTIAL** | 23:10–02:07 UTC (~2h57m, budget 4h) | [REPORT_CUBIC_REPLAY_VALIDATION.md](REPORT_CUBIC_REPLAY_VALIDATION.md) | `d417b2d`, `8b6336d`, `2c9ba3d`, `4019601`, `758f945` | Yes — PARTIAL meets continuation condition, proceed to N4 (differential debugger core) |
| N4 — differential debugger core | **COMPLETE** | 02:07–02:11 UTC (budget 1.5h) | [REPORT_DIFFERENTIAL_DEBUGGER.md](REPORT_DIFFERENTIAL_DEBUGGER.md) | `9097835` | Yes — hard negative oracle PASS for both Reno and CUBIC, proceed to N5 (controlled regression case study) |
| N5 — controlled regression case study | **PASS** | 02:11–02:16 UTC (budget 1.5h) | [REPORT_CONTROLLED_REGRESSION_CASE_STUDY.md](REPORT_CONTROLLED_REGRESSION_CASE_STUDY.md) | `4d2972e` (predictions), `2f82a9c` (results) | Yes — proceed to N6 (checkpoint + suffix reproducer) |
| N6 — checkpoint + suffix reproducer | **COMPLETE** | 02:17–02:19 UTC (budget 1h) | [REPORT_CHECKPOINT_REPRODUCER.md](REPORT_CHECKPOINT_REPRODUCER.md) | `d2f2adb` | Session ends here per pipeline — do not begin the historical CoVegas case study |
| Part A — evidence-language corrections | **COMPLETE** | 10:16–10:24 UTC | (folded into `REPORT_CUBIC_REPLAY_VALIDATION.md` + new `data/kernel_source_ref/CUBIC_SOURCE_PROVENANCE.md`) | `6e95112` | Yes — proceed to Part B |
| Part B — `undo_cwnd` auxiliary coverage | **COMPLETE (VALIDATED)** | 10:24–10:29 UTC | (folded into `REPORT_CUBIC_REPLAY_VALIDATION.md`) | `f4276f7` | Yes — R3 remains PARTIAL, proceed to Part C |
| Part C — clock-boundary investigation | **COMPLETE** (`ATTRIBUTED_AND_CHARACTERIZED`) | 10:29–10:31 UTC | [REPORT_CUBIC_CLOCK_BOUNDARY_INVESTIGATION.md](REPORT_CUBIC_CLOCK_BOUNDARY_INVESTIGATION.md) | `4cb3ee2` | Yes — does not upgrade R3 to PASS; proceed to Part D (CoVegas readiness audit) |
| Part D — CoVegas selection + predictions + Replay Contract audit | **COMPLETE** | 10:31–10:38 UTC | [data/historical_regression_selection.md](data/historical_regression_selection.md), [data/historical_regression_predictions.md](data/historical_regression_predictions.md), [data/covegas_replay_capability_audit.md](data/covegas_replay_capability_audit.md) | `1fd158e`, `d1998e4`, `e58339f`, `b0aac41` | Yes — proceed to Part E (CoVegas self-replay gate) |
| Part E — CoVegas self-replay fidelity gate | **PASS** | 10:38–11:09 UTC | [REPORT_COVEGAS_REPLAY_FIDELITY.md](REPORT_COVEGAS_REPLAY_FIDELITY.md) | `84efbe3`, `9e4f155` | Yes — unqualified PASS, proceed to Part F |
| Part 8 / Part F — historical trigger verification + differential case | **INCOMPLETE** (blocker: `TRIGGER NOT REPRODUCED`) | 11:03–11:09 UTC | [REPORT_HISTORICAL_COVEGAS_REGRESSION.md](REPORT_HISTORICAL_COVEGAS_REGRESSION.md), [data/historical_trigger_validation.md](data/historical_trigger_validation.md) | `5798816` | No — 3 bounded attempts exhausted per the addendum; not a FAIL, Part E's PASS unaffected |
| Current-state handoff + evidence reconciliation (round 1) | **COMPLETE** (docs only) | 2026-09-05 | [docs/CURRENT_STATE.md](docs/CURRENT_STATE.md) (new authoritative status doc) | `bb0fb3e` | Yes — no gate verdict changed; recomputed full-46 CUBIC clock attribution, corrected historical trigger denominators, classified CoVegas `undo_cwnd` as Outcome A, traced CoVegas ktime dataflow |
| Evidence reconciliation + A3 divergence predicate audit (round 1) | **COMPLETE** (docs + 2 offline scanners) | 2026-09-05 | [REPORT_EVIDENCE_RECONCILIATION_AND_A3_PREDICATE_AUDIT.md](REPORT_EVIDENCE_RECONCILIATION_AND_A3_PREDICATE_AUDIT.md), [data/historical_a3_predicate_audit.md](data/historical_a3_predicate_audit.md), [data/historical_a3_existing_trace_scan.md](data/historical_a3_existing_trace_scan.md) | `d9677dc` | Superseded by round 2 below |
| A3 scanner control-flow correction + phase-alignment audit (round 2) | **COMPLETE** (docs + scanner fixes) | 2026-09-05 | (folded into the same reports) + [docs/session/LATEST_REVIEW_HANDOFF.md](docs/session/LATEST_REVIEW_HANDOFF.md) | `45aa0ff` | Superseded on the offset bound by round 3 below — added the cwnd-limited gate (0 event-count change), bracketed the event↔schedule clock offset (`Δ ∈ [−0.05,+0.30]s`, lower bound asserted) |
| A3 Predicate-H time-origin final correction (round 3) | **COMPLETE** (docs + scanner offset re-derivation) | 2026-09-05 | (folded into the same reports) + [docs/session/LATEST_REVIEW_HANDOFF.md](docs/session/LATEST_REVIEW_HANDOFF.md) | (this commit) | STOP for project-level review — re-derived the offset from the verified harness happens-before order: `Δ = first_event_wall − cubic_rep1_start_wall ∈ [≈ −0.65, +0.30] s` (upper rigorous, lower loose; empirical Δ ≈ +0.12–0.20 s, positive — round-2 sign was right, lower bound was underived). All 9 DELAY→COMPETE transitions **ROBUST_ON**; historical archive OFF classification "unchanged under ±4 s" (no rigorous bound). Statistical wording corrected (zero-trigger campaign is "plausible/unsurprising", not "the expected outcome"). Interpretation **CASE 4**; no v2 differential-replay candidate |

## Phase 1 summary

R0 (recorder viability), R1 (Reno event-local exact semantic self-replay), and R2 (Reno
stateful-controller exact semantic self-replay) all PASS. 112,051 real kernel callback events
recorded across 3×90s transfers on the validated Gate-3-R2 topology, zero drops, zero sequence
gaps; replayed through a from-scratch userspace Reno model with zero mismatches (R1) and zero
first divergence (R2). Full detail, capability-audit findings, deviations, and R3 readiness notes
are in the linked report.

Work intentionally stopped at the end of Phase 1, per the original task brief (now archived at
`docs/archive/PHASE1_R0_R2_IMPLEMENTATION_BRIEF.md`) — CUBIC (R3) has not been started. Root
`INSTRUCTIONS.md` now holds the permanent unattended-work operating rules, not this historical
brief.

## N0 summary

Root cause found for Phase 1's reported `cong_avoid ≈ 20–25 µs/callback`: the ring-buffer wakeup
mechanism, not `bpf_ktime_get_ns()` or the recorder's own kfunc/`BPF_CORE_READ` work. A
`BPF_RB_NO_WAKEUP` diagnostic variant measured ~232 ns/callback mean vs. ~7,933 ns/callback for the
unmodified production recorder (~34×, reproducible across 3 reps each, non-overlapping
distributions), on loopback (needed for signal at this scale — the rate-limited Gate-3-R2 topology
gives too few events/s to resolve it). Removing the timestamp call showed no detectable effect,
ruling it out as the cause. Not adopted into the production recorder this session (time-budget
constrained); documented as a viable future optimization requiring full Phase-1 regression before
any adoption. Full detail: `REPORT_RECORDER_OVERHEAD_SANITY_CHECK.md`.

Mandatory Phase-1 regression re-verified clean immediately before and after N0 (production recorder
was never touched — all N0 variants are separate files under `bpf/diagnostic/`). Source repos
re-verified unmodified.

## N1 summary

Determined the CUBIC reference strategy empirically rather than assuming it: the kernel's own
`cubictcp_init/cong_avoid/recalc_ssthresh/state/cwnd_event` (plus shared `tcp_reno_undo_cwnd`) are
verifier-load-confirmed callable as kfuncs on this kernel (real program IDs assigned, not just
BTF-present) — a stronger oracle than the read-only `bpf_cubic.c` port's own reimplemented cubic
math, which is used only as the structural reference for field/clock usage. Ground-truthed
`struct bictcp`'s private-state layout via compiled `offsetof`/`sizeof` against a BTF-sourced field
list (17 fields, 16 semantic, corrects a flagged prior "15 fields / 16 names" transcription error).
Found CUBIC depends on two independent, previously-untracked clocks (`tcp_jiffies32` global,
`tp->tcp_mstamp` per-socket) and that `pkts_acked` directly mutates `snd_ssthresh` outside the
`ssthresh` callback's return value — both load-bearing for the Replay ABI v1 design. Precommitted
five named contract-field predictions plus several additional surfaced-but-unlisted fields
(`lsndtime`, `sk_pacing_rate/status`, `CONFIG_HZ`, the `delay_min` cross-callback dependency) before
any empirical recording, per the predictions-before-results rule — no CUBIC trace exists yet. Full
seven-callback manifest and a pre-registration of which callbacks are predicted thin under the
primary Gate-3-R2 workload (`ssthresh`, `set_state`'s loss branch, `cwnd_event`'s idle-resume
branch, `undo_cwnd`) are recorded for later comparison against actual coverage. Mandatory Phase-1
regression (26 tests + R1/R2 on all three `raw/r0/rep*.ccr` traces) reverified clean; source repos
reverified unmodified (git-tracked state identical, zero files under `~/cn-spike` with an mtime
after this session's start — see `data/readonly_repo_n1_check.txt` for the one methodology caveat:
the original aggregate tree-checksum command could not be exactly reproduced this session).

**Correction (same phase, before N2 began):** an advisor-flagged gap — the kfunc-callability probe
had tested six of seven CUBIC callbacks, omitting `pkts_acked` — was closed (`cubictcp_acked`
confirmed callable, program ID 276). Separately, the actual kernel source for this exact kernel
version was fetched from a matched public GitHub tag and found to diverge from the `bpf_cubic.c`
port in three load-bearing ways (time-math rounding order, HyStart round-reset relocated to
`pkts_acked` keyed on `snd_una` rather than `cong_avoid`'s `ack`, a real `sk_gso_max_size` field read
where the port hardcodes a constant) — reversing Prediction #1 (`snd_una`) from NOT REQUIRED to
REQUIRED. Documented transparently in `data/cubic_replay_kernel_source_correction.md` rather than
silently edited into the original files. The real kernel source is now the sole authoritative
reference for the N2/N3 replay model.

## N2/N3 summary

Designed and implemented Replay ABI v1 (ADR-017..021), built `bpf/cubic_wrapper.bpf.c` (all seven
callbacks in one `bpf_ringbuf_reserve` each, verifier-accepted on the first attempt), captured
3×90s primary CUBIC traces on validated Gate-3-R2 (zero drops, gapless), isolated `cubic_root`'s
integer semantics against a verbatim-C reference (10,023 cases, zero mismatches) before trusting
full-trace replay, then ran R3A (event-local) and R3B (stateful). R3A: 100% exact on all 236,042
`CLOCK_STABLE` events (4,485,714 field comparisons); R3B: 51,323–75,603 consecutive sequential
transitions replayed with exact semantic equality per trace, all 16 private fields demonstrated to
change nontrivially (closes `docs/LIMITATIONS.md` #13), before the first divergence in each trace —
always a `CLOCK_AMBIGUOUS` event (0.02% of events), characterized via a diagnostic (not adopted) as
a characterized clock-boundary limitation under the current recorder architecture, not a model or
recorder defect (new `docs/LIMITATIONS.md` #14). One real category-B model bug (`_tcp_friendliness` loop→closed-form
off-by-one) was found and fixed via R3A's full-16-field comparison schema before this report was
written (`data/cubic_replay_model_changes.md`). **R3 verdict: PARTIAL** — continuation condition
met in full; `undo_cwnd` marked `UNVALIDATED` (0 events across all three reps, as predicted).
Mandatory Phase-1 regression (40 tests: 26 v0 + 14 v1) reverified clean throughout; source repos
untouched. Full detail: `REPORT_CUBIC_REPLAY_VALIDATION.md`.

## Parts A–C summary (CUBIC closure)

Tightened evidence language (byte-exact → exact semantic equality; irreducible → characterized
clock-boundary limitation), added a real-evidence event-count accounting table, narrowed N0's
root-cause framing, verified callback naming against the fetched kernel source, and wrote
`data/kernel_source_ref/CUBIC_SOURCE_PROVENANCE.md` (resolved the tag to its exact commit,
disclosed the one unverified WSL-patch uncertainty). Closed `undo_cwnd` via one targeted auxiliary
trace (reorder-induced spurious loss, 12 events, 0 mismatches) — `VALIDATED`, R3 correctly left at
`PARTIAL`. Ran the full expanded clock-boundary investigation (ambiguity-rate arithmetic, two-sided
`{before,after}` attribution — 4/4 `MATCHES_AFTER_ONLY`, 0 `MATCHES_NEITHER` — stateful
resynchronization diagnostic showing zero unexplained `CLOCK_STABLE` divergence, and a bounded
instrumentation feasibility check that came back `NOT CLOSED`): verdict
`ATTRIBUTED_AND_CHARACTERIZED`, which explicitly does not upgrade R3 to `PASS`.

## Parts D–F summary (CoVegas + historical case study)

Selected the CoVegas v3→v4 "A3 latch-guard" regression (permanent COMPETE-mode capture, isolated to
one conditional in `handle_compete_mode`) from the read-only `~/cn-spike/covegas` history,
precommitted predictions (exact event/field left `UNKNOWN`), and audited the Replay Contract —
confirming directly from source that the union genuinely aliases memory across a mode transition,
and that `last_max_cwnd`/`epoch_start` sit outside it for exactly the reason the addendum predicted
(shared-callback mutation regardless of mode).

Built the CoVegas recorder/parser/model from scratch (ADR-022..024): no kernel-native reference
exists for CoVegas, so the recorder instruments a copy of the algorithm logic directly rather than
kfunc-delegating. Found and fixed one real recorder bug via a loopback smoke test (duplicate
`bpf_ktime_get_ns()` reads) before touching primary evidence. **Part E fidelity verdict: PASS**
(unqualified) — three primary traces on the historically-relevant intermittent-workload topology,
190,277 events, 4,982,990 field comparisons, **zero mismatches** in event-local replay; first
divergence = **NONE** in stateful replay across all three traces; all 30 private fields (including
both union arms) confirmed to change nontrivially. The clock-transfer question was answered
empirically rather than assumed: neither of CoVegas's two clocks produced a single mismatch on
these traces, a genuinely different outcome from CUBIC's characterized residual.

Attempted the historical trigger (spurious off-period COMPETE entry) across 3 bounded captures, per
the addendum's explicit pre-diff verification requirement — all 3 clean, all 3 showing the trigger
absent (statistically expected). **Denominator correction (later reconciliation, see
`REPORT_EVIDENCE_RECONCILIATION_AND_A3_PREDICATE_AUDIT.md`):** `REPORT_COVEGAS_V4.md`'s historical
`HOLD_MS=500` evidence is **3 runs / 9 off-period boundaries / 1 spurious entry**, not "1 of 9
runs"; the current campaign is **3 runs / 9 off-period boundaries / 0 spurious entries**; a rough
binomial sensitivity figure under an independence assumption is `P(0 in 9) = (8/9)^9 ≈ 34.6%` (the
earlier `~11%/run`, `P(0/3)≈70%` wording used the wrong denominator). Per the addendum, did not run
the diff and report "no divergence," did not retry further, and did not manufacture a different
trigger. **Part F: `INCOMPLETE`**, blocker `TRIGGER NOT REPRODUCED` — not a `FAIL`; Part E's `PASS`
is unaffected.

Mandatory Phase-1/CUBIC/CoVegas regression reverified clean throughout Parts A–F (40 automated
tests + Reno v0 R1/R2 on all three `raw/r0/` traces + CUBIC v1 R3A/R3B on all three
`raw/cubic_replay/primary/` traces + CoVegas E2/E3 on all three `raw/covegas_replay/primary/`
traces). Source repos (`~/cn-spike`, `~/cn-spike/covegas`) verified unmodified throughout: zero
files with an mtime after this session's start, `git status`/`HEAD` unchanged.
