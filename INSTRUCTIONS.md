# CCReplay — Build Phase 1: R0 / R1 / R2

This is the task brief this repository's Phase 1 work (R0/R1/R2, Reno-only) was built against,
preserved verbatim for provenance. See `REPORT_PHASE1_RENO_REPLAY_VALIDATION.md` for the result
and `docs/REPO_WORKFLOW.md` for the presentation conventions adopted after Phase 1 completed.

---

We have finished the architecture/design phase.

The project is now frozen as:

# CCReplay

## Deterministic Differential Replay for TCP Congestion Control

Your job in this task is to IMPLEMENT AND TEST ONLY THE FIRST THREE GATES:

* R0 — recorder viability
* R1 — Reno event-local exact semantic self-replay
* R2 — Reno stateful-controller exact semantic self-replay

Do NOT redesign the project unless actual kernel/compiler/verifier evidence makes the frozen
architecture impossible.

Do NOT reopen NetFork, ShadowCC, congestion-control algorithm ideation, or general project
selection.

Do NOT implement the entire 11-week project.

==================================================
0. FROZEN DOCUMENTATION IS AUTHORITATIVE
========================================

I will place the frozen documentation archive at:

`~/CCReplay_Final_Documentation.zip`

Create:

`~/ccreplay`

and extract the documentation into that repository.

Expected docs include:

* `CLAUDE.md`
* `README.md`
* `docs/PROJECT.md`
* `docs/ARCHITECTURE.md`
* `docs/SEMANTICS.md`
* `docs/REPLAY_ABI.md`
* `docs/RECORDER.md`
* `docs/REPLAY_ENGINE.md`
* `docs/DIFFERENTIAL_DEBUGGER.md`
* `docs/CORRECTNESS_ORACLES.md`
* `docs/GATES.md`
* `docs/EVALUATION.md`
* `docs/CASE_STUDIES.md`
* `docs/PRIOR_ART.md`
* `docs/LIMITATIONS.md`
* `docs/ROADMAP.md`
* `docs/PROVENANCE.md`
* `docs/DECISIONS.md`
* `docs/IMPLEMENTATION_HANDOFF.md`

READ ALL OF THEM BEFORE WRITING IMPLEMENTATION CODE.

Treat them as the project specification.

If implementation reality requires a semantic change:

1. STOP.
2. Explain the mismatch.
3. Update the appropriate documentation.
4. Add an ADR to `docs/DECISIONS.md`.
5. Then continue only if the change preserves the project's central semantics.

Do NOT silently reinterpret the docs.

==================================================

1. ABSOLUTE SEMANTIC RULE
   ==================================================

The project MUST preserve:

> CCReplay answers what a congestion-control implementation computes at a recorded callback
> boundary. It does not claim what network trajectory or performance that implementation would
> have produced.

CCReplay replays:

**the congestion-control implementation boundary**

NOT:

**the whole Linux TCP stack.**

The replay model is:

```
recorded shared TCP boundary state
          +
callback arguments / observations / time
          +
controller-private state
          |
          v
   controller implementation
          |
          v
   callback result
          +
controller-owned mutations
          +
   next private state
```

For stateful replay:

* shared TCP boundary state comes from the recording at EVERY callback;
* controller-private state evolves across events;
* userspace must NOT try to emulate all TCP-core state changes between callbacks.

==================================================
2. READ-ONLY SOURCE REPOSITORIES
================================

These are STRICTLY READ-ONLY:

* `~/cn-spike`
* `~/covegas`
* `~/cn`

Never modify them.

You may inspect and copy validated infrastructure.

Every copied/adapted file must be recorded in:

`~/ccreplay/docs/PROVENANCE.md`

with:

* source path;
* source git commit;
* copied vs adapted;
* exact modifications.

Verify after this task that the source repos remain unmodified.

==================================================
3. INSPECT EXISTING INFRASTRUCTURE FIRST
========================================

Before implementation, inspect the relevant material from the existing repos.

At minimum inspect:

From `~/cn-spike`:

* environment / CLAUDE notes;
* `REPORT_GATE3R2.md`;
* `REPORT_GATES5R8.md`;
* validated Gate 3-R2 setup;
* qdisc setup;
* offload setup;
* bfifo verification;
* struct_ops examples;
* ringbuf consumer;
* validated BPF CUBIC implementation;
* existing build/load patterns.

From `~/covegas`:

* build workflow;
* struct_ops code organization;
* ringbuf telemetry patterns;
* controller-private-state usage.

From `~/cn`:

* Gate 0 methodology;
* environment notes;
* run logging / provenance discipline.

Produce:

`data/inspection_summary.md`

containing:

* reusable infrastructure found;
* exact source commits;
* what will be copied;
* what will NOT be reused;
* any assumptions requiring verification.

Do not code before this inspection is complete.

==================================================
4. INITIAL REPOSITORY STRUCTURE
===============================

Create at least:

```text
~/ccreplay/

CLAUDE.md
README.md
docs/

bpf/
user/
controllers/
scripts/
tests/

raw/
    r0/
    r1/
    r2/

data/
plots/
```

Initialize git.

Make meaningful commits at these milestones:

1. frozen docs + scaffold
2. inspection/provenance
3. capability audit
4. Replay ABI + recorder
5. R0 result
6. replay engine
7. R1/R2 result

Do not squash away evidence of failures during development.

==================================================
5. CAPABILITY AUDIT — BEFORE RECORDER IMPLEMENTATION
====================================================

Target environment:

WSL2 Ubuntu
kernel:

`6.18.33.2-microsoft-standard-WSL2`

Perform a capability audit against the ACTUAL kernel.

Do not infer support merely from upstream Linux.

Check at minimum:

### A. Reno reference functions

Determine whether these are callable BPF kfuncs in this kernel/context:

* `tcp_reno_cong_avoid`
* `tcp_reno_ssthresh`
* `tcp_reno_undo_cwnd`

Inspect BTF directly.

Do not rely only on generated `vmlinux.h`.

### B. `BPF_MAP_TYPE_SK_STORAGE`

Test whether:

* `bpf_sk_storage_get`
* and, if needed, `bpf_sk_storage_delete`

are usable from the chosen BPF struct_ops congestion-control context.

Do a minimal compile/load/register smoke test.

### C. Callback surface

Inspect the kernel's `tcp_congestion_ops` BTF.

Determine the callbacks available to BPF struct_ops.

Then define the actual callback capability manifest for the Reno wrapper.

Do NOT require Reno to implement every possible callback.

### D. Timebase

Determine:

* kernel HZ;
* controller-visible time source available to the recorder;
* whether the reference Reno path needs any replay-visible clock.

### E. Writable/readable fields

Confirm which TCP state fields the recorder can read and which the wrapper/reference logic may
modify.

Do not guess based on previous projects if the exact field matters to replay.

Write:

`data/capability_audit.md`

containing PASS/FAIL for each capability and the exact commands/evidence used.

==================================================
6. RENO REFERENCE STRATEGY
==========================

Preferred strategy:

BPF wrapper congestion controller
|
+--> record boundary PRE
|
+--> invoke Linux Reno reference kfunc
|
+--> record callback result / semantic mutations
|
+--> emit trace event

This gives an external correctness reference not written by us.

If Reno kfuncs are unavailable:

* document that clearly;
* use the smallest defensible Reno fallback;
* update `docs/PROVENANCE.md`;
* update `docs/LIMITATIONS.md`;
* state that Oracle C becomes weaker.

Do NOT silently pretend the fallback is equivalent to an independent kernel reference.

==================================================
7. TRACE SCHEMA v0
==================

Implement the semantics in:

`docs/REPLAY_ABI.md`

Do not blindly freeze every speculative field in the document.

The initial schema should be sufficient for Reno while remaining extensible.

Every trace needs:

### Trace metadata

* magic;
* `trace_version`;
* recorder version;
* kernel release;
* reference implementation ID;
* callback capability manifest;
* private-state schema ID if applicable;
* relevant connection metadata.

### Event identity

For every callback invocation:

* monotonic logical sequence number;
* callback ID;
* timestamp / controller-visible time where required.

IMPORTANT:

Allocate the logical sequence number at CALLBACK ENTRY, before knowing whether ringbuf reservation
will succeed.

### Shared TCP PRE boundary state

Capture only the fields required for:

* the Reno replay contract;
* correctness comparison;
* diagnostics needed for R1/R2.

Keep the schema extensible for R3.

### Callback inputs

Record the callback arguments exactly.

### CallbackResult

This is FIRST-CLASS DATA.

Examples:

For `ssthresh()`:

* record the actual return value.

For `undo_cwnd()`:

* record the actual return value.

For `cong_avoid()`:

* result is VOID;
* record declared controller-owned mutations.

Do NOT infer return values from shared TCP post-state.

### Controller-owned semantic POST state

Record declared state mutations required by the Reno oracle.

### Private state

If Reno has no relevant private state under this implementation, represent that explicitly.

Do not invent private state merely because the generic schema supports it.

Raw `icsk_ca_priv` capture is OPTIONAL for R0/R1/R2 unless it is needed.

Do not make raw byte equality part of Reno correctness.

==================================================
8. ONE EVENT RECORD PER CALLBACK IF POSSIBLE
============================================

Prefer:

one EventRecord =

* PRE
* inputs
* callback result
* semantic POST

If technically feasible.

Then there is no PRE/POST pairing problem.

If verifier/ring-buffer constraints force split PRE/POST records:

STOP before implementing the workaround.

Define a proper pairing protocol, update the Replay ABI, and document the reason.

Do not silently add fragile pairing logic.

==================================================
9. EVENT LOSS MUST NEVER BE SILENT
==================================

At callback entry:

1. allocate logical sequence number;
2. attempt record reservation;
3. execute the reference controller regardless of reservation success;
4. if recording failed:

   * increment authoritative BPF-side drop counter;
   * preserve live controller semantics;
5. if recording succeeded:

   * finish EventRecord;
   * submit it.

The recorder must never change the reference controller result because telemetry failed.

Use TWO integrity checks:

### A. authoritative BPF-side drop counter

Read directly from map at teardown.

### B. sequence validation

Writer/parser verifies received event IDs are monotonic and gapless.

Optional additional accounting:

* total invocations;
* total emitted.

Do NOT rely only on a ring-buffer trailer to report ring-buffer loss.

Store teardown/readback metadata in a sidecar file.

A run with any replay-critical loss is INVALID.

==================================================
10. USERSpace TRACE WRITER / PARSER
===================================

Implement a simple, robust trace format appropriate for the project.

Do not over-engineer.

Requirements:

* versioned;
* deterministic;
* parser rejects unknown versions;
* metadata preserved;
* event ordering preserved;
* direct integrity validation;
* usable offline without kernel dependency.

Implement:

* userspace ringbuf consumer / trace writer;
* parser;
* trace validation command/test.

Preserve all raw traces under:

`raw/r0/`

Never edit them manually.

==================================================
11. GATE R0 — RECORDER VIABILITY
================================

Use ONLY the validated Gate 3-R2 topology.

Do not use superseded Gate 3 or Gate 3-R topology.

Target operating point:

* bottleneck: 10 Mbit/s
* base RTT: 40 ms
* queue: 5×BDP = approximately 250000 B bfifo
* offloads off
* real forwarding
* correct qdisc topology

Use the copied validated scripts with provenance.

Run a small controlled R0 batch:

3 × 90-second SOLO Reno transfers.

For each run record:

* run ID;
* callback manifest;
* logical callback invocation count;
* emitted event count;
* events/s;
* bytes/event;
* trace size;
* trace MB/s;
* BPF drop count;
* sequence gaps;
* callbacks observed;
* teardown state.

Enable BPF runtime stats consistently where supported.

Measure:

* run_time_ns
* run_cnt
* ns/callback

across all relevant recorder programs.

### R0 PASS

Only PASS if:

* zero authoritative replay-critical drops;
* zero unexplained sequence gaps;
* trace parses;
* every invocation of every callback declared by the Reno capability manifest is recorded;
* callback results exist where required;
* metadata readback succeeds;
* live transfers complete correctly.

### R0 FAIL

Fail if:

* loss can occur silently;
* ordering is ambiguous;
* callback result cannot be represented;
* wrapper cannot execute reference Reno correctly.

Engineering fixes such as:

* larger ring;
* smaller OPTIONAL payload;
* schema-layout improvement

are allowed.

Ignoring loss is not.

==================================================
12. USERSpace RENO MODEL
========================

Implement the smallest clear Reno replay model needed for the actual Reno callback manifest.

Do not build generic framework complexity before Reno passes.

The model must be:

* deterministic;
* explicit about state;
* free of wall-clock reads;
* free of hidden globals.

Controller-visible inputs come from the trace.

Declare the exact comparison schema per callback.

For example, if applicable:

`ssthresh`

* callback result

`undo_cwnd`

* callback result

`cong_avoid`

* `snd_cwnd`
* `snd_cwnd_cnt`

Do not blindly assume these are the only fields; verify actual Linux Reno semantics.

==================================================
13. MODE A — EVENT-LOCAL REPLAY
===============================

For each event independently:

1. load recorded shared TCP PRE state;
2. load recorded private PRE state if applicable;
3. supply callback input;
4. supply observations/time;
5. execute Reno transition;
6. compare declared callback result;
7. compare declared controller-owned semantic POST state.

No replay state carries to the next event.

Create strong mismatch diagnostics.

On mismatch print at minimum:

* trace;
* sequence;
* callback;
* timestamp;
* shared PRE;
* callback inputs;
* expected result;
* actual result;
* expected semantic POST;
* actual semantic POST;
* exact differing fields;
* ±5 events context.

==================================================
14. GATE R1
===========

Gate:

**Reno event-local exact semantic self-replay**

PASS requires:

100% exact equality on every declared exact semantic field for every valid event across all three
R0 traces.

Do NOT call this merely "close."

Do NOT use tolerance for integer state transitions.

If R1 fails:

1. identify first mismatch;
2. decide whether cause is:

   * missing Replay Contract input;
   * incorrect callback semantics;
   * parser error;
   * wrapper error;
   * Reno model bug;
3. fix the cause.

If a missing Replay Contract field is genuinely discovered:

* update `docs/REPLAY_ABI.md`;
* bump `trace_version`;
* update relevant docs;
* add an ADR if semantic;
* re-record traces;
* rerun R0/R1.

This is allowed.

Weakening the oracle is not.

==================================================
15. MODE B — STATEFUL CONTROLLER REPLAY
=======================================

This is critically important.

Do NOT simulate the full Linux TCP core.

Initialize Reno controller-private replay state ONCE.

For every event:

```
shared_state = recorded shared TCP state for THIS event

transition(
    shared_state,
    callback inputs,
    observations/time,
    current private state
)
```

Then compare:

* callback result;
* declared controller-owned mutation;
* declared private semantic state.

Carry forward only controller-private replay state.

For event N+1:

shared TCP input again comes from event N+1's recording.

Do NOT derive all of event N+1's TCP shared state from event N's replay output.

==================================================
16. GATE R2
===========

Gate:

**Reno stateful-controller exact semantic self-replay**

PASS:

first divergence = NONE on all three valid R0 traces under the declared semantic comparison
schema.

If divergence occurs:

diagnose:

* state initialization;
* hidden private state;
* ordering;
* missing event;
* missing callback input;
* model bug;
* schema bug.

If a legitimate Replay Contract correction is required, version and re-record.

### HARD WEEK-2 KILL CONDITION

If Reno stateful-controller exact semantic replay cannot be achieved without changing the meaning
of CCReplay or weakening the oracle:

STOP.

Write the failure report.

Do not continue to CUBIC.

==================================================
17. TESTS
=========

At minimum create automated tests for:

### Trace format

* version rejection;
* malformed trace rejection;
* sequence-gap detection;
* drop metadata handling.

### Controller model

* deterministic repeated replay;
* callback-specific known transition tests.

### Replay engine

* same trace + same implementation gives identical replay output;
* reference vs reference yields no first divergence.

If state snapshots exist:

* snapshot/restore round-trip exactly.

==================================================
18. NO R3 IMPLEMENTATION IN THIS TASK
=====================================

Do NOT implement CUBIC in this task.

You MAY inspect what R3 will require and document:

* likely callback manifest;
* private-state requirements;
* clock/time requirements;
* recorder changes.

But stop implementation after R0/R1/R2.

R3 begins only if R1 and R2 pass.

==================================================
19. DO NOT IMPLEMENT THESE YET
==============================

Do NOT implement:

* CUBIC replay;
* Vegas;
* BBR;
* CoVegas case study;
* historical bug case study;
* full differential CLI;
* GUI/dashboard;
* generic minimization;
* dependency-aware trace reduction;
* broad performance sweeps;
* paper writing;
* controller selection;
* alternate performance prediction.

==================================================
20. REPORTING
=============

Write:

`REPORT_GATES_R0_R1_R2.md`

It must include:

## A. Environment

* kernel;
* compiler/toolchain;
* BPF capability findings.

## B. Capability audit

* Reno kfuncs;
* SK_STORAGE;
* callback surface;
* reference implementation chosen.

## C. Replay ABI as actually implemented

* trace version;
* callback manifest;
* shared PRE fields;
* callback inputs;
* callback results;
* semantic POST fields;
* private-state schema.

## D. R0

Per-run table:

* events;
* events/s;
* trace size;
* drops;
* gaps;
* callbacks;
* ns/callback.

Explicit PASS/FAIL.

## E. R1

* events checked;
* exact fields compared;
* match rate;
* first mismatch if any.

Explicit PASS/FAIL.

## F. R2

* exact semantic comparison schema;
* first divergence or NONE;
* any state propagation issues.

Explicit PASS/FAIL.

## G. Failures/deviations

Every failed compile, verifier issue, trace-integrity failure, schema correction, and experiment
failure relevant to the final design.

Do not hide corrections.

## H. R3 readiness

State exactly:

* whether CCReplay is ready for CUBIC;
* biggest remaining blocker;
* what Replay ABI additions are expected.

==================================================
21. SOURCE REPO SAFETY CHECK
============================

Before finalizing:

verify:

* `~/cn-spike` unmodified;
* `~/covegas` unmodified;
* `~/cn` unmodified.

Record this in the report.

==================================================
22. FINAL TERMINAL SUMMARY
==========================

Print exactly:

```text
CCReplay Phase 1

R0 RECORDER VIABILITY:                 PASS / FAIL
R1 RENO EVENT-LOCAL REPLAY:            PASS / FAIL
R2 RENO STATEFUL-CONTROLLER REPLAY:    PASS / FAIL

KERNEL:
RENO KFUNCS AVAILABLE:
SK_STORAGE FROM STRUCT_OPS:
REFERENCE RENO STRATEGY:

TRACE VERSION:
CALLBACK MANIFEST:
SEMANTIC COMPARISON FIELDS:

R0 EVENTS:
R0 DROPS:
R0 SEQUENCE GAPS:
TRACE SIZE / 90s:
RECORDER NS/CALLBACK:

R1 EVENTS CHECKED:
R1 FIRST MISMATCH:

R2 FIRST DIVERGENCE:

REPLAY ABI CHANGES DURING GATES:
SOURCE REPOS VERIFIED UNMODIFIED:

READY FOR R3: YES / NO

MAIN BLOCKER:
REPORT PATH:
```

==================================================
23. FINAL BEHAVIOR RULE
=======================

Do not optimize for producing PASS.

Optimize for determining whether the frozen CCReplay architecture is actually correct.

A rigorous FAIL at R1 or R2 is more valuable than a false PASS obtained by weakening the
semantics.

Once R0/R1/R2 are complete, STOP.

Do not continue automatically into R3.
