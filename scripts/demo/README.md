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
ABI v2 CoVegas trace acquired by the capped historical campaign (valid run 4 of 4; 4 valid runs,
12 valid off-period boundaries, stopped on the first same-episode H+D). In one COMPETE episode it
contains:

- a `DELAY→COMPETE` transition at `seq=9533` **classified inside a cross-traffic OFF period under
  the established alignment interval; the classification also remains OFF under the documented
  sensitivity analysis** (no new time-origin work was done — see the technical docs);
- ≈ 1 s later, a settle-latch guard evaluation at `seq=10421` with `dlv_rate_bps / dlv_rate_max ≈
  0.9959` → the fixed/v4 "A3" guard **reverts** (no real competitor is depressing the rate). The
  reconstructed v3 build (v4 source with **only** that guard reverted to an unconditional latch)
  **latches** instead.

```text
10,420 matching transitions, then FIRST DIVERGENCE:  seq 10421 / cong_avoid
  mode:              fixed/v4 = DELAY (revert)   recon-v3 = COMPETE (latch)
  dlv_rate_compete:  fixed/v4 = 0                recon-v3 = 1,192,908
  + post_snd_cwnd (computed boundary value: 37 vs 65) and the full revert_to_delay()-vs-cubic_growth() field set
```

**Presenter note on `snd_cwnd`:** the `snd_cwnd` difference shown at the first divergence is the
value each implementation *computes at that recorded callback boundary* under the same recorded
input state. It does **not** imply that reconstructed-v3 would subsequently have followed a
particular cwnd, throughput, RTT, loss, or queue trajectory in a live network.

**Disclosures (both mandatory when presenting this):**

1. `reconstructed-v3` is a **documented reconstruction** (v4's committed source with one conditional
   reverted), **not** original committed v3 source — v3's `src/covegas.bpf.c` was never committed
   to the read-only repo.
2. The Replay-ABI-v2 support in the differential debugger was **implemented during the same
   session** that produced this result; it is validated by precommitted positive/negative controls
   and 7 permanent automated tests (`tests/test_ccreplay_diff_v2.py`), plus exact agreement with the
   precommitted first-divergence prediction.

Narrow claim only: on the recorded fixed/v4 callback stream, reconstructed-v3 first differs from
fixed/v4 at that Predicate-D event. **Not** a claim about alternate throughput / RTT / queue state
or a recreated 120 s network outcome.

The main demonstration (steps 1–3) works without this add-on; `demo_00_run_all.sh` appends it only
when the trace is present.

### Compact historical summary (for the five-minute version)

```text
Final precommitted campaign:  4 valid runs, 12 valid off-period boundaries, stopped on first same-episode H+D
qualifying v2 trace:          H entry seq 9533 (OFF period), D seq 10421, D rate ratio ~= 0.9959
differential:                 10,420 matching transitions, then first divergence seq 10421 (cong_avoid)
primary differences:          mode DELAY vs COMPETE ; dlv_rate_compete 0 vs 1,192,908
caveats:                      reconstructed-v3 = documented reconstruction ;
                              v2 differential path = implemented same session, validated with
                              precommitted controls + automated regression tests
```

The three scanner-audit rounds (offset re-derivation etc.) are technical documentation — bring them
up only if asked.
