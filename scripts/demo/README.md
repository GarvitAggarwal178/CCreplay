# CCReplay — Professor Demo (presenter guide)

Three deterministic, offline scripts. Total runtime ≈ 2 s. No network, no UI, no manual edits
between steps.

```
bash scripts/demo/demo_00_run_all.sh
```

runs, in order:

1. `demo_01_negative_control.sh` — identical implementations → **NO DIVERGENCE**
2. `demo_02_first_divergence.sh` — reference vs. a seeded one-line defect → **first divergence** (one callback, one field)
3. `demo_03_checkpoint_reproducer.sh` — reproduce that exact divergence from a checkpoint + a 204-event suffix

All numbers are cross-referenced in `data/demo/DEMO_NUMBERS.md` (every value cites a repository
source path).

---

## Problem

A performance trace (throughput curve, cwnd sawtooth, RTT plot) shows the *effect* of a
congestion-control regression. But the bug lives inside a CC callback transition — `ssthresh()`,
`cong_avoid()`, `pkts_acked()` — and reasoning backward from an aggregate curve to the first wrong
transition is slow and error-prone.

## What CCReplay does

```text
live CC callback boundary
  -> Replay Contract recording          (BPF struct_ops wrapper; versioned .ccr trace)
  -> reference / candidate offline replay   (deterministic userspace re-execution)
  -> first semantic divergence          (the first callback where the two implementations stop agreeing)
```

> CCReplay answers what a congestion-control implementation computes at a recorded callback
> boundary. It does not claim what network trajectory or performance that implementation would have
> produced.

## Step 1 — negative control

`user.cubic_model` replayed against **itself** over a real recorded CUBIC trace
(`raw/cubic_replay/primary/rep1.ccr`, Replay ABI v1):

```text
EVENTS CHECKED:   78,688
RESULT:           NO DIVERGENCE
```

Two identical implementations never disagree — this is the sanity floor for every claim that
follows.

## Step 2 — seeded regression

`user.cubic_model` (known good) vs. `user.cubic_model_bug_ssthresh` — an exact copy with **one
line changed**: the `ssthresh` reduction is off by +1.

```text
MATCHING EVENTS BEFORE DIVERGENCE: 1704

========= FIRST DIVERGENCE =========
EVENT INDEX: 1704
SEQ:         1705
CALLBACK:    ssthresh
FIELD:       result
  REFERENCE: 145
  CANDIDATE: 146
====================================
```

CCReplay pins the regression to **one callback invocation and one field**, not a region of a
graph.

## Step 3 — reproducer

The same divergence, reproduced by replaying **only** events 1501–1704 (the 204-event suffix) from
a private-state checkpoint taken at event 1500:

```text
FULL TRACE DIVERGENCE:  event_index=1704 seq=1705 callback=ssthresh field=result
CHECKPOINT:             event_index=1500 seq=1501
REPLAYED SUFFIX LENGTH: 204  (events 1501..1704, every one, in order)
REPRODUCED DIVERGENCE:  event_index=1704 seq=1705 field=result
IDENTICAL RESULT:       True
```

This is a **reproducer, not minimization**: events [0, 1500] are fully accounted for by the saved
checkpoint state (captured, not discarded); every event in [1501, 1704] is replayed, in order,
none removed.

## Why useful

> Instead of manually reasoning backward from a throughput or cwnd graph, CCReplay identifies the
> first controller transition where two implementations stop agreeing.

Do **not** claim the first divergence proves later throughput / RTT causality — it is a software
result about what the controller computes, localized to a callback boundary.

## Optional add-on — historical A3 regression (real captured trace)

`demo_04_historical_a3.sh` runs against `raw/covegas_campaign/rep4.ccr` — a real captured Replay
ABI v2 CoVegas trace acquired by the capped historical campaign (valid run 4 of 4). It contains,
in one COMPETE episode: a spurious `DELAY→COMPETE` transition during a cross-traffic OFF period
(`seq=9533`), and ≈ 1 s later a settle-latch guard evaluation (`seq=10421`) with
`dlv_rate_bps / dlv_rate_max ≈ 0.996` — so the fixed/v4 "A3" guard **reverts** (no real competitor
is depressing the rate). The reconstructed v3 build (v4 source with **only** that guard reverted to
an unconditional latch) **latches** instead.

```text
FIRST DIVERGENCE:  event 10420 / seq 10421 / cong_avoid
  priv_post_mode              fixed/v4 = DELAY (revert)   recon-v3 = COMPETE (latch)
  priv_post_dlv_rate_compete  fixed/v4 = 0                recon-v3 = 1,192,908
  + post_snd_cwnd and the full revert_to_delay()-vs-cubic_growth() field set
```

**Disclosure:** `reconstructed-v3` is a documented reconstruction (v4's committed source with one
conditional reverted), **not** original committed v3 source — v3's `src/covegas.bpf.c` was never
committed to the read-only repo. Narrow claim only: on the recorded fixed/v4 callback stream,
reconstructed-v3 first differs from fixed/v4 at that Predicate-D event. **Not** a claim about
alternate throughput / RTT / queue state or a recreated 120 s network outcome.

The main demonstration (steps 1–3) works without this add-on; `demo_00_run_all.sh` appends it only
when the trace is present.
