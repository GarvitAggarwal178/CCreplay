# Differential Debugger

## Goal

Turn a recorded congestion-control execution into a software-debugging result.

Target output:

> “Reference and candidate agree through event N-1. At event N, callback C, callback result/state field F differs.”

## FIRST_DIVERGENCE

Given a trace and two implementations:

```text
events 1 .. D-1   MATCH
event D            DIVERGE
```

Report:

- trace ID;
- event sequence number;
- callback;
- event time;
- shared boundary state;
- callback inputs;
- observations;
- reference result/state;
- candidate result/state;
- exact differing semantic fields;
- nearby event context.

## Callback-result diff

Return values are first-class.

Example:

```text
callback: ssthresh
reference return: 43
candidate return: 31
```

Do not infer these decisions indirectly from later TCP state.

## State-field diff

For controller-owned/private state:

```text
field             reference   candidate
snd_cwnd_cnt      0           1
epoch_start       ...         ...
mode              DELAY       COMPETE
```

Only declared semantic fields participate in correctness.

## Event context

Print configurable surrounding events for debugging. Context does not redefine first divergence.

## Divergence episode / reconvergence

Optional secondary diagnostics after first divergence.

## Invariant predicates

Optional later feature: user assertions over replay state, reported at the exact violating event.

Do not make this an R0/R1/R2 dependency.

## Checkpoint + suffix reproducer

For stateful replay:

```text
checkpoint @ K + events K+1..D
```

This is a valid compact reproducer because checkpoint state supplies the controller-private context for the suffix.

## Excluded base feature

Arbitrary deletion of recorded TCP control events.

Dependent event deletion can create an infeasible controller history. Generic delta-debugging is not the base project.

Dependency-aware reduction is optional stretch work only.
