# 11-Week Roadmap

## Week 1 — Recorder viability

- repo scaffold/provenance;
- BTF capability audit;
- Reno reference strategy;
- `SK_STORAGE` test or fallback;
- Replay ABI v0;
- callback manifest;
- explicit callback-result capture;
- logical sequence IDs;
- authoritative drop counter;
- writer/parser;
- R0.

**End-of-week requirement:** know whether lossless callback-boundary recording is viable.

## Week 2 — Reno replay correctness

- userspace Reno model;
- Mode A;
- Mode B;
- exact semantic comparison schema;
- mismatch diagnostics;
- repeatability tests;
- R1/R2.

**Hard kill:** if Reno stateful exact semantic self-replay cannot be achieved without weakening semantics, stop.

## Week 3 — CUBIC genericity

- private-state schema;
- controller-visible time;
- additional callbacks;
- Mode A/Mode B CUBIC;
- R3.

**Hard deadline:** end of week 3. Narrow claims immediately if necessary.

## Week 4 — Differential debugger

- reference/candidate replay;
- first divergence;
- result/state diff;
- event context;
- CLI.

## Week 5 — Checkpoints/reproducers

- private-state serialization;
- restore;
- checkpoint + suffix reproducer.

## Week 6 — Evaluation

- Replay ABI ablation;
- recorder non-interference equivalence study;
- direct BPF runtime;
- trace rate/volume;
- replay speed.

## Week 7 — Controlled regressions

Seed known defects and validate localization.

## Weeks 8–9 — Historical regression

Select a real buggy/fixed pair, record a valid trace, localize first divergence, compare with prior manual debugging.

## Week 10 — Tool polish

CLI, demo workflow, figures, diagnostics, docs cleanup.

## Week 11 — Final report/demo

Professor demo and paper-style writeup only if results support it.

## Optional stretch

Dependency-aware replay reduction only after the base project is complete. No arbitrary event deletion.

## Freeze rule

After R0 begins, architecture changes require a documented gate failure or ADR.
