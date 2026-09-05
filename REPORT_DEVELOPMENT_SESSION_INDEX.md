# Session Index

Chronological index of CCReplay work sessions. See `docs/REPO_WORKFLOW.md` for the convention
this table follows.

| Phase | Status | Duration | Report | Commit | Continue? |
| ----- | ------ | -------: | ------ | ------ | --------- |
| Phase 1 — recorder viability + Reno replay (R0/R1/R2) | **PASS** | one session | [REPORT_PHASE1_RENO_REPLAY_VALIDATION.md](REPORT_PHASE1_RENO_REPLAY_VALIDATION.md) | `9ebe25a` (report), `a9253dc` (purity-check fix) | Stopped by design — [docs/archive/PHASE1_R0_R2_IMPLEMENTATION_BRIEF.md](docs/archive/PHASE1_R0_R2_IMPLEMENTATION_BRIEF.md) §23: "Once R0/R1/R2 are complete, STOP. Do not continue automatically into R3." |
| N0 — recorder overhead sanity investigation | **COMPLETE** | 22:22–22:39 UTC (17 min, budget 1h) | [REPORT_RECORDER_OVERHEAD_SANITY_CHECK.md](REPORT_RECORDER_OVERHEAD_SANITY_CHECK.md) | `a89a39c` | Yes — proceed to N1 (CUBIC capability + contract audit) |
| N1 — CUBIC capability + contract audit | **COMPLETE** | 22:41–23:10 UTC (29 min, budget 3h) | [data/cubic_replay_capability_audit.md](data/cubic_replay_capability_audit.md), [data/cubic_replay_contract_predictions.md](data/cubic_replay_contract_predictions.md), [data/cubic_replay_callback_manifest.md](data/cubic_replay_callback_manifest.md), [data/cubic_replay_callback_coverage_plan.md](data/cubic_replay_callback_coverage_plan.md), [data/cubic_replay_kernel_source_correction.md](data/cubic_replay_kernel_source_correction.md) | `958ea88`, `9b51caf`, `346ed0d` | Yes — proceed to N2/N3 (Replay ABI v1 + CUBIC recorder) |
| N2/N3 — Replay ABI v1 + CUBIC recorder + R3A/R3B replay | **PARTIAL** | 23:10–02:0x UTC (~2h50m, budget 4h) | [REPORT_CUBIC_REPLAY_VALIDATION.md](REPORT_CUBIC_REPLAY_VALIDATION.md) | `d417b2d`, `8b6336d`, `2c9ba3d`, `4019601`, (this phase's final commit) | Yes — PARTIAL meets continuation condition, proceed to N4 (differential debugger core) |

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
transitions replayed byte-exact per trace, all 16 private fields demonstrated to change
nontrivially (closes `docs/LIMITATIONS.md` #13), before the first divergence in each trace — always
a `CLOCK_AMBIGUOUS` event (0.02% of events), characterized via a diagnostic (not adopted) as a
genuinely irreducible measurement-boundary condition, not a model or recorder defect (new
`docs/LIMITATIONS.md` #14). One real category-B model bug (`_tcp_friendliness` loop→closed-form
off-by-one) was found and fixed via R3A's full-16-field comparison schema before this report was
written (`data/cubic_replay_model_changes.md`). **R3 verdict: PARTIAL** — continuation condition
met in full; `undo_cwnd` marked `UNVALIDATED` (0 events across all three reps, as predicted).
Mandatory Phase-1 regression (40 tests: 26 v0 + 14 v1) reverified clean throughout; source repos
untouched. Full detail: `REPORT_CUBIC_REPLAY_VALIDATION.md`.
