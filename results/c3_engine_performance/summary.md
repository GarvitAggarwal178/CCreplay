# Engine Performance Measurement Summary

## Overview

Performance measurements were taken across 4 distinct traces spanning different congestion-control algorithms and trace sizes. Each operation (parse, replay, diff, all-decisions) was repeated 5 times to capture variance.

Test configuration:
- Host: WSL2 Ubuntu kernel 6.18.33.2
- Python: 3.14.4
- CPU cores: 16
- Test run: 2026-10-13 08:18-08:20 UTC
- Traces tested: 2 reno (r0, smoketest), 1 cubic, 1 covegas

## Key Measurements

### Parse Performance

Parse times show consistent linear scaling:

| Trace | Size | Mean Time | Events/sec | Stdev |
|-------|------|-----------|-----------|-------|
| raw/r0/rep1.ccr | 37,260 | 0.072s | 534K | 0.015s |
| raw/smoketest/t1.ccr | 160,518 | 0.361s | 453K | 0.057s |
| raw/cubic_replay/primary/rep1.ccr | 78,688 | 0.436s | 182K | 0.052s |
| raw/covegas_replay/primary/rep1.ccr | 63,329 | 0.451s | 141K | 0.042s |

**CORRECTED (on review):** the original text below claimed "5% variance" between the two Reno
rows; the actual figure is (534-453)/534 ~= 15%, not 5% -- a transcription error, not a re-measurement.
Parse throughput is lower for CUBIC/CoVegas than for Reno; this is at least as plausibly explained by
ABI field-count differences (CUBIC/CoVegas traces carry more semantic private fields per event, per
`docs/CURRENT_STATE.md` section 14) as by trace size, and this data cannot separate the two causes
since each ABI was only tested at one trace size here.

### Stateful Replay (Mode B) Performance

| Trace | Size | Mean Time | Events/sec | Controller |
|-------|------|-----------|-----------|-----------|
| raw/r0/rep1.ccr | 37,260 | 0.181s | 207K | Reno |
| raw/smoketest/t1.ccr | 160,518 | 0.729s | 221K | Reno |
| raw/cubic_replay/primary/rep1.ccr | 78,688 | 1.442s | 55K | CUBIC |
| raw/covegas_replay/primary/rep1.ccr | 63,329 | 1.559s | 40.9K | CoVegas |

Throughput differs by trace/controller: Reno maintains ~207-221K e/s; CUBIC drops to 55K e/s; CoVegas
to 40.9K e/s. As with parse, each ABI was tested on only one trace, so "controller complexity" and
"trace identity" are confounded here -- this data cannot attribute the slowdown to the controller
alone.

### Diff Performance

| Trace | Controller | Mean Time | Events/sec |
|-------|-----------|-----------|-----------|
| Reno (r0) | Reno | 0.179s | 213K |
| Reno (smoketest) | Reno | 0.678s | 241K |
| CUBIC | CUBIC | 1.251s | 63K |
| CoVegas | CoVegas | 1.530s | 42K |

**Diff is faster than Mode-B replay in all four rows** (0.179 < 0.181, 0.678 < 0.729, 1.251 < 1.442,
1.530 < 1.559), the opposite of "slight overhead" as originally written here. The two operations do
similar work (one stateful controller pass), so the gap is more likely run-to-run noise than a real
per-operation cost difference; it is not large enough either way to support a causal claim.

### All-Decisions (Mode A) Performance

| Trace | Controller | Mean Time | Events/sec |
|-------|-----------|-----------|-----------|
| Reno (r0) | Reno | 0.194s | 198K |
| Reno (smoketest) | Reno | 0.721s | 223K |
| CUBIC | CUBIC | 1.558s | 50.7K |
| CoVegas | CoVegas | 1.811s | 35.2K |

**CORRECTED (on review):** this was originally framed as "Mode A is slower than Mode B for complex
controllers, contrary to expectation," attributed to "fresh initialization per event." That comparison
is invalid: `all_decisions_core` replays **two** controller instances (reference + candidate) per
event plus comparison bookkeeping, against the single-controller Mode-B replay row above -- it is not
a same-work Mode A vs Mode B comparison, and running roughly 2x the controller logic per event fully
accounts for the gap without needing an "initialization overhead" story. No Mode A vs Mode B
same-controller-count comparison was actually run.

### Memory Usage

**CORRECTION (added on review, after the original measurement): the table and conclusion below, as
originally written, drew an unsupported causal claim from this data and have been corrected.**
`resource.getrusage(...).ru_maxrss` is a **per-process, monotonically non-decreasing high-water
mark** — it is the peak RSS of the entire Python process *since it started*, not an isolated
measurement of whatever code ran most recently. `run.py` processes all 4 traces **sequentially in
one process**, in this fixed order: Reno (r0/rep1) → Reno (smoketest/t1) → CUBIC → CoVegas. Because
`ru_maxrss` cannot decrease, each later trace's reported figure is contaminated by every parse/
replay/diff/all-decisions call that ran *before* it in the same process -- it cannot be attributed
to that trace or controller alone. This is visible directly in the raw data (`summary.csv`): both
Reno traces report the identical value (365,228 KB) because nothing freed memory between them, and
each subsequent controller's number is >= the previous one's, consistent with simple accumulation,
not with "CoVegas's controller state is bigger than CUBIC's."

| Trace | Controller | Process peak RSS *at that point in a shared sequential run* |
|-------|-----------|----------|
| raw/r0/rep1.ccr | Reno | 365 MB |
| raw/smoketest/t1.ccr | Reno | 365 MB |
| raw/cubic_replay/primary/rep1.ccr | CUBIC | 467 MB |
| raw/covegas_replay/primary/rep1.ccr | CoVegas | 658 MB |

**No claim about relative per-controller memory footprint can be drawn from this table.** A correct
measurement would run each (trace, controller) case in its own fresh subprocess and read that
subprocess's own peak RSS -- not yet done. This is flagged here rather than silently corrected, per
project policy of never hiding a measurement-design problem once found.

## Trend Analysis

### Linearity Assessment

For a pure O(n) operation, events_per_sec should remain constant across trace sizes.

**Parse**: r0 (37K events, 534K e/s) vs smoketest (160K events, 453K e/s) -- events/sec differs by
about 15% ((534-453)/534), not the "5%" originally stated here. This is consistent with roughly linear
scaling but is weaker evidence for it than first claimed; a 2-trace, 1-ABI comparison cannot rule out
other causes of that 15% gap (cache effects, measurement noise).

**Replay (Reno only, the one controller tested at two trace sizes)**: 207K vs 221K e/s is about 6.5%
variance ((221-207)/221), not "3%". Still roughly flat across a 4x trace-size difference, consistent
with linear scaling, but the number itself was mis-stated.

CUBIC/CoVegas were each measured on only one trace size, so no linearity claim can be made for them
from this data.

### Performance Bottlenecks

1. Parse/replay/diff throughput differs substantially between the tested traces; whether that is
   controller complexity, ABI field count, or trace content is not separable from this data (see
   confound note above).
2. Parse is roughly 2-4x faster than Mode-B replay/diff on the traces tested.

## Conclusion

**CORRECTED (on review):** the bullets and closing line below originally over-claimed. What this
measurement actually supports:

- **Parse**: 140-534K events/sec. Reno's own two trace sizes show ~15% events/sec variance (not the
  "5%" first claimed), weak-to-moderate evidence of roughly linear scaling; CUBIC/CoVegas were each
  tested at one size only, so no scaling claim can be made for them here.
- **Replay Mode B**: 40-221K events/sec. Reno's two sizes show ~6.5% variance (not "3%"), consistent
  with linear scaling for Reno specifically.
- **Diff**: 42-241K events/sec -- faster than Mode-B replay in all four rows tested here, not slower.
- **All-Decisions Mode A**: 35-223K events/sec. Not comparable to the Mode-B replay row above (see
  confound note): all-decisions runs two controller instances per event, Mode-B replay runs one.
- **Memory**: 365-658 MB peak RSS observed. As the correction above states, this is a single shared
  process's non-decreasing high-water mark across all 4 traces run sequentially -- it supports no
  claim about relative per-controller or per-trace memory footprint, and is **not** "trace-size
  independent, algorithm-dependent" as this line originally (incorrectly) concluded.

Reno's own two sizes are consistent with roughly linear scaling in parse and Mode-B replay. Nothing
else in this report supports a general "O(n) across all operations" or a controller-complexity
attribution; both would require testing each ABI at multiple trace sizes and each (trace, controller)
pair in its own fresh process, neither of which this run did.
