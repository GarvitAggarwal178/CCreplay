# CUBIC Replay Validation (R3)

**Naming note:** this is `docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md`'s `REPORT_GATE_R3_CUBIC.md`,
renamed per `docs/REPO_WORKFLOW.md`'s public-facing naming convention (parallel to
`REPORT_PHASE1_RENO_REPLAY_VALIDATION.md`).

## Status: **PARTIAL** — continuation-eligible

R3's literal PASS criterion ("R3B first divergence = NONE... on all valid primary traces") is not
met: all three primary traces show a first divergence, each on a `CLOCK_AMBIGUOUS` event
(`data/cubic_replay_kernel_source_correction.md`'s clock-window hazard, not a contract, model, or
recorder defect). Per the pipeline's PARTIAL continuation condition, all three required conditions
are met:

* central stateful CUBIC path replays exactly — **yes** (51,323 / 75,603 / 61,729 consecutive
  sequential Mode-B transitions, byte-exact, before the first `CLOCK_AMBIGUOUS` divergence in each
  trace);
* private state propagates exactly and nontrivially — **yes** (all 16 semantic fields changed value
  across the replayed sequence, `fields_that_never_changed_in_any_trace = []`);
* only rare/non-central callbacks remain unvalidated — **yes** (`undo_cwnd`, 0 events across all
  three reps, predicted thin in `data/cubic_replay_callback_coverage_plan.md`, marked
  `UNVALIDATED` below, not attempted via auxiliary trace this session due to remaining time budget).

**Continuation to N4 is authorized** under this reading. The verdict is deliberately PARTIAL, not
PASS — the redefinition of "pass" used internally by the replay engines (CLOCK_STABLE-only) is a
diagnostic breakdown, not the gate criterion, and is not used to claim PASS.

## Question

Does CUBIC (real kernel kfunc delegation for recording, real kernel source for the userspace replay
model) achieve exact semantic self-replay under Replay ABI v1, event-locally (R3A) and statefully
(R3B), on the validated Gate-3-R2 topology?

## Precommitted expectations

`data/cubic_replay_contract_predictions.md` (five named predictions plus additional surfaced
fields, precommitted before any empirical recording) and
`data/cubic_replay_callback_coverage_plan.md` (per-callback thin/dominant predictions, precommitted
before any primary trace existed). Both were partially revised by
`data/cubic_replay_kernel_source_correction.md` after obtaining the real kernel source — documented
transparently, not silently.

## Environment

`6.18.33.2-microsoft-standard-WSL2`, validated Gate-3-R2 topology (3 netns, veth, htb+bfifo,
10 Mbit/s, 40ms base RTT, 250000B=5×BDP bfifo, offloads disabled), `kernel.bpf_stats_enabled=1`,
`CONFIG_HZ=250`. Reference: real kernel `cubictcp_init/cong_avoid/recalc_ssthresh/state/cwnd_event/
acked` + `tcp_reno_undo_cwnd`, called directly as kfuncs (ADR-017) — verifier-load-confirmed for all
seven (`data/cubic_replay_capability_audit.md`, corrected to seven in
`data/cubic_replay_kernel_source_correction.md`). Userspace model built from
`data/kernel_source_ref/tcp_cubic.c` (real kernel source, not `bpf_cubic.c`).

## Method

1. **N2** — designed Replay ABI v1 (`docs/REPLAY_ABI.md`, ADR-017..021) before writing any
   implementation code. Built `bpf/cubic_wrapper.bpf.c` (all seven callbacks, one
   `bpf_ringbuf_reserve` per invocation — N2.2's split-record fallback was not needed, verifier
   accepted the full ~488-byte record on the first attempt) and `user/ccr_recorder_cubic.c` /
   `user/ccr_trace_v1.py`. Verified end-to-end via a loopback smoke test before any primary
   recording.
2. **N2.3** — captured 3×90s primary CUBIC traces on validated Gate-3-R2
   (`raw/cubic_replay/primary/rep{1,2,3}.ccr`): zero authoritative drops, gapless global sequence,
   dominant connection ≥99.99% of events, all seven callback types except `undo_cwnd` observed with
   remarkably consistent per-callback counts across the three independent reps.
3. **INTEGER-SEMANTICS TEST** — isolated `cubic_root`/`fls64` against a verbatim-C transcription of
   the real kernel source, 10,023 deterministic test cases (every integer 0–10,000 plus a
   log-spaced sweep to 2^62), zero mismatches, before trusting any full-trace comparison
   (`data/cubic_replay_integer_semantics_test.json`).
4. **R3A** (`user/replay_r3a.py`) — event-local replay: private state for each event comes fresh
   from that event's own recorded PRE state (CLAUDE.md Mode A), never carried over.
5. **R3B** (`user/replay_r3b.py`) — stateful replay: private state initialized once (all-zero,
   matching a freshly allocated `icsk_ca_priv`), carried forward across every event; the trace's own
   `init` event is transition #1, not skipped.

## Evidence

### R3A (event-local)

| | value |
| --- | ---: |
| Total events checked (3 traces) | 236,088 |
| Total field comparisons | 4,485,714 |
| `CLOCK_STABLE` events checked | 236,042 |
| `CLOCK_STABLE` mismatches | **0** |
| `CLOCK_AMBIGUOUS` events checked | 46 |
| `CLOCK_AMBIGUOUS` mismatches | 4 |

100.0000% exact semantic equality on every `CLOCK_STABLE` event, across all seven callback types
that fired in the primary traces, on every one of the 4,485,714 individual field comparisons
(full 16-field private-state schema checked for every callback, not only the fields each callback
is nominally expected to touch — Phase-1's `COMPARISON_FIELDS` under-scoping mistake is not
repeated).

### R3B (stateful)

| trace | events replayed sequentially before first divergence | of | first divergence callback | clock |
| --- | ---: | ---: | --- | --- |
| rep1 | 51,323 | 78,688 | `cong_avoid` | `CLOCK_AMBIGUOUS` |
| rep2 | 75,603 | 78,768 | `cong_avoid` | `CLOCK_AMBIGUOUS` |
| rep3 | 61,729 | 78,632 | `cong_avoid` | `CLOCK_AMBIGUOUS` |

`nontrivial_private_state_propagation = true`; all 16 semantic private fields changed value across
the replayed sequence in every trace (`fields_that_never_changed_in_any_trace = []`) — closes
`docs/LIMITATIONS.md` #13.

### Callback coverage vs. `data/cubic_replay_callback_coverage_plan.md`'s predictions

| callback | predicted | actual (per rep, consistent across all 3) |
| --- | --- | ---: |
| `init` | fixed, 1/connection | 2 (ADR-016 stray-socket pattern, same as Reno) |
| `cong_avoid` | dominant | ~37,150–37,240 |
| `pkts_acked` | dominant | ~41,400–41,460 |
| `ssthresh` | likely rare | 14 (nonzero, exercised) |
| `set_state` | likely very rare | 42 (nonzero, exercised) |
| `cwnd_event` | likely very rare/zero | 15 (nonzero, exercised) |
| `undo_cwnd` | likely rare/zero | **0** — `UNVALIDATED` |

Every prediction held. `undo_cwnd` is `UNVALIDATED` — zero events across all three reps, and no
auxiliary loss-injection scenario was attempted this session (remaining time budget); it is
architecturally identical to Reno's already-validated `tcp_reno_undo_cwnd` (zero CUBIC-specific
logic, `data/cubic_replay_callback_manifest.md`), which somewhat mitigates but does not close the
gap for CUBIC's own trace evidence specifically.

## Failures and deviations

1. **`_tcp_friendliness` loop→closed-form off-by-one (category B, fixed).** R3A's first run against
   real primary traces found 8 mismatches, all `priv_post_ack_cnt`/`priv_post_tcp_cwnd` on
   `cong_avoid`. Root cause: the closed-form substitution for the real source's strict-inequality
   `while (ack_cnt > delta)` loop used plain `ack_cnt // delta`, wrong exactly when `ack_cnt` is a
   positive multiple of `delta`. Fixed using the `ceil(a/b)-1 == (a-1)//b` identity. Full account:
   `data/cubic_replay_model_changes.md` Entry 1. This is the direct payoff of R3A's decision to
   compare the full 16-field private schema for every callback rather than only the fields each
   callback nominally touches.
2. **Clock-ambiguity residual (not fixed — characterized).** The only remaining mismatches (4 of
   4,485,714+ comparisons) are confined to `CLOCK_AMBIGUOUS` events. A diagnostic substitution
   (clock_jiffies32_after in place of _before, on the 46 ambiguous events only) resolved all 4
   original mismatches but introduced 2 new ones on different events — proving no single fixed
   before/after convention resolves every ambiguous event. No model change was made (adopting
   whichever snapshot matches the recorded outcome would be exactly the anti-fitting rule's
   forbidden "magic value derived from expected output"). Full account:
   `data/cubic_replay_model_changes.md` Investigation 2; new limitation:
   `docs/LIMITATIONS.md` #14.
3. **`undo_cwnd` UNVALIDATED for CUBIC specifically** (see coverage table above). Not remediated
   this session; flagged rather than silently absorbed.

## Limitations

See `docs/LIMITATIONS.md` #7 (controller-visible time), #12 (kernel portability), #13 (closed by
this report), and new #14 (clock-ambiguity residual). Additionally: the reference-strategy caveat
from `data/cubic_replay_capability_audit.md` N1.1 applies unchanged — this oracle validates
CCReplay's replay architecture, not independently the correctness of CUBIC's algorithm itself.

## Gate verdict: R3 = **PARTIAL**

Per `docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md`'s R3 verdict rubric: not PASS (R3B's literal
"first divergence = NONE" is not met), not FAIL ("central replay semantics cannot be achieved
without weakening the oracle" does not apply — central replay semantics ARE achieved exactly,
except for a characterized, irreducible measurement-boundary condition affecting 0.02% of events),
not INCOMPLETE (a defensible, fully-characterized result was reached within budget). PARTIAL's
continuation condition is met in full (see Status section). **Continuation to N4 is authorized.**

## Reproduction paths

* Traces: `raw/cubic_replay/primary/rep{1,2,3}.ccr` + `.meta.json` + `_validation.json`.
* Recorder: `build/ccr_recorder_cubic`, source `bpf/cubic_wrapper.bpf.c` / `user/ccr_recorder_cubic.c`.
* Parser: `user/ccr_trace_v1.py`.
* Model: `user/cubic_model.py` (from `data/kernel_source_ref/tcp_cubic.c`).
* Replay engines: `user/replay_r3a.py`, `user/replay_r3b.py`.
* Integer-semantics test: `data/audit_src/integer_semantics_check.{c,py}`,
  `data/cubic_replay_integer_semantics_test.json`.
* Run: `python3 user/replay_r3a.py raw/cubic_replay/primary/rep1.ccr raw/cubic_replay/primary/rep1.meta.json [rep2...] [rep3...]`
  (and analogously for `replay_r3b.py`).

## Relevant commits

`d417b2d` (ABI v1 design), `8b6336d` (recorder+parser), `2c9ba3d` (primary traces + initial model),
`4019601` (integer-semantics test), and this report's own commit (R3A/R3B engines + the
`_tcp_friendliness` fix + this report).
