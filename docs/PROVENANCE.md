# Provenance

Read-only source repositories:

- `~/cn-spike`
- `~/covegas`
- `~/cn`

Anything reused must be copied into CCReplay and recorded here.

## Table

`~/cn-spike` HEAD at copy time: `022c2e214d4b05012ce379e8b3a14787ee6dff43` (repo has pre-existing
uncommitted local changes unrelated to this task — modified `CLAUDE.md`, untracked Gate 9/covegas
material — recorded in `data/readonly_repo_baseline.txt`, not caused by CCReplay work).

| CCReplay file | source path | source commit | copied/adapted | exact change |
|---|---|---|---|---|
| `bpf/vmlinux.h` | `~/cn-spike/vmlinux.h` | `022c2e2` | copied | none (this kernel's BTF dump, byte-identical) |
| `bpf/bpf_tracing_net.h` | `~/cn-spike/bpf_src/bpf_tracing_net.h` | `022c2e2` | copied | none |
| `scripts/setup_topology.sh` | `~/cn-spike/scripts/gate3r2_setup_topology.sh` | `022c2e2` | copied | renamed only; no `cd` line present in source, none added |
| `scripts/set_qdiscs.sh` | `~/cn-spike/scripts/gate3r2_set_qdiscs.sh` | `022c2e2` | adapted | `cd ~/cn-spike` → `cd ~/ccreplay` (sed), otherwise byte-identical; still takes `B_BYTES` as `$1` |
| `scripts/set_offloads.sh` | `~/cn-spike/scripts/gate3r2_set_offloads.sh` | `022c2e2` | adapted | `cd ~/cn-spike` → `cd ~/ccreplay` (sed), otherwise byte-identical |
| `scripts/teardown_topology.sh` | `~/cn-spike/scripts/gate3r2_teardown.sh` | `022c2e2` | adapted | `cd ~/cn-spike` → `cd ~/ccreplay` (sed), otherwise byte-identical |
| `scripts/verify_bfifo_limit.py` | `~/cn-spike/scripts/gate3r2_verify_bfifo_limit.py` | `022c2e2` | copied | none |
| `bpf/reno_wrapper.bpf.c` (pending) | `~/cn-spike/bpf_src/spike_probe.bpf.c`, `spike_min.bpf.c`, `spike_ctrl.bpf.c` | `022c2e2` | adapted | pattern only: the three `tcp_reno_*` `__ksym` extern declarations and the general struct_ops-wraps-kfunc shape are reused; the wrapper body, event-record layout, sequence/drop-counter logic, and per-callback recorder instrumentation are new CCReplay code, not present in any source file. Recorded again with the exact diff once written. |
| `scripts/build_bpf.sh` (pending) | `~/cn-spike/scripts/gate4a_compile.sh` | `022c2e2` | adapted | reuses the `clang -target bpf -D__TARGET_ARCH_x86 -g -O2 -I ... -c ...` invocation shape; script structure/paths are new. |
| `bpf/covegas_wrapper.bpf.c` (pending) | `~/cn-spike/covegas/src/covegas.bpf.c` | `bab7ab7` (repo HEAD; the file itself was last touched at `b5bc0be`, "v4") | adapted | algorithm logic (mode transitions, cubic-shaped growth, minrtt probe, delivery-rate tracking) copied near-verbatim per ADR-022 (no kernel-native form exists to delegate to via kfunc, unlike Reno/CUBIC); recording instrumentation (PRE/POST snapshots, sequence/drop counters, two-clock brackets, ring-buffer emission) is new CCReplay code, not present in the source. Recorded again with the exact diff once written. |
| `scripts/covegas_run_intermittent.sh` (pending) | `~/cn-spike/covegas/scripts/partC_run_intermittent.sh` | `bab7ab7` | adapted | same workload shape (covegas continuous 120s on port 5201; cubic cross-traffic 20s-on/20s-off ×3 on port 5301) and topology calls, paths/recorder invocation updated for CCReplay; `covegas_consumer`'s ringbuf-CSV consumer is not reused (CCReplay uses its own `.ccr` binary trace format via `build/ccr_recorder_covegas`, not the source repo's CSV telemetry path). |

## Read-only source repository location corrections

- `~/covegas` does not exist as a top-level directory on this machine. The material described in
  "Expected reusable categories" below actually lives at `~/cn-spike/covegas/` (its own nested git
  repo). Inspected there (see `data/inspection_summary.md`); nothing from it was copied into
  CCReplay.
- `~/cn` contains only a copy of the frozen CCReplay documentation set (`CLAUDE.md`, `README.md`,
  `docs/`), not the Gate 0 methodology / environment-notes / run-logging material the category
  list below describes. Nothing was found there to reuse. See `data/inspection_summary.md`.

## Expected reusable categories

### `~/cn-spike`

- validated Gate 3-R2 topology setup;
- qdisc/offload setup;
- parser utilities;
- working BPF struct_ops/ring-buffer patterns;
- validated BPF CUBIC implementation.

### `~/covegas`

- BPF build patterns;
- telemetry-consumer patterns;
- historical buggy/fixed controller versions for the later case study.

### `~/cn`

- Gate 0 methodology;
- reproducibility baselines;
- experiment/run-log discipline.

## Repository self-provenance

The original Phase-1 (R0/R1/R2) implementation task brief was archived verbatim from the former
root-level `INSTRUCTIONS.md` to `docs/archive/PHASE1_R0_R2_IMPLEMENTATION_BRIEF.md` (`git mv`,
contents byte-identical — a path change only). Root `INSTRUCTIONS.md` was then replaced with the
permanent unattended-work operating rules document that governs all sessions from Phase 1 onward.

## External (non-read-only-repo) source reference

`data/kernel_source_ref/tcp_cubic.c` — fetched from
`https://raw.githubusercontent.com/microsoft/WSL2-Linux-Kernel/linux-msft-wsl-6.18.33.2/net/ipv4/tcp_cubic.c`
(public GitHub tag matched to this machine's exact `uname -r`, confirmed via the repo's Releases
API, not guessed), 2026-09-04, sha256
`730015587ab59bc17fa725c5167c8cf4a828d04e630fae7267e7df2c4ee84191`. Read-only reference material for
the N2/N3 CUBIC replay model design — never executed, never linked into the CCReplay build. Not
subject to the `~/cn-spike`/`~/covegas`/`~/cn` read-only-repo rules above (it is not one of those
repos), but held to the same "record source and treat as authoritative, do not silently alter"
standard. See `data/cubic_replay_kernel_source_correction.md` for why it superseded
`~/cn-spike/bpf_src/bpf_cubic.c` as the CUBIC algorithm reference. Full provenance detail (resolved
commit hash, cross-checks performed, disclosed WSL-patch uncertainty) is in
`data/kernel_source_ref/CUBIC_SOURCE_PROVENANCE.md` — this note is now a pointer, not the primary
record.

## Rules

1. Record source commit at copy time.
2. Record even trivial edits.
3. Never edit source repositories in place.
4. If copied logic changes semantics, label it adapted.
5. Historical case-study code must preserve enough version identity to explain the bug/fix difference.
