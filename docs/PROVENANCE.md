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

## Rules

1. Record source commit at copy time.
2. Record even trivial edits.
3. Never edit source repositories in place.
4. If copied logic changes semantics, label it adapted.
5. Historical case-study code must preserve enough version identity to explain the bug/fix difference.
