# Recorder

## Purpose

Capture the live congestion-control callback boundary faithfully enough to support exact semantic replay.

The recorder must preserve:

- callback ordering;
- callback identity;
- shared boundary state;
- callback inputs;
- controller-visible observations/time;
- explicit callback result;
- semantic controller-private state where required;
- replay-critical loss information.

## Initial wrapper strategy

A BPF `struct_ops` CC is itself the active congestion-control implementation for the socket.

The initial recorder therefore wraps the reference controller:

```text
wrapper callback
    |
    +--> allocate logical event seq
    +--> capture shared/private PRE
    +--> capture callback inputs
    +--> execute reference CC logic
    +--> capture explicit callback result
    +--> capture semantic POST/private state
    +--> emit EventRecord
```

Do not assume an independent `struct_ops` observer can sit beside native CUBIC.

## Reference logic

Preferred order:

1. Linux callable/kfunc-backed reference logic where supported on the exact kernel;
2. previously validated BPF controller implementation copied with provenance;
3. hand-written wrapper logic only where necessary, with the weaker oracle documented.

## Sequence allocation

Allocate the logical invocation sequence number at callback entry.

If recording fails, the controller still executes correctly and the sequence number is still consumed.

This makes loss detectable rather than invisible.

## Drop detection

Required:

1. authoritative BPF-side drop counter, incremented on replay-critical emission failure;
2. userspace sequence validation;
3. optional invocation/emission accounting where feasible.

At teardown, read the drop counter directly from the map or another independent channel.

Do not rely only on a ring-buffer trailer to validate ring-buffer integrity.

## One-record-per-callback preference

Prefer one EventRecord containing PRE + inputs + result + POST.

If verifier or size constraints force split records, revise the Replay ABI with an explicit pairing protocol.

## Callback manifest

The wrapper declares its implemented/instrumented callback surface.

R0 validates every invocation of that declared surface, not every possible TCP CC callback.

## Per-socket recorder state

`BPF_MAP_TYPE_SK_STORAGE` is preferred if usable from the selected struct_ops context on the target kernel.

Benefits:

- socket-local lifetime;
- automatic cleanup;
- no cookie reuse handling;
- no manual GC.

If unavailable, use a documented fallback; do not redesign the project solely around this helper.

## Ring buffer sizing

Do not freeze theoretical event-rate numbers into the specification.

R0 measures:

- events/s;
- bytes/event;
- trace MB/s;
- reservation failures.

Choose buffer size with measured margin.

## Overhead

Measure where supported:

- accumulated BPF runtime;
- invocation count;
- ns/callback;
- trace serialization cost;
- trace volume.

Behavioral non-interference is evaluated later under `EVALUATION.md`.

## Priority rule

Correctness is more important than diagnostic richness.

If the event record is too large:

1. remove OPTIONAL/DIAGNOSTIC fields first;
2. preserve replay-critical state/results;
3. bump schema version if semantics change.

Never accept replay-critical event loss merely to retain diagnostics.
