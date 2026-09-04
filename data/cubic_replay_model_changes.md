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

**No entries yet.** As of this file's commit (N1), no CUBIC replay model exists, no recorder has
been built, and no trace has been captured — there is nothing yet to have produced a mismatch
against. This file is created now (per pipeline N1's file list) as the log this session is
committed to using from the first N2/N3 model change onward, not backfilled after the fact.
