# Evaluation Plan

The artifact must dominate the evaluation. CCReplay is not a large congestion-control benchmark.

## 1. Replay fidelity

For every supported implementation report:

- trace version;
- callback manifest;
- exact fields compared;
- Mode A match rate;
- Mode B first divergence;
- first mismatch if any.

The principal correctness result is exact semantic replay fidelity.

## 2. Recorder integrity

Measure:

- callback invocations;
- successful emissions;
- authoritative drop count;
- sequence gaps;
- events/s;
- bytes/event;
- trace MB/s.

A fidelity result is invalid if replay-critical recording loss occurred.

## 3. Recorder non-interference

The recorder runs on the live path, so its effect must be bounded.

### Design

Use a highly reproducible solo baseline.

Compare:

- the same reference wrapper logic with recording disabled;
- the same reference wrapper logic with recording enabled.

This isolates instrumentation from implementation differences.

### Replications

Use at least 8 runs per arm unless a later precommitted power argument justifies another design. Interleave/randomize arms to distribute slow drift.

### Statistical framing

Use equivalence testing, not “p > 0.05”.

### Equivalence margins

Freeze margins before observing recorder-vs-control results.

Candidate margins such as throughput ±1% and mean RTT ±2 ms must be justified as practically negligible effects for the intended debugging use case and compared with measured baseline variability.

Do not justify RTT margins with 1 Hz sampling language.

### Direct overhead

Where available report total BPF runtime, callback count, ns/callback, CPU cost, and trace serialization cost.

## 4. Replay performance

Report:

- replay events/s;
- wall-clock replay time for a standard trace;
- memory usage;
- checkpoint serialization cost.

## 5. Replay ABI ablation

After a full sufficient contract passes:

- mask one field class at a time;
- rerun self-replay;
- report the first failing event.

Deliverable: per-algorithm load-bearing field table.

Do not call this universal minimality.

## 6. Controlled regression case study

Seed known defects and evaluate whether first divergence occurs at the expected semantic transition and names the expected result/state class.

Reference-vs-reference must report no divergence.

## 7. Historical regression case study

Use a genuine buggy/fixed pair and deliver:

- first divergence;
- callback/result/state difference;
- event context;
- relation to later historical failure;
- comparison with prior manual debugging workflow.

## 8. Optional replay scaling

Offline replay of multiple candidates may be measured if useful, but this is secondary.
