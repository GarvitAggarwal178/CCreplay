# Replay Contract / Replay ABI

## Status

Initial design version: **v0**.

Any semantic field addition, removal, or reinterpretation requires a `trace_version` bump, documentation update, and re-recording of traces used by correctness gates.

## Purpose

Faithful CC replay may depend on callback identity/order, callback arguments, shared TCP boundary state, controller-visible clocks, delivery observations, recovery-facing state, and algorithm-private history.

The Replay Contract makes that boundary explicit.

## Trace structure

```text
TraceHeader
ConnectionMetadata
CallbackCapabilityManifest
EventRecord[]
RecorderRunMetadata
```

## TraceHeader

Recommended semantic fields:

- magic;
- trace version;
- recorder version;
- kernel release/build ID where available;
- reference implementation ID;
- private-state schema ID;
- callback manifest ID/hash;
- clock metadata;
- relevant connection constants;
- trace creation metadata;
- layout hash where raw implementation-specific bytes are archived.

## CallbackCapabilityManifest

Lists callbacks implemented/instrumented by the active wrapper/reference implementation.

A trace only promises complete coverage for this declared surface.

## EventRecord

Conceptually:

```text
seq
callback_id
timestamp_ns
controller_timebase

CallbackInputs
SharedTcpPreState
Observations
PrivateStatePre

CallbackResult

ControllerOwnedPostState
PrivateStatePost
```

## Logical sequence number

`seq` identifies the callback invocation, not merely a successfully emitted ring-buffer record.

It must be allocated at callback entry before recording success is known.

A failed event reservation consumes the sequence number and increments the authoritative BPF drop counter.

## CallbackResult

Callback result is first-class trace data.

### `ssthresh`

Record the returned scalar value explicitly.

Do not infer it from immediate POST shared state.

### `undo_cwnd`

Record the returned scalar value explicitly.

### `cong_avoid`

Void callback. Its semantic result is represented through declared controller-owned mutations, such as `snd_cwnd` and `snd_cwnd_cnt`.

### Future callbacks

Every callback schema must state whether its semantic output is:

- scalar return;
- structured return;
- void + mutations;
- observation-only.

## SharedTcpPreState

Candidate fields should be classified as:

- CORE;
- ALGORITHM-SPECIFIC;
- OPTIONAL/DIAGNOSTIC.

A field belongs in the replay contract if the implementation reads it, the oracle requires it, or it is necessary to diagnose fidelity.

Possible fields include:

- `snd_cwnd`;
- `snd_ssthresh`;
- `snd_cwnd_cnt`;
- `snd_cwnd_clamp`;
- congestion-control state;
- packets-out / in-flight state;
- cwnd-limited indication.

Do not record every kernel field merely because it exists.

## Observations

Candidate observation classes include:

- callback RTT sample;
- SRTT / min RTT when read by the controller;
- delivery-rate state when read;
- loss/recovery-facing values;
- controller-visible timebase.

## Controller-visible time

Record the time representation actually used by the controller whenever possible.

A high-resolution monotonic timestamp may also be recorded for diagnostics, but it is not automatically equivalent to the controller's own clock.

## Private state

Correctness uses a semantic `PrivateStateSchema`.

Examples for CUBIC may include parsed epoch/history fields.

Raw `icsk_ca_priv` bytes may additionally be archived. Raw byte equality is not the default oracle because padding or unused bytes can be semantically irrelevant.

## ControllerOwnedPostState

Contains declared controller-owned mutations for the callback.

The exact schema is callback/controller specific.

## RecorderRunMetadata

Must be obtained through a reliable side channel at teardown rather than solely via the ring buffer being validated.

Recommended fields:

- total callback invocations if available;
- successful emissions;
- authoritative drop count;
- first/last logical sequence;
- teardown status;
- recorder configuration.

## Integrity requirements

A trace used by correctness gates requires:

- zero authoritative replay-critical drops;
- no unexplained sequence gaps;
- known trace version;
- matching callback manifest;
- valid parse;
- valid metadata readback.

## Per-algorithm sufficiency

The project does not claim one universal minimal Replay ABI.

For each supported implementation, determine which field classes are sufficient for exact semantic self-replay.

## Replay ABI ablation

Only after a full sufficient contract passes:

- mask one field class at replay time;
- rerun self-replay;
- report first failure.

This identifies load-bearing fields for that implementation; it is not a universal-minimality claim.
