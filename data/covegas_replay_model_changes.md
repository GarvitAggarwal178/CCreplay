# CoVegas Replay Model Change Log (E4)

Per the addendum's anti-fitting rule (same taxonomy as `data/cubic_replay_model_changes.md`):
A — missing contract input proven from source; B — transcription error proven from source;
C — recorder bug. No event-specific fitting.

## Entry 1 — recorder's `clock_ktime_ns_before` did not match the algorithm's own `now` (category C, fixed)

* **Mismatch event:** loopback smoke-test trace, `seq=0`, `init`. First (and only) mismatch found
  by E2's first run against a real recorded trace, on `priv_post_last_minrtt_probe_ns`.
* **Category: C — recorder bug.** `bpf/covegas_wrapper.bpf.c`'s `fill_common()` called
  `bpf_ktime_get_ns()` independently to set `clock_ktime_ns_before`, and `ccr_covegas_init`/
  `ccr_covegas_cong_avoid` separately called `bpf_ktime_get_ns()` again to compute the `now` value
  actually fed to the algorithm logic (`ca->last_minrtt_probe_ns = now` in `init`;
  `handle_minrtt_probe(tp, ca, now)` in `cong_avoid`) — two independent reads, not one shared value.
  Since `bpf_ktime_get_ns()` has nanosecond resolution, two sequential reads separated by any real
  work (here: `snap_shared_pre`/`snap_private`, a handful of `BPF_CORE_READ`s) are essentially never
  equal — confirmed directly: `clock_ktime_ambiguous` was 100% of events in every capture, both
  before and after this fix (a real, disclosed clock-resolution property of `bpf_ktime_get_ns()` on
  this kernel, not itself the bug — see the note below). The *recorded* `clock_ktime_ns_before`
  therefore did not equal the *actually-used* `now`, and the model (correctly using the recorded
  value) diverged from the recorder (which had used a different, later value).
* **Exact change:** `fill_common()` now takes `now_ktime` as a parameter instead of calling
  `bpf_ktime_get_ns()` internally; every call site computes `now = bpf_ktime_get_ns()` **once**
  and passes the same value both to `fill_common` (as `clock_ktime_ns_before`) and to the algorithm
  logic (`handle_minrtt_probe`/`covegas_init`'s `now`). `ccr_covegas_init`/`ccr_covegas_cong_avoid`
  restructured to compute `now` before the recorder-vs-no-recorder branch, eliminating the
  duplicate-path duplicated logic this also required (previously `do_init`/`do_init_instrumented`
  were two separate, hand-duplicated code blocks; now one shared block, entered via an `if (e)`
  guard at both ends instead of two `goto` targets).
* **Reference source region:** N/A — this is purely a recorder-instrumentation bug (the algorithm
  logic copied from the read-only reference was never wrong; the *new* instrumentation code wrapping
  it read the wrong clock value).
* **Re-recording required:** no new *primary* trace existed yet at the time this was found (found
  against a disposable loopback smoke-test trace, explicitly not a primary evidence trace, before
  any Gate-3-R2 capture was attempted).
* **Resulting commit:** the commit that introduces `bpf/covegas_wrapper.bpf.c`,
  `user/covegas_model.py`, and this file together (this fix predates any primary trace, so it is
  folded into the initial implementation commit rather than a separate correction commit).

## Note: `clock_ktime_ambiguous` is expected to be ~100% of events, and this is not itself a defect

Unlike `tcp_jiffies32` (coarse, `HZ=250` → 4ms resolution — CUBIC found ~99.98% `CLOCK_STABLE`),
`bpf_ktime_get_ns()` has nanosecond resolution, far finer than the real work happening between any
two sequential reads. Two `bpf_ktime_get_ns()` calls separated by even a few CPU cycles of real
work will almost always differ by at least 1ns. This makes the `CLOCK_STABLE`/`CLOCK_AMBIGUOUS`
classification, as literally defined (`before == after`), **structurally near-tautological for
this clock** — it does not carry the same diagnostic weight it does for `tcp_jiffies32`, and a
near-100% `CLOCK_AMBIGUOUS` rate for `clock_ktime_*` is the *expected*, not anomalous, result.
Measured, not assumed (ADR-024 explicitly left this open pending measurement). What actually matters
for replay exactness is whether `covegas`'s ktime-derived comparisons (all against millisecond-scale
thresholds — the 200ms probe hold, `RATE_SETTLE_MS`≥1000ms) are sensitive to nanosecond-level
before/after slop, which E2/E3's actual pass/fail results answer directly and empirically, not this
proxy metric. See `REPORT_COVEGAS_REPLAY_FIDELITY.md`'s clock-transfer discussion for how this was
scored.
