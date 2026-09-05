# Final Historical Capture Campaign — Precommit

**Committed BEFORE the first new capture** (Phase 7 of
`docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md`). `A3_TRACK_BLOCKED = NO` (Phase 1); all Phase-4
controls PASS.

## Goal

Acquire **one** usable historical differential candidate: a Replay ABI v2 CoVegas trace containing
**Predicate H and Predicate D in the SAME COMPETE episode**. This is acquisition, **not** rate
estimation.

## Configuration — exactly preserved (no changes)

```text
HOLD_MS               = 500                (scripts/covegas_run_intermittent.sh default; the only build)
CoVegas               = continuous 120 s   (iperf3 -C ccr_covegas -t 120)
CUBIC cross-traffic   = real kernel cubic, 20 s ON / 20 s OFF x3   (ports 5201 / 5301)
Topology              = validated Gate-3-R2  (scripts/setup_topology.sh + set_qdiscs.sh 250000 + set_offloads.sh)
Replay                = ABI v2, fixed/v4 controller (bpf/covegas_wrapper.bpf.c)
Recorder              = build/ccr_recorder_covegas
```

No change to: `HOLD_MS`; thresholds; bottleneck (10 Mbit/s htb + 250000 B bfifo); RTT (40 ms base,
two 20 ms netem); queue; detector; cross-traffic algorithm; phase timing.

## Hard budget (never exceeded)

```text
MAX_VALID_RUNS       = 9
MAX_VALID_BOUNDARIES = 27      (3 off-period boundaries per valid run)
MAX_TOTAL_ATTEMPTS   = 12      (valid + invalid)
```

Every attempt (valid or invalid) is retained and reported.

## Valid-run requirements

```text
drops = 0
global sequence gapless
dominant connection valid (>= 99% of events)
metadata consistent (invocations == emitted + drops; counters_read_ok)
parser / validate_run_v2 passes
```

Invalid attempts are preserved and reported but do not count toward valid-run evidence.

## Per-valid-capture procedure

1. integrity validation (`user/ccr_trace_v2.py::validate_run_v2`);
2. **H scan** — DELAY→COMPETE transitions, phase classified over the derived offset interval
   (`Δ = first_dominant_event_wall − cubic_rep1_start_wall ∈ [≈ −0.65, +0.30] s`; `ROBUST_OFF`
   required for H);
3. **D scan** — `user/scan_historical_a3.py` control flow (cwnd-limited → `handle_minrtt_probe` →
   COMPETE dispatch → `dlv_rate_compete == 0` → settle-time gate under **both** jiffies endpoints →
   `dlv_rate_bps != 0` → v4 guard FALSE);
4. **same-episode H+D** classification — a guard-failing settle-latch event whose COMPETE episode
   was entered by a Predicate-H (`ROBUST_OFF`) DELAY→COMPETE transition.

## Stop rule

```text
STOP network capture immediately when  H_AND_D_IN_SAME_EPISODE = YES   (never continue after the first acquisition)
otherwise continue until  9 valid runs  OR  12 total attempts  (whichever comes first)
```

For every H episode, record why D did or did not occur: probe blocked / settle gate not reached /
`dlv_rate_bps == 0` / guard passed / guard failed / other source-derived prerequisite.

## Probability wording (permitted only)

> If boundaries were IID with `p = 1/9` **purely as a sensitivity assumption**, then the chance of
> observing at least one Predicate-H event in 27 boundaries would be `1 − (8/9)^27 ≈ 95.8%`.

Immediately: *This is not a formal power guarantee and does not describe same-episode H+D
acquisition probability. D has additional prerequisites and no H+D occurrence probability has been
estimated.* The campaign is **not** "95%-powered".

## Hard termination (Phase 11, regardless of outcome)

```text
NO run 10; NO > 12 total attempts; NO longer trace; NO HOLD_MS change; NO threshold change;
NO new historical workload; NO post-hoc H/D redefinition.
```
