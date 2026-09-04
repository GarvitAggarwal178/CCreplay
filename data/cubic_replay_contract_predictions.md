# CUBIC Replay Contract Predictions (N1.4) — precommitted before empirical field discovery

> **Correction notice:** Prediction #1 (`snd_una`) below was reasoned from `bpf_cubic.c` and is
> reversed by the real kernel source obtained later this session — NOT REQUIRED → REQUIRED. See
> `data/cubic_replay_kernel_source_correction.md`. Left unedited below per the evidence-preservation
> rule; the correction file is the record of what changed and why.

Pipeline mapping: this is `data/r3_contract_predictions.md`. See
`data/cubic_replay_capability_audit.md`'s naming table.

**Status at time of writing: no empirical recording has been performed. No live CUBIC trace exists
yet.** Everything below is a falsifiable hypothesis, grounded in reading the structurally faithful
reference port `~/cn-spike/bpf_src/bpf_cubic.c` (read-only, not modified) and this kernel's live
BTF/`offsetof` ground truth (`data/cubic_replay_capability_audit.md`), not in running the recorder.
This file is committed before any recorder build, trace capture, or empirical field-mutation
observation, per `INSTRUCTIONS.md` §9 (predictions before results).

Classification (CONFIRMED / PARTIALLY REQUIRED / NOT REQUIRED / WRONG / UNDECIDED) happens later,
in N2/N3, against real recorded traces from the real kernel `cubictcp_*` kfuncs — **not** against
this document's own reasoning, and the classification will be appended to this file rather than
silently overwriting the predictions.

---

## The five precommitted predictions

### 1. `snd_una`

**Prediction: NOT REQUIRED.**

No reference to `tp->snd_una` appears anywhere in `bpf_cubic.c`'s six callback bodies or their
helpers (`bictcp_update`, `cubic_root`, `hystart_update`, `hystart_ack_delay`,
`bictcp_hystart_reset`). CUBIC's window/HyStart logic keys off `snd_cwnd`, `snd_nxt`, and ACK
sequence numbers passed as callback arguments (`ack` in `cong_avoid`), not `snd_una` directly.
Hypothesis risk: the *real* kernel `tcp_cubic.c` could reference `snd_una` in a way the BPF port
elides or computes differently (e.g. via a helper macro not visible in this port) — this cannot be
ruled out from source reading alone, hence "prediction," not "fact."

### 2. `snd_nxt`

**Prediction: REQUIRED.**

`bictcp_hystart_reset()` sets `ca->end_seq = tp->snd_nxt` (line 175), and this function is called
from `init`, `cong_avoid` (on HyStart round restart), and `set_state` (on `TCP_CA_Loss`). This is
already confirmed present in the reference source, not merely guessed — but it is listed as a
"prediction" here because it has not yet been confirmed as an actually-populated, non-degenerate
field in a real recorded trace (e.g. it could be predicted to be trivially equal to `snd_cwnd`'s
correlate in the low-loss primary workload if HyStart hardly ever resets after the first round).

### 3. `pkts_acked` RTT sample / `rtt_us`

**Prediction: REQUIRED.**

`bpf_cubic_acked(sk, sample)` reads `sample->rtt_us` directly (line 511, 518) and it is the sole
input to `delay_min` tracking and the entire HyStart-DELAY path. Without it, `pkts_acked` cannot be
replayed at all. This is the highest-confidence prediction in this set — the *whole point* of
`pkts_acked` existing as a distinct callback (rather than folding delay-tracking into `cong_avoid`)
is to receive this per-ACK RTT sample.

### 4. `snd_ssthresh`

**Prediction: PARTIALLY REQUIRED, with a twist not anticipated by treating it as a simple
scalar.**

`snd_ssthresh` is read as ordinary PRE state (unclear if CUBIC's `cong_avoid` reads it directly —
grep shows no direct read in `bictcp_update`/`bpf_cubic_cong_avoid`; slow-start/cwnd-limited gating
uses `snd_cwnd`, not `snd_ssthresh`, so **prediction: not read by `cong_avoid`**). It **is** written
in two structurally different ways: (a) as the normal class-4 return value of the `ssthresh`
callback (`cubictcp_recalc_ssthresh`, same as Reno), and (b) — the twist — as a **direct mutation
from inside `pkts_acked`** (`tp->snd_ssthresh = tp->snd_cwnd`, lines 479/494, HyStart "exit point
found"), which is architecturally new relative to Phase-1 Reno (documented in the capability audit's
"architecturally significant finding" section). Prediction: the ABI v1 `pkts_acked` EventRecord
needs an explicit `post_snd_ssthresh` field or this HyStart-triggered mutation is invisible to
replay comparison.

### 5. `ca_state` / `set_state` argument

**Prediction: REQUIRED, but narrowly.**

`bpf_cubic_state(sk, new_state)` only branches on one specific value: `new_state == TCP_CA_Loss`
(line 426); all other state transitions are no-ops for CUBIC. Prediction: the recorded
`new_state` argument is required for event-local (Mode A) replay fidelity, but empirically, under
the low-loss Gate-3-R2 primary workload, **most recorded `set_state` events will show the
`TCP_CA_Loss` branch never taken** (see `data/cubic_replay_callback_coverage_plan.md`) — i.e. this
field is required by the contract but may be under-exercised by the primary trace, an auxiliary-
scenario question, not a contract-sufficiency question.

---

## Important UNPREDICTED inputs surfaced by source reading (beyond the pipeline's five)

The pipeline named five candidate fields as a starting hypothesis set, not an exhaustive one. N1.3's
full read of `bpf_cubic.c` surfaced several more fields/mechanisms that a Replay-ABI-v1 design must
account for and that were not on the pipeline's named list:

* **`tp->snd_cwnd`, `is_cwnd_limited`** — `cong_avoid` returns immediately if
  `!tcp_is_cwnd_limited(sk)` (line 391), identical gating pattern to Reno's ADR-015 discovery. Since
  ADR-015 already added `is_cwnd_limited`/`max_packets_out` to Replay ABI v0, this is a
  **reused-field prediction**, not a new one — expected to carry over unchanged.
* **`tp->lsndtime`** — read by `cwnd_event` for its idle-time shift calculation (line 202). Not on
  the pipeline's five; newly surfaced, needed only for `cwnd_event`.
* **`sk->sk_pacing_rate`, `sk->sk_pacing_status`** — read by `hystart_ack_delay()`/
  `hystart_update()` inside `pkts_acked` (lines 447, 474). Not on the pipeline's five; newly
  surfaced, needed only for `pkts_acked`'s HyStart-ACK-train path.
* **Two independent clock sources** (`tcp_jiffies32` global, `tp->tcp_mstamp` per-socket) — see the
  capability audit's clock-window hazard section. Not fields in the traditional PRE-state sense, but
  both are required controller-visible-time inputs with no Phase-1 precedent (Reno's math had zero
  time dependency).
* **`CONFIG_HZ` (=250, ground-truthed from `/proc/config.gz`)** — a boot/build-time constant, not a
  per-event field, but load-bearing for interpreting `tcp_jiffies32` deltas; belongs in
  `RecorderRunMetadata`, not in per-event records.
* **Cross-callback private-state dependency**: `delay_min` is written only by `pkts_acked` and read
  only by `cong_avoid`/`pkts_acked` itself — this is the concrete "non-trivial private-state
  propagation across callbacks" case that `docs/LIMITATIONS.md` #13 flagged as untested by Reno R2.
  It is the single field most load-bearing for R3B's stateful-replay claim.

These will be tracked through N1.5's manifest and N1.6's coverage plan, and classified alongside the
five named predictions once empirical traces exist.
