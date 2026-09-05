# CUBIC Replay Model Change Log (N1 skeleton, populated in N2/N3)

Pipeline mapping: `data/r3_model_changes.md`. See `data/cubic_replay_capability_audit.md`'s naming
table.

Per pipeline's anti-fitting-rule section, every change to the CUBIC userspace replay model or to the
Replay Contract, made in response to a real recorded mismatch, is appended here — never silently
folded into a commit without this record. Categories:

* **A — Missing Replay Contract input**: reference source proves the implementation reads a field
  absent from the trace.
* **B — Transcription error**: userspace model differs from the reference source.
* **C — Recorder error**: recorder captured, represented, or ordered an input incorrectly.

Each entry records: mismatch event; category A/B/C; exact change; reference source file and
line/region; reason; whether re-recording was required; resulting commit.

**Not permitted, per the pipeline's explicit prohibition:** event-ID special cases, trace-name
special cases, magic values derived from expected output, or logic without a source/recorder
justification traceable to one of the three categories above. If a mismatch cannot be justified
under A/B/C, it is left unresolved and reported as such — never silently patched around.

---

## Log

### Entry 1 — `_tcp_friendliness` loop→closed-form off-by-one

* **Mismatch event:** `raw/cubic_replay/primary/rep1.ccr`, `seq=25641`, `cong_avoid`. First (and
  only distinct root cause) mismatch found by R3A's first run against real primary traces.
  `priv_post_ack_cnt` expected 0 got 331; `priv_post_tcp_cwnd` expected 146 got 145. 8 total
  mismatched events in that first run, all sharing this one root cause (confirmed before writing
  this entry, not assumed).
* **Category: B — Transcription error.** The userspace model's closed-form substitution for the
  real source's `while (ca->ack_cnt > delta) { ca->ack_cnt -= delta; ca->tcp_cwnd++; }` loop
  (`tcp_cubic.c` lines 305-308) was `n = ack_cnt // delta`, which is wrong exactly when `ack_cnt`
  is a positive multiple of `delta`: the real loop's strict `>` condition means it does not execute
  at all when `ack_cnt == delta`, but plain floor division computes `n=1` in that case.
* **Exact change:** `user/cubic_model.py`'s `_tcp_friendliness`: guard the substitution on
  `ca["ack_cnt"] > delta` (mirroring the loop's own entry condition exactly) and use
  `n = (ack_cnt - 1) // delta` (the standard `ceil(a/b) - 1 == (a-1)//b` identity for `a>=1`, the
  closed form that actually matches a strict-inequality countdown loop) rather than plain
  `ack_cnt // delta`.
* **Reference source region:** `data/kernel_source_ref/tcp_cubic.c` lines 305-308.
* **Reason:** the original substitution was reasoned informally ("mathematically identical closed
  form") without checking the boundary case `ack_cnt == delta`; R3A's full-16-field private-state
  comparison (deliberately checking every field for every callback, not only the fields a callback
  is "expected" to touch) caught it on the very first real-trace run.
* **Re-recording required:** no — this is a userspace-model-only fix; the recorded trace's own
  values were never in question (the recorder delegates to the real kernel kfunc, ADR-017), only
  the model's reproduction of it.
* **Resulting commit:** to be recorded at the commit that includes this fix (same commit as this
  log entry).

### Investigation 2 — clock-ambiguous residual: before-vs-after substitution (no model change)

* **Context:** R3A/R3B's only mismatches (4 of 4,485,714+ field comparisons on the primary traces)
  are confined entirely to `CLOCK_AMBIGUOUS` events (46 of 236,088, ~0.02%) -- events where
  `clock_jiffies32_before != clock_jiffies32_after`. The model always uses `_before` (a convention
  documented in `cubic_model.bictcp_update`'s docstring before any trace was recorded).
* **Diagnostic run (not a model change):** substituted `clock_jiffies32_after` for `_before` on all
  46 `CLOCK_AMBIGUOUS` events and re-ran the comparison. Result: all 4 original mismatches resolve
  exactly with `_after` -- but 2 NEW mismatches appear on different events (`rep1` `seq=18745,41482`)
  that were exact under `_before`. **No single fixed choice (always-before or always-after) resolves
  every `CLOCK_AMBIGUOUS` event** -- this is not "the wrong pick," it is direct evidence that,
  under the current wrapper/kfunc observation boundary, the exact value the real kernel's internal
  `tcp_jiffies32` reads actually saw for these specific events cannot always be reconstructed from
  the two bracket values the recorder captures (different events are individually consistent with
  different single-read timings, with no universal rule across all of them).
* **Category: none of A/B/C.** Per the pipeline's anti-fitting rule, adopting whichever snapshot
  value makes a given event match its recorded outcome would be exactly the forbidden "magic value
  derived from expected output." **No change was made to `cubic_model.py`** as a result of this
  investigation; the `_before` convention (chosen and documented before any mismatch was observed)
  is retained, and the residual is reported as a characterized clock-boundary limitation under the
  current recorder architecture in `docs/LIMITATIONS.md` and `REPORT_CUBIC_REPLAY_VALIDATION.md`
  (report renamed since this entry was written), not resolved by tuning. See
  `REPORT_CUBIC_CLOCK_BOUNDARY_INVESTIGATION.md` for the follow-up quantitative/attribution/resync
  diagnostics that further characterize (without resolving) this limitation.
* **Reference source region:** none (this is a replay-contract measurement-boundary property, not a
  reference-source discrepancy).
* **Re-recording required:** no.
* **Resulting commit:** same commit as `REPORT_GATE_R3_CUBIC.md`.
