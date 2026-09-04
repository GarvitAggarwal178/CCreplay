# Provenance

Read-only source repositories:

- `~/cn-spike`
- `~/covegas`
- `~/cn`

Anything reused must be copied into CCReplay and recorded here.

## Table

| CCReplay file | source path | source commit | copied/adapted | exact change |
|---|---|---|---|---|
| | | | | |

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
