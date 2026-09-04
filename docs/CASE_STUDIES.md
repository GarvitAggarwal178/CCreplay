# Case Studies

The case studies answer the professor-level question:

> **Why is CCReplay useful?**

The answer must be stronger than “different algorithms produce different cwnds.”

# Case Study A — Controlled injected regression

## Goal

Validate the debugger where the expected semantic effect is known before replay.

## Base controller

Reno or CUBIC, depending on fidelity gates.

## Candidate seeded defects

Examples:

### Wrong multiplicative decrease

Expected divergence region: first relevant `ssthresh` callback.

Expected semantic difference: callback return.

### Incorrect ACK accounting

Expected divergence region: first congestion-avoidance event where altered accounting changes a controller-owned state transition.

### Missing state reset

Expected divergence region: first event after the reset should have occurred.

## Procedure

For each seeded defect:

1. document the code change;
2. document the expected affected result/state class before replay;
3. run reference-vs-reference;
4. run reference-vs-buggy;
5. require the divergence to be explainable from the defect.

Do not tune expectations after seeing the result.

---

# Case Study B — Real historical regression

## Goal

Use a real previous buggy/fixed implementation pair.

## Comparison rule

Compare two implementations that isolate an actual code/mechanism change.

Do not compare unrelated policies and call ordinary policy disagreement a bug.

## Candidate historical material

Potential CoVegas candidates include:

- repeated/permanent competitive-mode capture;
- targeted-revert regression;
- controller-state refresh defect;
- another documented buggy/fixed pair.

## Freeze before running

Document only what is already known:

- historical failure;
- buggy/fixed code difference;
- affected controller state/mechanism;
- triggering region/event class where known.

Do not predeclare the exact first callback/event unless historical evidence already proves it.

## What CCReplay should discover

- first semantic divergence;
- callback;
- callback result or state field;
- nearby context.

## Interpreting the result

Allowed:

> “The buggy and fixed implementations first differ here, and this state difference belongs to the mechanism associated with the later stuck mode.”

Not automatically allowed:

> “This single event proves the entire performance regression.”

The link to later behavior must be argued.

## Debugging-value comparison

Compare the previous manual workflow — runs, sweeps, timeline inspection, reasoning — with the CCReplay workflow: record valid trace, run diff, inspect first divergence/context.
