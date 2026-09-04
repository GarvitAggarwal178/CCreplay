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

## v0 concrete instantiation — Reno

Determined empirically in `data/capability_audit.md` (sections A–F) before any recorder code was
written, by capturing a wide PRE/POST field superset against real kernel `tcp_reno_*` calls under
the validated Gate-3-R2 topology, diffing which fields actually mutated, and validating a
from-scratch userspace replay model against the captured trace (100.0000% exact match, 24,651
real `cong_avoid` events).

**Callback manifest:** `{ssthresh, cong_avoid, undo_cwnd}` — exactly the callbacks native
`tcp_reno_ops` implements upstream. No `.init` — Reno has no controller-private state to set up
(see Private state, below).

**TraceHeader** additions beyond the recommended fields: `callback_manifest` as a 3-bit mask
(`ssthresh|cong_avoid|undo_cwnd`); `reference_implementation_id = "linux_tcp_reno_kfunc"` (kernel
`tcp_reno_cong_avoid`/`tcp_reno_ssthresh`/`tcp_reno_undo_cwnd`, called directly as BPF kfuncs —
Oracle C, independent of the replay implementation); `private_state_schema_id = NONE`.

**EventRecord — one record per callback invocation, PRE+inputs+result+POST in a single
`bpf_ringbuf_reserve`** (feasible on this kernel/verifier — proven directly by
`data/audit_src/audit_fields.bpf.c`, which used exactly this shape for 60s/24,656 events with zero
verifier issues; §8's split-record fallback is not needed):

- `seq` (u64) — global logical sequence, allocated at callback entry via an atomic increment on a
  single-entry counter map, before reservation is attempted (ADR-009).
- `sock_cookie` (u64) — every record carries an originating-socket identity discriminator.
  `bpf_get_socket_cookie()` was attempted first and is **not usable from this program type on this
  kernel** (verifier: "program of this type cannot use helper bpf_get_socket_cookie" — confirmed
  by a direct load attempt against the real recorder object, not assumed from the capability
  audit's generic helper-presence check). The raw `sk` pointer value is used instead, cast to u64;
  it is a within-trace discriminator only, not a stable cross-boot identifier, and is never
  compared across separate recording sessions. R0's controlled single-transfer experiments are
  expected to produce events from exactly one socket per trace; the parser reports the
  distinct-`sock_cookie` count and treats more than one as a condition requiring explicit
  investigation before a trace is accepted, rather than silently pooling multiple connections'
  events under one global sequence. (Motivated by an unexplained multi-event artifact observed in
  an unrelated `SK_STORAGE` audit smoke test — see `data/capability_audit.md` section B — that was
  never conclusively attributed to a single cause.)
- `ts_ns` — diagnostic monotonic timestamp (`bpf_ktime_get_ns()`). Reno itself has no
  controller-visible clock dependency (section D); this field is diagnostic/ordering-support only,
  per `REPLAY_ABI.md`'s distinction above.
- `callback_id` — `1=ssthresh, 2=cong_avoid, 3=undo_cwnd`.
- **CallbackInputs:** `ack`, `acked` (meaningful for `cong_avoid` only; `0` otherwise).
- **SharedTcpPreState / Observations (CORE unless noted):** `snd_cwnd`, `snd_ssthresh`,
  `snd_cwnd_cnt`, `snd_cwnd_clamp`, `prior_cwnd` (needed only by `undo_cwnd`), `max_packets_out`
  and `is_cwnd_limited` (OBSERVATION class — **required, not optional**: empirically shown to gate
  whether `cong_avoid` mutates anything at all; see capability audit section F for the two
  otherwise-identical real events this was discovered from).
- **CallbackResult:** `result_valid` (1 for `ssthresh`/`undo_cwnd`, 0 for `cong_avoid`), `result`
  (the returned scalar).
- **ControllerOwnedPostState:** `snd_cwnd`, `snd_cwnd_cnt` (both empirically confirmed as the
  complete mutated-field set for `cong_avoid`; `ssthresh` and `undo_cwnd` are pure — POST equals
  PRE for every field, confirmed on 5/5 and 8/8 real events respectively).

**Private state:** NONE. Reno maintains no controller-private state under this Replay Contract —
every field it reads or writes is already classified as shared TCP boundary state above. Stated
explicitly per this document's "do not invent private state" guidance, not left implicit.

**RecorderRunMetadata (sidecar, read at teardown before unregistering the struct_ops, per
ADR-009/`RECORDER.md`):** `invocations`, `emitted`, `drops` (three independent atomic counters;
integrity requires `invocations == emitted + drops`, not merely a gapless `seq`, since a gapless
sequence cannot detect loss truncated off the tail of a run — see `docs/DECISIONS.md` ADR-013),
`first_seq`, `last_seq`, `distinct_socket_cookies`, `teardown_status`, per-program
`run_time_ns`/`run_cnt` (`kernel.bpf_stats_enabled=1` required, enabled consistently across all R0
runs).

## Replay ABI ablation

Only after a full sufficient contract passes:

- mask one field class at replay time;
- rerun self-replay;
- report first failure.

This identifies load-bearing fields for that implementation; it is not a universal-minimality claim.
