# Implementation Handoff to Claude Code

This document defines implementation scope after the documentation freeze. It contains no implementation code.

## Initial scope

Implement only:

- repository scaffold and provenance;
- capability audit;
- Replay ABI v0;
- Reno wrapper recorder;
- trace writer/parser;
- R0;
- Reno event-local replay;
- Reno stateful-controller replay;
- first-mismatch diagnostics;
- R1/R2.

Do not implement CUBIC, Vegas, CoVegas case studies, dashboards, generic minimization, or broad evaluation until R1/R2 pass.

## Core semantic boundary

```text
recorded shared TCP boundary state
+
callback inputs
+
controller-visible observations/time
+
controller-private state
        |
        v
CC implementation
        |
        v
callback result
+
controller-owned mutations
+
next private state
```

Do not reproduce Linux TCP-core evolution between callbacks.

## R0 priorities

1. inspect target-kernel BTF;
2. determine Reno reference strategy;
3. test `SK_STORAGE` or fallback;
4. create callback capability manifest;
5. allocate logical `seq` at callback entry;
6. capture explicit callback result;
7. prefer one record per callback;
8. maintain authoritative BPF-side drop counter;
9. read drop metadata directly at teardown;
10. preserve all failed runs.

## R1 priorities

Event-local replay compares callback result, controller-owned semantic mutations, and semantic private POST state where applicable.

Raw private-byte mismatches alone are not gate failures.

## R2 priorities

Stateful controller replay initializes private state once, injects recorded shared boundary state at every event, executes the callback, compares semantic output/state, and carries only controller-private replay state forward.

Do not derive the next event's shared TCP state solely from replay output.

## Hard stops

Stop and report if:

- replay-critical loss can occur silently;
- callback ordering cannot be represented;
- callback results cannot be captured;
- R1 cannot achieve exact semantic equality after legitimate contract corrections;
- R2 remains unexplained by the week-2 deadline;
- PASS would require changing the semantic meaning of replay.

## Required R0/R1/R2 report

Report:

- kernel capability audit;
- actual callback manifest;
- implemented Replay ABI version;
- exact semantic comparison schema;
- event/drop/trace-volume numbers;
- R0/R1/R2 PASS/FAIL;
- first mismatch if any;
- ABI changes made during discovery;
- readiness for R3.

## Claim discipline

Reno success does not justify claims about CUBIC, Vegas, BBR, arbitrary kernel CCAs, alternate performance, or full TCP replay.
