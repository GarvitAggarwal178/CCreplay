# Recorder Overhead Sanity Check

**Phase:** N0 (per `docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md` — diagnostic-only, not the formal
non-interference study).

## Status

**COMPLETE.** Ring-buffer notification/wakeup handling was the dominant measured contributor to
the `cong_avoid` per-callback cost under the N0 loopback diagnostic — not `bpf_ktime_get_ns()` and
not the reference-kfunc/`BPF_CORE_READ` work itself. This is a diagnostic finding at loopback rates,
not a universal claim about what dominates recorder cost under every workload/topology; see
Limitations for what it does and does not establish.

## Question

Phase 1 (`REPORT_PHASE1_RENO_REPLAY_VALIDATION.md`) reported `cong_avoid ≈ 20–25 µs/callback` with
`kernel.bpf_stats_enabled=1`. This is suspiciously high for a kfunc call plus a handful of
`BPF_CORE_READ`s. Does it represent intrinsic recorder cost, or an artifact of measurement/
instrumentation?

## Precommitted expectation

Before running anything: `bpf_ktime_get_ns()` was suspected first (it's the one call in the
wrapper with no obvious cheap implementation guarantee on a paravirtualized clocksource), with
`bpf_stats` instrumentation itself as the second suspect. The ring-buffer wakeup was not the
leading hypothesis going in.

## Environment

- Kernel: `6.18.33.2-microsoft-standard-WSL2` (unchanged from Phase 1).
- Clocksource: `tsc` (active), `hyperv_clocksource_tsc_page`/`hyperv_clocksource_msr`/`acpi_pm`
  available but not selected — `cat /sys/devices/system/clocksource/clocksource0/current_clocksource`.
  The kernel judged the enlightened-VMCS TSC reliable enough to use directly (matches earlier
  Phase-1 dmesg: "kvm_intel: Using Hyper-V Enlightened VMCS").
- Topology: **loopback (127.0.0.1), not the Gate-3-R2 emulation topology.** Deliberate deviation,
  in-scope for N0 (explicitly diagnostic, not a gate) — the Gate-3-R2 path only reaches ~414
  `cong_avoid` events/s (rate-limited to 10 Mbit/s), giving ≈0.9% CPU-time signal per wall-second
  at the ~20 µs/callback scale, below what coarse timing can resolve. Loopback reaches
  ~20,000–32,000 events/s, ~50–80× the signal.

## Method

Three BPF program variants, compiled and loaded independently (never edited in place — see
Implementation below):

1. **`baseline_production`** — `bpf/reno_wrapper.bpf.c`, the actual production recorder, unmodified.
2. **`noktime_variant`** — `bpf/diagnostic/reno_wrapper_noktime.bpf.c`: byte-identical to (1) except
   `bpf_ktime_get_ns()` is never called (`ts_ns` left `0`). Tests N0.4.
3. **`nowakeup_variant`** — `bpf/diagnostic/reno_wrapper_nowakeup.bpf.c`: byte-identical to (1)
   except every `bpf_ringbuf_submit()` passes `BPF_RB_NO_WAKEUP` instead of `0`. Consumer switches
   from `ring_buffer__poll()` (wakeup-driven) to `ring_buffer__consume()` busy-polled every 2 ms
   (`user/diagnostic/generic_loader.c`, a reusable diagnostic-only loader — no skeleton codegen,
   attaches any `.o`'s struct_ops generically). Tests N0.3.

None of these variants' traces are used for any replay gate; `raw/recorder_overhead/` is entirely
separate from `raw/r0/`.

Each variant: `iperf3 -c 127.0.0.1 -n 3G -C <name>`, `kernel.bpf_stats_enabled=1`,
`run_time_ns`/`run_cnt` read directly from the `cong_avoid` BPF program's own accounting at
teardown, 3 repetitions for `baseline_production` and `nowakeup_variant`, 2 for `noktime_variant`
(time-budget-limited — see Limitations).

## N0.1 — measurement arithmetic

Verified against all three Phase-1 R0 traces before running any new experiment (no new experiment
needed — this was checkable from already-committed data):

| rep | `cong_avoid` `run_cnt` (bpf_stats) | `cong_avoid` events in trace | match |
|---|---|---|---|
| rep1 | 37,254 | 37,254 | yes |
| rep2 | 37,385 | 37,385 | yes |
| rep3 | 37,394 | 37,394 | yes |

`ssthresh`/`undo_cwnd` counts matched identically. Per-program attribution is correct; the
Phase-1 ns/callback figure was not computed by dividing aggregate runtime by an unrelated count.

## Evidence

`data/recorder_overhead/ns_per_callback_summary.csv` (raw loader output in
`raw/recorder_overhead/`):

| variant | reps | ns/callback (each rep) | mean |
|---|---|---|---|
| `baseline_production` | 3 | 6847.0, 8837.0, 8113.6 | **7,933** |
| `noktime_variant` | 2 | 9872.0, 8261.1 | **9,067** |
| `nowakeup_variant` | 3 | 317.8, 191.6, 186.9 | **232** |

**`nowakeup_variant` is ~34× lower than `baseline_production`** (7,933 / 232 ≈ 34.2), consistent
and reproducible across all 3 repetitions of each (no overlap between the two distributions: the
lowest `baseline_production` rep, 6,847 ns, is still ~22× the highest `nowakeup_variant` rep,
317.8 ns).

**`noktime_variant` shows no reduction relative to `baseline_production`** — if anything slightly
higher (9,067 vs 7,933 ns mean), which is not read as evidence `bpf_ktime_get_ns()` costs more than
zero; it is read as **no detectable signal**, consistent with a cheap TSC-backed read and the
run-to-run variance already visible within `baseline_production`'s own 3 reps (6,847–8,837 ns,
a ~29% spread with nothing changed between them).

Integrity (`invocations == emitted + drops`, zero drops) held on every one of the 8 diagnostic
runs, including all 3 `nowakeup_variant` reps — confirming the busy-polled `ring_buffer__consume()`
drain strategy caught every event despite the producer never signaling wakeup readiness (this is
exactly the property `BPF_RB_NO_WAKEUP` puts at risk if the consumer strategy is wrong; verified,
not assumed).

## N0.2 — `bpf_stats` instrumentation cost

**Not directly measurable as stated in the task brief.** `run_time_ns`/`run_cnt` only exist when
`kernel.bpf_stats_enabled=1` — there is no ns/callback number to compare against with stats off,
by construction. An external metric (wall-clock time for the fixed 3 GB transfer) was tried first
and discarded: at loopback throughput (~30 Gbit/s, ~1s per 3 GB) it is dominated by scheduler/
memory-bandwidth noise unrelated to the recorder — one run of `noktime_variant` measured 2.02s wall
against ~1.0–1.02s for every other variant including the unmodified control, a result with the
wrong sign to be a real recorder-cost signal, and not reproduced in later reps. Wall-clock time at
this scale is not a usable proxy for this question and is reported here as a discarded method, not
a result.

**Evidence-based inference, not a direct measurement:** `bpf_stats` accounting requires two
additional clock reads per invocation (enter/exit timestamps), performed by the kernel on the same
`tsc` clocksource `bpf_ktime_get_ns()` uses. Since removing the wrapper's own `ktime` read (N0.4)
produced no detectable cost reduction, the two stats-accounting reads — the same operation, same
clocksource — are inferred to be similarly cheap. This is an inference from N0.4, explicitly
labeled as such, not a measurement stats-off could ever produce.

**Classification: unresolved as a direct measurement; inferred small, not zero.**

## N0.3 — ring-buffer wakeup effect

**Primary finding.** `BPF_RB_NO_WAKEUP` + busy-polled `ring_buffer__consume()` reduces measured
`cong_avoid` cost from a mean of 7,933 ns to 232 ns — a ~34× reduction, reproducible across 3 reps
each, with the two distributions non-overlapping. This is the dominant explanation for Phase 1's
~20–25 µs/callback figure (the netns Gate-3-R2 topology's absolute numbers differ from loopback's,
but both use the same wakeup-signaling `bpf_ringbuf_submit(e, 0)` — see Limitations for why the
two are not being claimed numerically equal).

**Not adopted into the production recorder in this session.** Per `docs/session/
OVERNIGHT_EVIDENCE_PIPELINE.md` N0.3: adoption is conditional on (a) zero replay-critical loss
remaining — confirmed here (drops=0, `invocations==emitted` on every `nowakeup_variant` rep) — and
(b) a full Phase-1 regression pass afterward. Time budget did not permit doing the adoption
properly (migrating `user/ccr_recorder.c` to the `consume()`-based drain strategy, re-verifying
against the Gate-3-R2 topology specifically, then re-running the full Phase-1 regression) within
N0's remaining window. **Recorded as a documented, viable future optimization, not executed.** If
adopted later: mandatory Phase-1 regression (26 tests + R1 + R2 against all three committed
`raw/r0/rep*.ccr` traces) before any new trace is trusted.

## N0.4 — timestamp effect

No detectable cost reduction from omitting `bpf_ktime_get_ns()` (see Evidence above). Read
together with the confirmed `tsc` clocksource, this is consistent with — not proof of, but
consistent with — a cheap, non-trapping TSC read on this kernel/hypervisor configuration.
WSL2/paravirtualized timing overhead specifically was not confirmed as a contributor; if it were
material, `noktime_variant` should have shown a reduction, and it did not.

## N0.5 — conclusion

**Classification: primarily ring-buffer wakeup dominated**, not primarily real recorder
(kfunc-call + `BPF_CORE_READ`) cost, not primarily `bpf_stats` overhead, not primarily timestamp
cost. The ~232 ns/callback floor observed under `nowakeup_variant` is a plausible estimate of the
recorder's actual per-callback CPU cost (kfunc delegation + field snapshots + ringbuf reserve/
submit, minus wakeup signaling) — still not definitively isolated from the ~29% baseline-to-baseline
variance already observed, but an order of magnitude closer to "what the recorder logic itself
costs" than the original 20–25 µs figure was.

## Required documentation addition

Per N0.5's explicit requirement, added to `docs/LIMITATIONS.md` (not merely stated here):

> Reno R2 did not independently validate non-trivial private-state propagation because Reno has no
> private controller state under ABI v0. Stateful private-state replay remains an R3/CUBIC
> question.

## Failures and deviations

- Two shell scripts written during this investigation had a `$()`-command-substitution stripping
  issue and a JSON-parsing bug (the diagnostic loader's stdout starts with a literal `ATTACHED`
  line before the JSON block, which `json.load()` cannot parse directly) — both caught immediately
  from empty/failed output, fixed by moving inline commands to script files and stripping to the
  first `{` before parsing, respectively. Neither affected the underlying experiment data, which
  had already been written to disk correctly; only the immediate inline reporting of it failed.
- First N0.2 wall-clock attempt (see above) was discarded as unusable rather than reported as a
  finding — the 2.02s `noktime_variant` outlier had the wrong sign to be real and was not
  reproduced.

## Limitations

- `noktime_variant` has only 2 repetitions (not 3, matching the other two variants) — time-budget
  constrained. The "no detectable signal" conclusion is not overturned by a third rep in either
  direction being plausible, since both existing reps already sit close to `baseline_production`'s
  own spread.
- Loopback numbers are not claimed to equal Gate-3-R2 netns numbers; the *mechanism* (wakeup
  signaling as the dominant measured contributor) is the transferable finding, not the absolute
  ns/callback value. **The absolute figures in this report are diagnostic, not a production
  performance claim.** Gate-3-R2 was deliberately not used for this high-rate comparison (its
  ~414 events/s at 10 Mbit/s gives too little signal to resolve microsecond-scale differences — see
  Environment); a netns-topology confirmation was not attempted this session. **Formal live
  non-interference measurement (whether the recorder detectably perturbs the connection it
  instruments under the validated topology) remains a later, separate evaluation** — N0 measures
  recorder CPU cost in isolation, not interference with the TCP connection being recorded.
- `bpf_stats`'s own overhead (N0.2) remains an inference, not a direct measurement, for the reason
  stated above; this is a property of what `bpf_stats_enabled` measures, not a gap this session
  could have closed with more time.

## Gate verdict

N/A — N0 is diagnostic, not a pass/fail gate. **Investigation COMPLETE within budget.**

## Reproduction paths

- `bpf/diagnostic/reno_wrapper_noktime.bpf.c`, `bpf/diagnostic/reno_wrapper_nowakeup.bpf.c`
- `user/diagnostic/generic_loader.c`
- `raw/recorder_overhead/` (all raw run artifacts, loader stdout/stderr, iperf3 JSON)
- `data/recorder_overhead/ns_per_callback_summary.csv`

## Relevant commits

See the commit that introduces this report and its supporting files (single commit, per
`docs/REPO_WORKFLOW.md` commit-content rules — investigation, diagnostic sources, data, and report
land together since they are one coherent unit of N0 work).
