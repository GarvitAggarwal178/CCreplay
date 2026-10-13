# Architecture Decision Records

## ADR-001 — NetFork deprioritized

**Status:** accepted.

Gate 0 showed ordinary throughput comparisons were highly reproducible, while the weak queue-delay axis was driven by tiny policy separation. The later phasecheck weakened the “same waveform with multi-second phase drift” interpretation.

**Decision:** do not build NetFork as the semester artifact.

## ADR-002 — Live ShadowCC rejected as centerpiece

**Status:** accepted.

Passive in-kernel shadow execution provides weaker debugging ergonomics than userspace replay while imposing verifier/state constraints.

The kernel retains the task only it can perform faithfully: capture the live CC callback boundary.

## ADR-003 — Record/replay architecture adopted

**Status:** accepted.

```text
kernel callback recorder -> versioned trace -> userspace replay -> differential debugger
```

## ADR-004 — Replay controller boundary, not full TCP

**Status:** accepted.

Linux TCP may mutate shared state between callbacks. Mode B therefore injects recorded shared boundary state at every callback while controller-private replay state evolves.

## ADR-005 — Callback results are first-class

**Status:** accepted.

Return values such as `ssthresh()` are controller decisions and may be applied by TCP after callback return. They must be recorded explicitly.

## ADR-006 — Exact semantic replay terminology

**Status:** accepted.

Correctness means exact equality on declared semantic callback results/state fields, not blanket raw-byte equality.

## ADR-007 — Wrapper recorder initially

**Status:** accepted.

Do not assume an independent `struct_ops` observer can coexist with native CCA ownership. Initial recorder is the active wrapper/reference CC.

## ADR-008 — Callback capability manifest

**Status:** accepted.

Different CCAs implement different callback subsets. Each trace declares the surface it promises to record.

## ADR-009 — Sequence allocation before recording success

**Status:** accepted.

A failed ring-buffer reservation must not erase a callback from logical history. Sequence is allocated at callback entry; authoritative drops live outside the ring buffer.

## ADR-010 — `SK_STORAGE` preferred, not assumed

**Status:** proposed pending R0.

Use if available from the selected context; otherwise use a documented fallback.

## ADR-011 — Mode A and Mode B retained

**Status:** accepted.

Mode A independently validates transitions. Mode B validates private-state evolution while injecting recorded shared TCP state at every event. Neither claims alternate network execution.

## ADR-012 — Arbitrary event minimization excluded

**Status:** accepted.

Base reproducer is checkpoint + suffix. Dependency-aware reduction is optional stretch work.

## ADR-013 — Three independent counters, not just gapless sequence, for drop integrity

**Status:** accepted (capability audit / pre-R0).

A gapless, monotonic `seq` proves no *interior* record was dropped, but cannot detect loss
truncated off the *tail* of a run (userspace stops polling before teardown; the last N events
were reserved+submitted but never drained, or never reserved at all after the last observed
`seq`). `RECORDER.md`'s authoritative BPF-side drop counter is necessary but, alone, does not
close this either, since it only counts reservation failures, not a total-invocation count to
check emitted+drops against.

**Decision:** the recorder maintains three atomic counters (`invocations`, `emitted`, `drops`),
all read directly from the map at teardown, before the struct_ops program is unregistered. A
trace is integrity-valid only if `invocations == emitted + drops` **and** `seq` is gapless — the
two checks catch different failure classes (interior loss vs. tail truncation) and neither
substitutes for the other.

## ADR-014 — Reno wrapper has no `.init` and no controller-private state

**Status:** accepted (capability audit / pre-R0).

Upstream `tcp_reno_ops` implements no `.init`. The capability audit's empirical field-mutation
pass (100% exact replay match on 24,651 real `cong_avoid` events using only already-classified
shared-TCP-state fields) confirmed Reno reads/writes nothing outside `SharedTcpPreState`/
`ControllerOwnedPostState` — it has no algorithm-private history, epoch, or mode state. Per
`RECORDER.md`'s "do not invent private state merely because the generic schema supports it," the
wrapper declares no `.init` and does not allocate `SK_STORAGE` for Reno, even though `SK_STORAGE`
was separately validated as available (capability audit section B) for a future controller that
does need it.

## ADR-015 — `is_cwnd_limited`/`max_packets_out` added as required (not optional) `cong_avoid` inputs

**Status:** accepted (capability audit / pre-R0, before first trace recorded).

`docs/REPLAY_ABI.md`'s original example field list for `cong_avoid` (`snd_cwnd`, `snd_cwnd_cnt`)
did not mention the gating condition `tcp_is_cwnd_limited()`. The capability audit's Mode-A dry
run against real captured traffic found two events with identical `snd_cwnd`/`snd_ssthresh`/
`acked` but opposite outcomes (one grew, one didn't), explained exactly by differing
`is_cwnd_limited`/`max_packets_out` values. Without these fields, event-local replay would apply
growth the real kernel did not. Added to Replay ABI v0's required `cong_avoid` input set before
any trace was recorded under this contract, so no `trace_version` bump or re-recording was
triggered — this is the contract-discovery process `GATES.md`/`IMPLEMENTATION_HANDOFF.md`
anticipate, completed at the cheapest possible point (pre-recording, via a disposable audit
capture) rather than after an R1 mismatch.

## ADR-016 — Dominant-connection selection for multi-socket recordings

**Status:** accepted (capability audit / pre-R0).

Registering `ccr_reno` as a named congestion controller makes it available to *any* socket that
requests it by name for the lifetime of the recording, not only the one connection under test.
Empirically, two independent loopback smoke tests (the `SK_STORAGE` audit and the real recorder's
own end-to-end test) both showed a second, short-lived socket contributing exactly one stray event
alongside the ~99.999%-share main transfer socket — plausibly `iperf3` applying `-C` to its control
channel as well as its data channel, though this was not chased to a certain root cause (see
`data/capability_audit.md` section B).

`docs/SEMANTICS.md`'s core object is a **connection's** callback boundary, not a recording
window's. **Decision:** every `EventRecord` carries a `sock_cookie` (session-scoped socket-pointer
discriminator — `bpf_get_socket_cookie()` is unavailable from this program type on this kernel, so
the raw `sk` pointer value is used instead, see `docs/REPLAY_ABI.md`). The parser
(`user/ccr_trace.py`) selects the socket with the most events as the trace's dominant connection
and reports any other sockets' events as diagnostic, not as part of the replayed sequence. A trace
is rejected if the dominant connection accounts for less than 99% of events (an actual mixed-load
recording, not an incidental stray-socket artifact) rather than silently pooling two connections'
histories under one sequence.

## ADR-017 — CUBIC reference: real kernel kfuncs for recording, real kernel source for the replay model (not `bpf_cubic.c` for either)

**Status:** accepted (N1 capability audit, before any CUBIC recorder code was written).

N1.1 verifier-load-confirmed (real program IDs assigned, not merely BTF-present) that all seven of
CUBIC's real kernel functions — `cubictcp_init`, `cubictcp_cong_avoid`, `cubictcp_recalc_ssthresh`,
`cubictcp_state`, `cubictcp_cwnd_event`, `cubictcp_acked`, plus shared `tcp_reno_undo_cwnd` — are
callable as kfuncs from `struct_ops` on this kernel. **Decision:** the CUBIC recorder wraps these
real kernel functions directly (Oracle C, same architecture as Reno/ADR precedent), not the
read-only `~/cn-spike/bpf_src/bpf_cubic.c` port, which is a stronger oracle and was independently
confirmed as the kernel's own intended calling convention (`data/kernel_source_ref/tcp_cubic.c`
lines 490–497 register exactly these six kfuncs via `register_btf_kfunc_id_set(BPF_PROG_TYPE_STRUCT_OPS,
...)`).

Separately and just as importantly: the **userspace replay model** is built from
`data/kernel_source_ref/tcp_cubic.c` (the actual kernel source for this exact running kernel,
version-matched via GitHub's Releases API, not guessed) — not from `bpf_cubic.c`. Reading the real
source after having only `bpf_cubic.c` available found three load-bearing algorithmic differences
(time-math rounding order in `bictcp_update`; the HyStart round-reset trigger relocated from
`cong_avoid`'s `ack` argument to `pkts_acked`'s `hystart_update` keyed on `tp->snd_una`; a real
`sk->sk_gso_max_size` field read where the port hardcodes a constant) — see
`data/cubic_replay_kernel_source_correction.md` for the full account, including the direct reversal
of this session's own precommitted Prediction #1 (`snd_una`). Using the port for the replay model
would risk exactly the anti-fitting-rule failure mode the pipeline warns about: a mismatch that is
neither a missing-input (A), transcription (B), nor recorder (C) error, but a genuine difference
between two independently-written implementations, for which there is no legal fix under the A/B/C
taxonomy.

## ADR-018 — Two independent controller-visible clocks, captured and classified per event

**Status:** accepted (N1 capability audit / clock-window hazard investigation, before any recorder
code was written).

Reno's math has zero time dependency; CUBIC's does, and via **two independent clock sources**, not
the single `tcp_jiffies32` a naive reading might assume. `tcp_jiffies32` is a **global** kernel
jiffies counter (`(u32)jiffies`, `CONFIG_HZ=250` on this kernel — ~4ms resolution), consulted
throughout `bictcp_update`'s epoch/delta math and `cwnd_event`'s idle-shift logic; it is not stored
on any socket and cannot be captured as an ordinary shared-state field. `tp->tcp_mstamp` is an
ordinary per-socket microsecond timestamp, already updated by TCP core independently of the CC
callback, used by the HyStart path. Both are independently verifier-load-confirmed readable from
`struct_ops` on this kernel.

**Decision:** record `clock_jiffies32_before`/`clock_jiffies32_after` (snapshotted immediately
before/after the kfunc call) and classify each event `CLOCK_STABLE` (equal) or `CLOCK_AMBIGUOUS`
(changed during the call) — per the pipeline's explicit prohibition on substituting a "nearby"
clock and declaring the hazard resolved, no other timestamp (including the trace's existing
diagnostic `ts_ns`) is used as a stand-in. `tp->tcp_mstamp` needs only one PRE snapshot per event
(only TCP core writes it, never the CC callback, so it cannot change mid-call) and is recorded as
ordinary `SharedTcpPreState`, not as a before/after pair.

## ADR-019 — CUBIC semantic private-state schema: 16 fields, `unused` deliberately excluded

**Status:** accepted (N1.3 ground-truth layout, before any recorder code was written).

`struct bictcp` (`icsk_ca_priv`) has 17 declared members, ground-truthed via compiled
`offsetof`/`sizeof` against a struct built from live BTF's own field list
(`data/audit_src/print_offsets_cubic.c`; corrects a flagged prior "15 fields / 16 names"
transcription error) — 60 bytes total, matching the BTF-reported `STRUCT size=60` exactly, no
compiler-inserted padding. One member, `unused` (offset 40, `u16`), is confirmed never read or
written anywhere in the reference source. **Decision:** the semantic private-state schema is the
other 16 fields; `unused` is excluded from PRE/POST comparison (it is genuine struct content, not
compiler padding, but it is dead — including it in the equality oracle could only ever produce a
spurious pass or a spurious fail on a field the algorithm never uses). Raw `icsk_ca_priv` bytes
(104 bytes, all 16 semantic fields plus `unused` plus the unused tail past `struct bictcp`'s 60
bytes) are additionally archived per event for diagnostic ground truth, consistent with
`docs/REPLAY_ABI.md`'s existing "raw bytes may additionally be archived; correctness uses parsed
semantic fields" principle.

## ADR-020 — `pkts_acked` requires an explicit `post_snd_ssthresh` field

**Status:** accepted (N1.5 callback manifest / N1.1 kernel-source correction, before any recorder
code was written).

Unlike Reno, where `snd_ssthresh` is mutated only through the `.ssthresh` callback's return value
(a class-4 "callback result" already captured by v0's `result` field), CUBIC's `pkts_acked` writes
`tp->snd_ssthresh` **directly** from inside its HyStart path (`WRITE_ONCE(tp->snd_ssthresh,
tcp_snd_cwnd(tp))`, `data/kernel_source_ref/tcp_cubic.c` lines 426/446) — a controller-owned
mutation performed by a callback whose own nominal "result" is `void` and has nothing to do with
ssthresh. Without an explicit field for this, the mutation would be invisible to Mode A/B
comparison whenever HyStart's exit condition fires. **Decision:** `pkts_acked`'s `EventRecordV1`
carries `post_snd_ssthresh` alongside the existing `post_snd_cwnd`/`post_snd_cwnd_cnt`, capturing
`tp->snd_ssthresh` after the kfunc call regardless of whether this specific event actually triggered
the HyStart-exit branch (so a non-triggering event's `post_snd_ssthresh == pre_snd_ssthresh` is
itself a meaningful, checked assertion, not merely an absent field).

## ADR-021 — Replay ABI v1 is a new, independently-versioned record type; v0 is untouched

**Status:** accepted (N2, before any ABI-v1 implementation code was written).

CUBIC's contract surface (two clocks, seven callbacks, 16 private fields, several new shared-state
fields, an explicit `post_snd_ssthresh`) does not fit `struct ccr_event`'s 88-byte v0 layout, and
`user/ccr_trace.py` asserts `EVENT_SIZE == 88` / `HEADER_SIZE == 144` as a deliberate parse-time
ground-truth check (Phase 1). Widening `struct ccr_event` in place would silently invalidate that
assertion's meaning and put all three committed `raw/r0/rep*.ccr` traces and the mandatory Phase-1
regression at risk on every future CUBIC-driven change. **Decision:** v1 introduces a new,
separate `struct ccr_event_v1` (and a new Python parse path dispatched on `TraceHeader.trace_version
== 1`); `struct ccr_event` / `TraceVersion == 0` / all Reno code paths are not modified. The
`TraceHeader` layout itself does not change — its existing `record_size` and `trace_version` fields
already generalize to a differently-sized v1 record without requiring a header format change. Every
change under this ADR must pass the full Phase-1 regression (26 tests, R1 and R2 over all three
`raw/r0/rep*.ccr` traces) before proceeding, per the pipeline's N2 mandatory-regression requirement.

## ADR-022 — CoVegas has no kernel-native reference; the recorder instruments a copied, unmodified-logic BPF implementation directly (no kfunc delegation)

**Status:** accepted (Part D/E, before any CoVegas recorder code was written).

Reno and CUBIC's recorders delegate to real *kernel-compiled* functions, callable as kfuncs because
the kernel explicitly registers them via `register_btf_kfunc_id_set` (ADR-017 and its Reno
precedent). CoVegas has no such kernel entity — `~/cn-spike/covegas/src/covegas.bpf.c` is itself a
BPF program, and BPF programs cannot call other independently-loaded BPF programs as functions (no
kfunc registration exists, or could meaningfully exist, for another struct_ops object's callback
bodies). **Decision:** the CoVegas recorder (`bpf/covegas_wrapper.bpf.c`) copies the read-only
source's algorithm logic near-verbatim into CCReplay (documented in `docs/PROVENANCE.md`, per
CLAUDE.md's read-only-repo rule) and adds recording instrumentation (PRE/POST snapshots, sequence
counters, ring-buffer emission — the same pattern as `reno_wrapper.bpf.c`/`cubic_wrapper.bpf.c`)
directly around that copied logic, rather than wrapping a delegated call. The recorder *is* the live
reference — there is no separable "reference vs. instrumentation" split for this controller, which
is exactly what `data/covegas_replay_capability_audit.md`'s D4 reference-strength statement already
discloses (Oracle strength: validated-BPF-implementation-as-reference, not independent kernel
ground truth). This is not a weakening of the recording architecture; it is the only architecture
available for a controller with no kernel-native form, stated plainly rather than implied.

## ADR-023 — CoVegas private-state comparison is mode-dependent (PRE mode gates PRE-arm fields, POST mode gates POST-arm fields independently)

**Status:** accepted (D3, before any CoVegas recorder/model code was written).

`data/covegas_replay_capability_audit.md`'s D3 audit found `struct covegas`'s `union u` arms
genuinely alias the same memory across a `MODE_DELAY`/`MODE_COMPETE` transition (confirmed directly
from the source's own comment, not inferred) — comparing the currently-dead arm's bytes at any
instant is not merely unnecessary but actively misleading, since those bytes are a *reinterpretation*
of live data from the other arm, not a semantic value in their own right. **Decision:** the CoVegas
Replay ABI v2 comparison schema is `comparison_schema(callback, controller_mode, replay_phase)`, not
merely `comparison_schema(callback)` (CUBIC's v1 shape, sufficient there because CUBIC has no
union). Concretely: an event's PRE-state union-arm fields are compared only if that event's own
*recorded PRE* `mode` selects that arm; POST-state union-arm fields are compared only if the
*computed POST* `mode` selects that arm (independently — a transition event's PRE and POST modes
can differ). The 17 dedicated (non-union) fields are compared unconditionally, same as any other
controller's private-state schema. Raw `icsk_ca_priv` bytes remain archived diagnostically
(`docs/REPLAY_ABI.md`'s existing "Private state" section) but never enter the correctness oracle for
the dead arm.

## ADR-024 — CoVegas records two independent controller-visible clock brackets (`tcp_jiffies32` and `bpf_ktime_get_ns()`)

**Status:** accepted (D3, before any CoVegas recorder code was written).

Unlike CUBIC's second clock (`tp->tcp_mstamp`, a per-socket field the controller merely *reads*,
requiring only one PRE snapshot per ADR-018), CoVegas's second clock
(`now = bpf_ktime_get_ns()` in `covegas_cong_avoid`/`handle_minrtt_probe`/`covegas_pkts_acked`) is
**computed fresh by the controller itself, once per invocation** — architecturally closer to
`tcp_jiffies32` than to `tp->tcp_mstamp`. **Decision:** both clocks get an independent
before/after bracket (`clock_jiffies32_{before,after}`, `clock_ktime_ns_{before,after}`) around the
recorder's own instrumented call, with the same `CLOCK_STABLE`/`CLOCK_AMBIGUOUS` classification
applied to each independently (an event could be jiffies-stable but ktime-ambiguous, or vice versa,
in principle — `bpf_ktime_get_ns()` has far finer resolution than one jiffy, so ktime-ambiguity is
expected to be exceedingly rare in practice, but this is not assumed, only measured). Whether either
clock's ambiguity actually manifests in CoVegas traces, and whether CUBIC's
`ATTRIBUTED_AND_CHARACTERIZED` clock verdict transfers, is proven empirically in Part E3 — not
assumed from CUBIC's result (`REPORT_CUBIC_CLOCK_BOUNDARY_INVESTIGATION.md`), per the addendum's
explicit instruction.

## ADR-025 — CCReplay Studio wraps the existing engine; it does not re-implement or re-derive any verdict

**Status:** accepted (Studio build, 13 Oct 2026).

**Context.** CCReplay Studio is a local web app (FastAPI backend + React/Vite frontend) that lets
a user browse recorded traces, construct controller variants (parameter overrides or hand-written
Python), run the differential debugger and checkpoint reproducer, and export results, all without
leaving a browser. This is purely an interactive front end over work already proven correct
elsewhere in this project; it must not become a second, divergent implementation of replay
semantics.

**Decision.**
1. `ccreplay/*.py` (new package) only *wraps* `user/ccr_trace*.py`, `user/ccreplay_diff.py`,
   `user/ccreplay_checkpoint.py`, and the `user/*_model.py` controller modules -- it calls them
   directly and never re-implements parsing, replay, or comparison logic. `bpf/`, `user/*.py`,
   `tests/`, and `raw/` are not modified by the Studio build.
2. Every value the UI displays comes from a real call into this wrapper layer at request time; the
   frontend holds no hardcoded trace/controller/divergence data.
3. Parameter variants and user-written controllers are built by executing a **fresh copy** of an
   existing model module's source into a new module object (`ccreplay.controllers.clone_base`),
   because `transition()` calls sibling functions through its own module's namespace --
   `import`-then-monkeypatch does not work (verified empirically before this was adopted; see
   `STUDIO_CONTEXT.md` §9).
4. The Studio's ABI-validation table (Reno PASS / CUBIC PARTIAL / CoVegas PASS, with the same
   caveats as `docs/CURRENT_STATE.md` §5) is displayed verbatim in the UI and is never recomputed
   or softened by the Studio layer.
5. Studio-created artifacts (`controllers/user/*.py`, `studio_data/`, `uploads/`) are local
   application state, not project evidence; they do not retroactively validate or invalidate any
   existing gate. A Studio-run differential-debugger result is exactly as authoritative as running
   `user/ccreplay_diff.py` directly from the command line, because it is the same code path.

**Consequence.** Studio bugs (a wrapper bug, a UI bug) can misreport what the engine computed; they
cannot change what the engine actually computes, because the engine is not forked. If the Studio
and the command-line tools ever disagree on the same trace/reference/candidate, that is a defect in
the wrapper layer to be fixed, not a basis for a new verdict.

## ADR-026 — All-decisions comparison (M7) is a new orchestration loop, not new comparison logic

**Status:** accepted (M7 start, 13 Oct 2026).

**Context.** ADR-025 says `ccreplay/` "never re-implements or re-derives" the engine's comparison
logic. M7 adds an all-decisions mode (every event, both event-local/Mode A and stateful/Mode B,
compared and reported, not just the first divergence) and a parameter sweep. Read literally, "never
re-implements comparison logic" could be mistaken to forbid this -- it does not, but the boundary
needs to be stated explicitly so a future session doesn't either (a) refuse to build M7 citing
ADR-025, or (b) build it by copying/adapting `diff_trace`'s comparison arithmetic into a second,
divergent implementation.

**Decision.** `ccreplay/diff.py`'s all-decisions function is an **orchestration loop only**: for
each event it calls the exact same primitives `diff_trace` already uses --
`_detect_version_and_parse` (`user/ccreplay_diff.py`), each module's own `transition()`, and the
reference module's own declared comparison schema (`COMPARISON_FIELDS[cb]` or
`comparison_fields(cb, pre_mode, post_mode)` for v2, ADR-023) -- and simply does not stop at the
first disagreement. It introduces no new notion of "differs," no new field-selection rule, and no
alternate schema. Mode A's shared private PRE state come from the relevant **built-in base
module's** `private_pre_from_event` (`user/cubic_model.py`, `user/covegas_model.py`; Reno has none,
ADR-014) -- not from either the reference's or candidate's own copy of that function, since a
cloned/user-written candidate could in principle lack or override it, and both sides of an
event-local comparison must start from the identical recorded PRE state by construction, not from
two independently-reconstructed copies of it.

**Consequence.** Everything ADR-025 says about Studio bugs vs. engine verdicts still applies
unchanged: an all-decisions disagreement count is only as trustworthy as the per-event
`diff_trace`-equivalent comparison it's built from, and a discrepancy between the all-decisions
summary and running `diff_trace` event-by-event by hand would be a wrapper bug, never a basis for a
new engine verdict. All-decisions comparison on CUBIC does not upgrade or downgrade CUBIC's
documented PARTIAL self-replay verdict (`docs/CURRENT_STATE.md` §5) -- it is a model-vs-model
comparison (two controller implementations against each other), not a model-vs-recording self-replay
check, and must not be described as either validating or invalidating that verdict.
