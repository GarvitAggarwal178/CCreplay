# Replay contract and technical reference

[Project home](../README.md)

## An event has four semantic parts

| Part | Meaning | Examples |
|---|---|---|
| Shared TCP input state | State supplied by Linux at this callback boundary | cwnd, ssthresh, cwnd counter, cwnd-limited observations |
| Controller-private state | History owned by the congestion controller | CUBIC epoch/counters; CoVegas mode and estimators |
| Arguments and observations | Callback inputs and controller-visible time | ACK counts, RTT sample, jiffies bracket |
| Computed outputs | Explicit return and declared controller-owned/private POST | returned threshold, changed cwnd, next private state |

PRE means immediately before controller execution. POST means immediately after it. Semantic equality compares the declared meaningful fields. Raw padding and unused private bytes are not correctness criteria.

## Replay modes

**Mode A - event-local:** both implementations start each event with the same recorded shared PRE, recorded private PRE and callback inputs. No private replay state carries between events. This isolates local transition differences.

**Mode B - stateful:** shared TCP inputs still come from each recorded event, while reference and candidate carry their own private states forward. This can expose how an earlier private-state change affects later decisions. It does not feed a candidate's shared TCP output back into a simulated network.

An all-decisions result can identify whether the private PRE states already differ. Those differences may be cascades from an earlier transition. Do not label every later disagreement cascaded solely because an earlier event differed.

## Controller interface

A model provides a transition accepting an event and private state, returning computed fields and the next private state. It declares an initialization seed and callback comparison fields. CoVegas uses a mode-dependent field schema.

Conceptual interface:

    computed_fields, next_private_state = transition(event, private_state)

Time-dependent models must use controller-visible time supplied by the recording, not wall-clock reads. User modifications must preserve the selected contract. Validation checks interface compatibility and a finite sampled execution (complete output and next-private-state streams, compared across a fresh module and a reset reuse); it is not proof of algorithm correctness or of universal determinism.

## Supported Replay ABIs

| ABI | Family | Declared callbacks | Private/time requirements |
|---|---|---|---|
| v0 | Reno | ssthresh, cong_avoid, undo_cwnd | No algorithm-private state; no controller clock dependency |
| v1 | CUBIC | v0 callbacks plus init, set_state, cwnd_event, pkts_acked | 16 semantic private fields; jiffies bracket and cached TCP timestamp |
| v2 | CoVegas | init, ssthresh, cong_avoid, undo_cwnd, pkts_acked | 30 semantic fields across dedicated state and both union arms; two clock brackets |

The v2 private comparison depends on callback, PRE mode and POST mode. Only the semantically active union arm is compared at each phase. A mode disagreement is itself meaningful.

Current shared header size is 144 bytes. Header fields include magic, trace/recorder versions, kernel release, reference identity, callback manifest, private schema, record size and creation time. Authoritative binary layouts are the versioned `bpf/ccr_event*.h` headers and `HEADER_FMT`, `EVENT_FMT` and `EVENT_FIELDS` in `user/ccr_trace*.py`. Their source and tests take precedence over a hand-maintained offset table. A layout or semantic change requires an explicit version decision and compatibility tests. The earlier detailed field tables are preserved in the archive listed in [Provenance](PROVENANCE.md).

## What comparisons mean

**Self-replay:** compare a model with the recorded execution it is intended to reproduce. This validates fidelity under the selected reference/oracle.

**Differential replay:** compare two implementations on the same recorded inputs. Identical models can agree even when their comparison to the kernel recording is clock-limited. These are different claims.

**Native network comparison:** execute distinct live connections, such as native Reno and native CUBIC, and compare actual measurements. This is not same-trace replay.

Studio requires trace, reference and candidate to share a Replay ABI. Selecting Reno and CUBIC together on one trace is not supported.

## Event identity and ordering

Recorded sequence numbers identify callback invocations and can start at zero. They are global to the recording; the selected dominant connection can contain gaps caused by other sockets. Its zero-based row index is a separate identity. Never infer index as sequence minus one.

Replay sorts the selected dominant connection by recorded sequence. That selection is not a complete multiconnection TCP replay. Socket discriminators are within-recording identities, not persistent cross-boot IDs.

## Integrity and coverage

A valid structural parse alone does not prove a complete capture. Check supported header/layout, full records, callback manifest, sequence evidence, authoritative drop/invocation/emission counts and compatible metadata. A missing sidecar means some integrity checks are unknown. A header-only control is not a useful replay recording.

A callback absent from a recording is unexercised. Agreement on a trace cannot rule out defects on unexercised paths.

## Clock boundary

CUBIC reads a global jiffies clock. A tick can occur between the recorder's before/after observations. Equal endpoints are CLOCK_STABLE; differing endpoints are CLOCK_AMBIGUOUS. The documented replay convention cannot recover every actual internal read, so historical CUBIC self-replay remains PARTIAL. Do not select a time convention merely to make a trace pass.

Current CUBIC/CoVegas models use CONFIG_HZ=250. Rebuilding BPF code for another kernel is not, by itself, proof that the userspace model matches that kernel's source and clock assumptions.

## Checkpoint boundary (schema 2)

A checkpoint stores `next_event_index` K, `next_seq` and each controller's private state **immediately before** event K. Resuming executes events K through D inclusive: D-K+1 transitions, where D is the first-difference index. For K=1500 and D=1704 that is 205 transitions, including the failing one. A divergence exactly at K is reproduced by a one-transition suffix; a divergence at index 0 resumes from the initial state.

Reproduction is exact only when the resumed divergence equals the full run in position, differing fields, both computed outputs and both post-event private states (`same_divergence` in `user/ccreplay_checkpoint.py`). Matching the event index and field names alone is insufficient. Schema 1 checkpoints stored the same pre-event state but resumed at K+1, skipping event K; they are rejected rather than reinterpreted. A checkpoint reproducer neither minimizes nor deletes events from a failing history. Mode A carries no private state and needs no checkpoint.

## Replay sessions

A Replay session fixes a recording hash, two controller revisions (immutable source capsules with dependency hashes) and a mode, and stores the full computed stream: per event, each side's computed fields and private PRE/POST, plus disagreement and cascade labels. A rerun that finds a changed dependency is refused. Sessions are regenerable derived data under `runtime/replay/<id>/`.

## Bounded imported-controller interface

The two-file workbench supports only the v0 numeric callback output schema. Event-local mode supplies None on each callback and requires None next state. Initialized stateful mode requires `INITIAL_PRIVATE_STATE` (preferred) or `NONE_PRIVATE_STATE`; each side gets a fresh deep copy and receives its own returned private state on the next supplied event. State is finite JSON data with string object keys, at most 128 KiB and 64 nested levels. Inputs and states are copied before calling each source. Optional plain-text explanations do not affect numeric comparison. Private-state key differences are not correctness failures.

Shared TCP PRE is always supplied independently, including in stateful mode. Recorded stateful windows must start at selected-connection index zero; a later start is rejected with an initialization explanation because prefix warmup is not implemented. This does not read recorded private state as a new imported policy's history. Saved runs retain source texts, input-window snapshots, exact initialization JSON/hashes and per-event private PRE/POST; explicit reruns use the saved initialization. This interface does not accept arbitrary programs, stateful ABI-v1/v2 files, or compile custom kernel controllers. Those compatible built-in revisions continue to use the separate Replay debugger.
