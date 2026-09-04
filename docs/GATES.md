# Project Gates

The gates exist to discover fatal problems early.

## R0 — Recorder viability

**Latest:** end of week 1.

### Hypothesis

A wrapper congestion controller can record every invocation of every callback declared by its active capability manifest, in exact logical order, with detectable loss and usable callback/result state.

### Required checks

- target-kernel BTF capability audit;
- reference-controller invocation strategy;
- `SK_STORAGE` viability or documented fallback;
- one logical event ID per callback invocation;
- one-record PRE/input/result/POST format where feasible;
- authoritative BPF drop counter;
- sequence validation;
- trace parser;
- callback capability manifest;
- direct recorder overhead measurement.

### PASS

- zero replay-critical BPF-side drops;
- zero unexplained sequence gaps;
- trace parses successfully;
- every invocation of every callback declared by the active manifest is captured;
- callback result is present where the callback returns a value;
- recorder metadata is read successfully at teardown.

### FAIL

- replay-critical loss can occur silently;
- callback ordering cannot be represented;
- callback result cannot be captured faithfully;
- wrapper cannot execute the chosen reference controller correctly.

### Allowed engineering fixes

- enlarge ring buffer;
- remove OPTIONAL fields;
- change trace layout;
- use a documented per-socket-state fallback.

### Forbidden “fixes”

- ignore drops;
- weaken trace-integrity requirements.

---

## R1 — Reno event-local exact semantic self-replay

**Latest:** week 2.

### Hypothesis

For every recorded Reno callback, the Replay Contract contains enough information to reproduce the declared Reno transition exactly.

### Replay semantics

Use recorded shared PRE state, callback inputs, observations/time, and recorded private PRE state where applicable. Do not simulate TCP-core evolution.

### Required comparison examples

According to the actual Reno manifest:

- `ssthresh`: exact scalar return;
- `undo_cwnd`: exact scalar return;
- `cong_avoid`: exact declared controller-owned mutations such as `snd_cwnd` and `snd_cwnd_cnt`.

The final comparison list follows the actual implementation manifest.

### PASS

100% exact semantic equality on every declared exact field of every valid event across the R0 traces.

### FAIL

Any unexplained mismatch.

### Contract-discovery response

If the first mismatch exposes a genuinely missing Replay Contract input:

1. identify it;
2. update the ABI;
3. bump `trace_version`;
4. re-record;
5. retry.

That is contract discovery, not gate weakening.

---

## R2 — Reno stateful-controller exact semantic self-replay

**Latest:** week 2.

### Hypothesis

Reno controller-private state can be initialized once and propagated across the recorded callback stream without divergence while shared TCP boundary state is injected from the trace at every event.

### Replay semantics

For each event:

```text
recorded shared boundary state
+
recorded callback input
+
recorded observations/time
+
current replay-private state
        |
        v
Reno replay transition
```

Compare callback result, declared controller-owned mutation, and declared private state. The next event's shared TCP state again comes from the recording.

### PASS

First divergence = NONE on every R0 trace.

### FAIL

An unexplained semantic divergence remains after legitimate Replay Contract/model correction.

### Project kill condition

If the simplest supported controller cannot achieve stateful exact semantic self-replay by the end of week 2, stop rather than weakening the meaning of replay.

---

## R3 — CUBIC fidelity / genericity gate

**Latest:** end of week 3.

### Why R3 matters

Reno may be too simple. CUBIC forces the architecture to confront:

- multiple callback types;
- private historical state;
- controller-visible time;
- algorithm-specific semantic state schema;
- stateful private-state propagation.

### PASS

Exact semantic self-replay under the declared CUBIC oracle for the supported callback/state contract.

### Contract discovery

If CUBIC exposes a missing callback-visible input, add it, version the ABI, and retry within the week-3 deadline.

### FAIL

The project cannot faithfully represent CUBIC-class controller state by the hard deadline.

### Response

Narrow claims immediately rather than spending the semester endlessly rescuing R3.

---

## Project-level hard kills

Stop or fundamentally narrow if:

1. replay-critical event loss cannot be detected reliably;
2. callback ordering/result semantics cannot be preserved;
3. Reno exact semantic self-replay cannot be achieved;
4. the debugger cannot localize a meaningful implementation regression beyond what simple tracing already reveals;
5. close prior work is discovered that already provides essentially the same callback-level differential replay/debugging mechanism.
