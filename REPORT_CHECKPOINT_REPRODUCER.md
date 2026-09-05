# Checkpoint + Suffix Reproducer (N6)

**Naming note:** this is `docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md`'s `REPORT_CHECKPOINT_REPRODUCER.md`
(already a public-facing name, no rename needed).

## Status: COMPLETE

## Question

Can a replay-private-state checkpoint, taken during a full model-vs-model replay, be used to
reproduce an already-found first divergence by replaying only the suffix from that checkpoint
forward — without deleting or skipping any event in that suffix?

## What was built

`user/ccreplay_checkpoint.py`:

* **Deterministic serialization** — checkpoints are JSON with `sort_keys=True`; two independent
  runs of the same trace/models/interval produce byte-identical checkpoint files (verified: `diff`
  reports no difference between two independent runs saved to separate files).
* **Schema version** — every checkpoint carries `schema_version=1` explicitly.
* **Exact snapshot/restore** — a checkpoint captures both the reference's and the candidate's full
  private-state dict (`dict(ref_state)`/`dict(cand_state)`, a real copy, not a reference) at a given
  event index, plus the trace/module identity and the event's `seq`.
* **Resume from event boundary** — `replay_suffix_from_checkpoint` restores state from a checkpoint
  and replays events strictly *after* the checkpoint's index through a target index, in full
  sequential order.

## Demonstration: one positive seeded bug (Bug 1 — wrong `ssthresh` reduction)

Trace: `raw/cubic_replay/primary/rep1.ccr`. Checkpoints taken every 500 events.

| | value |
| --- | --- |
| First divergence, full from-scratch run (D) | event_index=1704, seq=1705, callback=`ssthresh`, field=`result` |
| Nearest checkpoint at or before D (K) | event_index=1500, seq=1501 |
| Suffix replayed | events [1501 .. 1704] — **204 events, every one of them, in order** |
| Divergence found from the suffix replay | event_index=1704, seq=1705, field=`result` — **identical** |
| `reproduced_same_divergence` | **true** |

This is a reproducer, not minimization: every event in `[K+1, D]` was replayed, none deleted or
skipped — the checkpoint's entire purpose is that events `[0, K]` are already fully accounted for
by the saved state (captured, not discarded). No claim of a shorter, minimized, or reduced
reproduction sequence is made; `docs/LIMITATIONS.md` #9 ("no arbitrary event minimization") is
respected by construction, not merely by disclaimer.

## Reproduction

```
python3 user/ccreplay_checkpoint.py raw/cubic_replay/primary/rep1.ccr \
  --reference user.cubic_model --candidate user.cubic_model_bug_ssthresh \
  --interval 500 --save-checkpoints-to /tmp/checkpoints.json
```

## Relevant commit

This report's own commit (adds `user/ccreplay_checkpoint.py` and this file).

Mandatory Phase-1 regression: reverified clean before this commit (40/40 tests).
