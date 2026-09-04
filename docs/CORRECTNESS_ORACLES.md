# Correctness Oracles

CCReplay must not validate itself only against another copy of the same logic.

## Oracle A — Event-local exact semantic self-replay

For every recorded event, use recorded shared PRE state, recorded private PRE state, callback inputs, observations, and time to reproduce the declared controller transition.

### Criterion

100% exact equality on every field declared exact by the callback/controller comparison schema.

### Validates

- individual transition logic;
- Replay ABI sufficiency for one event;
- callback-result recording;
- state parsing;
- semantic comparison.

### Does not validate

Private-state propagation across events.

## Oracle B — Stateful-controller exact semantic self-replay

Initialize controller-private state once, inject recorded shared TCP boundary state at each event, and evolve private replay state naturally.

### Criterion

First divergence = NONE on every valid trace.

### Validates

- private-state initialization/propagation;
- callback ordering;
- controller-visible time handling;
- stateful Replay ABI sufficiency.

### Does not require

Reproduction of TCP-core updates outside the CC callback.

## Oracle C — Independent live/reference implementation

Where possible, recorded live results should come from Linux reference logic that the userspace replay model did not author.

For Reno, use target-kernel callable reference functions if available and permitted from the chosen BPF context.

If unavailable, document the weaker fallback.

## CUBIC oracle

CUBIC is the genericity gate because it introduces private history and time dependence.

A previously validated BPF CUBIC may serve as live reference, but this is weaker than an independent Linux reference and must be stated.

## Exact semantic equality

Do not use “bit-exact” as shorthand.

Correct phrase:

> **exact semantic equality on every declared callback result and semantic state field.**

## Raw private bytes

Raw `icsk_ca_priv` may be archived but raw byte equality is not the gate because padding/unused bytes may be irrelevant.

## Relaxations

A non-literal equivalence rule is allowed only if documented before accepting the result, cannot hide logic differences, and is named explicitly in the report.

Weakening the oracle after seeing a mismatch solely to obtain PASS is prohibited.

## Required gate reporting

Every R1/R2/R3 report lists:

- callbacks covered;
- fields compared per callback;
- private-state schema;
- trace version;
- first mismatch if any;
- independence of the live reference from the replay implementation.
