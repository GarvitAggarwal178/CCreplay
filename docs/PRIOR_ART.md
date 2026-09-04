# Prior Art and Positioning

## Language rule

Write:

> “We did not find X under the searches and systems examined.”

Never write:

> “Nobody has done X.”

Update this document whenever the project claim broadens.

## Comparison dimensions

For each close system ask:

1. What execution boundary does it record/control?
2. Does it replay whole TCP behavior or only a controller implementation?
3. Does it replay two controller implementations against one fixed recorded contract?
4. Does it localize the first semantic controller divergence?
5. Does it define a callback/state Replay Contract?
6. Does it validate that contract through exact semantic self-replay?

## DETER — strongest prior-art risk

### Overlap

DETER occupies deterministic TCP record/replay for diagnosis. CCReplay cannot claim invention of TCP record/replay or deterministic TCP debugging.

### Intended distinction

CCReplay targets the congestion-control implementation at the callback boundary and uses deterministic differential replay to localize controller-state/result divergence, rather than replaying a whole TCP execution primarily to reproduce a performance problem.

### Required action

Before any research-novelty claim, read DETER in full and record exactly what it captures, replays, compares, and localizes.

Research novelty remains **YELLOW** until then.

## CCP / Portus

### Overlap

Userspace congestion-control execution behind a datapath interface is not our invention.

### Intended distinction

CCReplay is passive/offline after recording. It does not actuate the live connection. Its core operation is repeatable implementation replay and regression localization.

## CC-Fuzz

### Overlap

Both concern CC correctness/debugging.

### Intended distinction

CC-Fuzz searches workloads/conditions that trigger failures. CCReplay starts from a concrete recorded execution and localizes implementation divergence.

## General record/replay debuggers

Deterministic replay, reverse debugging, checkpoints, and differential replay are established software-debugging ideas.

The networking-specific contribution must therefore be the mapping to:

- Linux CC callback boundary;
- versioned Replay ABI;
- exact semantic self-replay;
- CC state/result first-divergence localization.

## Delta debugging

Generic delta debugging is established prior art and arbitrary TCP-event deletion is not a base CCReplay claim.

Checkpoint + suffix is a reproducer mechanism, not a minimization novelty claim.

## Network differential testing

Search explicitly for transport/network-stack differential replay and congestion-control regression testing. Any system already doing CC callback-level differential replay would be major overlap.

## Verdicts

### Semester-project originality

**GREEN, provisionally.**

The artifact requires substantial new engineering and has a clear professor-visible contribution even if research novelty is moderate.

### Research novelty

**YELLOW.**

Potentially distinct center:

> callback-level deterministic differential replay specifically for congestion-control implementations, with per-algorithm Replay Contract validation and first-divergence localization.

That requires focused prior-art review before paper-level claims.

## Search log

Append date, query, sources found, overlap, and whether positioning changed. Preserve inconvenient results.
