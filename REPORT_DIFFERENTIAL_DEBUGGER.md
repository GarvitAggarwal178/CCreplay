# Differential Debugger Core (N4)

**Naming note:** this is `docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md`'s `REPORT_DIFFERENTIAL_DEBUGGER.md`
(no rename needed — already a public-facing name).

## Status: COMPLETE — hard negative sanity oracle PASS

## Question

Can two controller implementations, replayed against the same recorded Replay Contract, be
compared to identify the first callback at which their declared results or state transitions
differ (CLAUDE.md allowed claim #5)?

## What was built

`user/ccreplay_diff.py` — the smallest useful implementation of the pipeline's conceptual
`ccreplay diff TRACE --reference REF --candidate CANDIDATE` command. `REF`/`CANDIDATE` are Python
model modules exposing the same interface already established by `user/reno_model.py` (v0) and
`user/cubic_model.py` (v1): a `transition(event, private_state)` function and a `COMPARISON_FIELDS`
schema. Both modules are replayed statefully (shared TCP state injected from the recording at every
event; each module's own private state carried forward independently — the same Mode-B shape as
`replay_r2.py`/`replay_r3b.py`, generalized to two independently-evolving implementations instead of
one model vs. the recording) against the same trace. Trace version (v0/v1) is detected from the
header, not assumed from either module's identity, so the same tool works for both Reno and CUBIC
traces without a separate code path per controller.

Required output fields (all present in every divergence report): matched-event count before
divergence; first divergent event (seq + index); callback; callback result diff; controller-owned
state diff; private-state diff; shared PRE; inputs/time; ±5 event context.

## Hard negative sanity oracle

| trace | reference | candidate | events checked | result |
| --- | --- | --- | ---: | --- |
| `raw/r0/rep1.ccr` (Reno, v0) | `user.reno_model` | `user.reno_model` | 37,260 | **NO DIVERGENCE** |
| `raw/cubic_replay/primary/rep1.ccr` (CUBIC, v1) | `user.cubic_model` | `user.cubic_model` | 78,688 | **NO DIVERGENCE** |

Both required cases (Reno trace, CUBIC trace) pass. This validates the diff engine's own mechanics
(field comparison, private-state threading, no aliasing/nondeterminism bugs) independent of
model-vs-recording fidelity, which is R1/R2/R3A/R3B's separate concern — a module compared against
itself is deterministic and trivially agrees with itself regardless of whether it also agrees with
the recorded trace (in particular, the CUBIC hard-negative run includes the same 46
`CLOCK_AMBIGUOUS` events that produce `REPORT_CUBIC_REPLAY_VALIDATION.md`'s residual: both
`reference` and `candidate` read the identical recorded `clock_jiffies32_before` value and so agree
with each other even where that value's fidelity to the real kernel's internal read is itself
ambiguous).

Per the pipeline's explicit rule: "If either produces divergence: N4 FAIL/INCOMPLETE. Do not
proceed to N5." Neither produced divergence — **N4 gate PASS, proceeding to N5 is authorized.**

## Design notes / limitations

* The tool compares two *implementations*, not an implementation against the recording — this is
  deliberately the N5 use case (a known-good reference vs. a candidate with a suspected/seeded
  defect), not a restatement of R1/R2/R3A/R3B.
* Not yet exercised on a genuine divergence (a candidate module that actually differs from its
  reference) — that is N5's explicit purpose (seeded bugs with precommitted predictions). The hard
  negative oracle only proves the tool does not report a *false* divergence; N5 is required to prove
  it correctly reports a *true* one.
* `meta.json` is accepted as a CLI argument for symmetry with the other replay tools but is not
  currently used by the diff itself (no sidecar-derived value is needed for a pure model-vs-model
  comparison).

## Reproduction

```
python3 user/ccreplay_diff.py raw/r0/rep1.ccr raw/r0/rep1.meta.json --reference user.reno_model --candidate user.reno_model
python3 user/ccreplay_diff.py raw/cubic_replay/primary/rep1.ccr raw/cubic_replay/primary/rep1.meta.json --reference user.cubic_model --candidate user.cubic_model
```

## Relevant commit

This report's own commit (adds `user/ccreplay_diff.py`, `cubic_model.py`'s `INITIAL_PRIVATE_STATE`
export, and this file).

Mandatory Phase-1 regression: 40/40 tests pass, reverified immediately before this report's commit.
