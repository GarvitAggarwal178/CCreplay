# Architecture

## System overview

```text
                  LIVE TCP CONNECTION
                          |
                          v
              Linux TCP CC callback boundary
                          |
             +------------+------------+
             | BPF WRAPPER / RECORDER   |
             | 1. allocate event seq    |
             | 2. capture shared PRE    |
             | 3. capture private PRE   |
             | 4. capture callback args |
             | 5. execute reference CC  |
             | 6. capture result        |
             | 7. capture semantic POST |
             | 8. emit EventRecord      |
             +------------+------------+
                          |
                          v
                  userspace trace writer
                          |
                          v
                versioned .ccr trace
                          |
          +---------------+---------------+
          |                               |
          v                               v
 event-local replay             stateful controller replay
          |                               |
          +---------------+---------------+
                          |
                          v
                 differential engine
                          |
               first semantic divergence
```

## Architectural boundary

CCReplay records and replays the **congestion-control implementation boundary**. It does not emulate Linux TCP as a whole.

Linux TCP may change shared state between callbacks. Therefore every replay event injects the recorded shared TCP boundary state rather than asking userspace to synthesize TCP-core evolution.

Controller-private state is the state that naturally evolves across Mode B.

## Callback result is first-class

A callback return value is a controller decision.

For callbacks such as `ssthresh()` or `undo_cwnd()`, record the return explicitly. Do not infer it from immediate shared-state snapshots because Linux may apply it after callback return.

## Recorder strategy

The initial recorder is a wrapper congestion controller, not a passive second `struct_ops` observer.

Reference logic should come from Linux-exposed callable logic where available, otherwise from a validated BPF implementation with provenance.

Recording an unmodified native CCA is a possible later portability goal, not a week-1 requirement.

## Event integrity

Each callback invocation receives a monotonically increasing logical sequence number at callback entry.

```text
allocate seq
    |
attempt event reservation
    |
execute reference logic regardless
    |
if recording failed: increment authoritative drop counter
if recording succeeded: submit record
```

A failed ring-buffer reservation must not alter the live controller result.

At teardown, userspace reads the authoritative drop counter directly from a map or other independent channel.

## One-record design

Preferred design: one EventRecord contains PRE + inputs + result + POST.

If implementation constraints require split records, a later schema version must define explicit pairing.

## Callback capability manifest

Each trace declares the callbacks implemented/instrumented by the active wrapper/reference implementation.

R0 validates capture of every invocation declared by this manifest. It does not require Reno to implement unrelated callbacks.

## Mode A

Recorded shared PRE + recorded private PRE + callback inputs/observations/time -> computed callback result and semantic POST.

No replay state persists.

## Mode B

Controller-private replay state persists. Recorded shared TCP boundary state is injected at each callback.

The replay engine does not simulate TCP-core updates between callbacks.

## Differential engine

Reference and candidate run against the same event contract and mode.

Base output:

- first divergent event;
- callback;
- callback result diff;
- controller-owned state diff;
- semantic private-state diff;
- context.

## Checkpoints

Stateful replay checkpoints serialize controller-private replay state at periodic event boundaries.

A valid compact reproducer is:

```text
checkpoint @ K + events K+1..D
```

where D is first divergence.

## Invalidating failures

- nonzero replay-critical drop count;
- unexplained sequence gap;
- unknown trace version;
- capability-manifest mismatch;
- unexplained self-replay mismatch;
- silent oracle relaxation.
