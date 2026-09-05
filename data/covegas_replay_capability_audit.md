# CoVegas Replay Contract Audit (D3)

Source: `~/cn-spike/covegas/src/covegas.bpf.c` (944 lines, read in full; the only version of this
file ever committed to the read-only repo — see `data/historical_regression_selection.md` — so it
is unambiguously "the selected FIXED/reference implementation" this audit is derived from). Not
modified. Derived by direct reading, not by eye-transcription of struct layout (see N1.3-style
discipline below).

## Callback manifest

`struct tcp_congestion_ops covegas` (lines 936–944): five callbacks — fewer than CUBIC's seven; no
`.set_state`, no `.cwnd_event`.

| callback | args | return | shared state read | shared state mutated | private state read | private state mutated | time sources | observations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `init` | `sk` | void | `tp->snd_nxt`, `tp->snd_cwnd` | none | none (fresh `icsk_ca_priv`) | ALL fields (explicit zero/init, lines 813–842) | `bpf_ktime_get_ns()` (seeds `last_minrtt_probe_ns`) | none |
| `cong_avoid` | `sk`,`ack`,`acked` | void | `tp->snd_cwnd`,`is_cwnd_limited`,`srtt_us`,`snd_nxt`,`mss_cache`,`rate_delivered`,`rate_interval_us`,`rate_app_limited` (via callees) | `tp->snd_cwnd`,`snd_ssthresh` (via `handle_delay_mode`'s slow-start branch), `tp->snd_cwnd` (via minrtt-probe cwnd cut/restore and DELAY's ±1) | nearly everything (dispatches to `handle_minrtt_probe`/`handle_compete_mode`/`handle_delay_mode`) | nearly everything | `bpf_ktime_get_ns()` (probe timing), `tcp_jiffies32` (epoch/hold/settle timing — **two clocks, same class of hazard as CUBIC's ADR-018**) | none directly (delegates) |
| `ssthresh` | `sk` | `u32` | `tp->snd_cwnd` | none directly (return value applied by core) | `last_max_cwnd`,`epoch_start` (read+write) | `last_max_cwnd`,`epoch_start` (write) | none | none |
| `undo_cwnd` | `sk` | `u32` | `tp->snd_cwnd`,`prior_cwnd` | none (return value applied by core) | none — delegates entirely to `tcp_reno_undo_cwnd` (identical to Reno/CUBIC) | none | none | none |
| `pkts_acked` | `sk`,`sample` | void | `tp->snd_cwnd` | none | `min_rtt_us`,`recent_min_us`,`minrtt_probing`,`minrtt_probe_min_us` (read+write), `dlv_rate_bps`,`dlv_rate_max` (via `update_dlv_rate`) | same fields | none directly (uses `sample->rtt_us`) | `sample->rtt_us` (the callback's entire reason for existing, same role as CUBIC's `pkts_acked`) |

`init` writing "ALL fields" and `ssthresh` sharing `last_max_cwnd`/`epoch_start` across both modes
mirrors Reno/CUBIC's precedent exactly (ADR-014/N1.5).

## Private state schema — ground truth, not eye-transcribed

`struct covegas` (lines 317–378), `sizeof == 104` bytes exactly at the `ICSK_CA_PRIV_SIZE` ceiling
— **per the source's own comment** (lines 311–316), this was independently verified by the original
author two ways (native compile of the identical field layout; field reordering + remeasure) since
`bpftool btf dump ... format c` does not emit a body for `struct covegas` at all (never referenced
via CO-RE relocation — confirmed by the source comment, not re-verified independently by this
session, since CCReplay has not yet built any covegas-observing BPF object of its own — this
ground-truthing will be redone against the CCReplay-copied version once that recorder is built,
per N1.3's own discipline, not merely trusted from the source comment).

### Dedicated (mode-independent) fields — 17 total

| field | type | live in | notes |
| --- | --- | --- | --- |
| `min_rtt_us` | `u32` | both | long-term RTT floor |
| `recent_min_us` | `u32` | both | window/probe min sample |
| `detect_count` | `u32` | both (semantically DELAY-only, but reset from COMPETE's `revert_to_delay`) | |
| `last_max_cwnd` | `u32` | **both — the addendum's named example, confirmed exactly** | shared by `ssthresh` (both modes) and `handle_delay_mode`'s `keep_epoch` gate |
| `epoch_start` | `u32` | **both — the addendum's named example, confirmed exactly** | same as above; also shifted by the minrtt-probe idle-gap trick regardless of mode |
| `cwnd_before_minrtt_probe` | `u32` | both | minrtt probe runs regardless of `ca->mode` |
| `minrtt_probe_min_us` | `u32` | both | |
| `last_queue_est_pkts` | `u32` | written only in DELAY, read (telemetry) in both | **stale-while-COMPETE**: not updated during COMPETE mode, so its value during a COMPETE stretch is a leftover DELAY-mode snapshot, not "current" — a mode-dependent *staleness* semantic distinct from the union's dead-arm case, flagged separately below |
| `dlv_rate_bps` | `u32` | both | updated every `pkts_acked`, mode-independent |
| `dlv_rate_compete` | `u32` | **mode-dependent liveness, NOT the union**: `0` sentinel in DELAY and pre-settle COMPETE; nonzero only after a successful A3 latch. **Not reset to 0 on COMPETE→DELAY** (`revert_to_delay` does not zero it) — retains its last latched value through the following DELAY stretch until the *next* DELAY→COMPETE transition explicitly zeroes it (line 779). A genuine "meaningful only in some states, but not union-aliased" case, distinct from the addendum's union scenario. |
| `dlv_rate_max` | `u32` | both | decays continuously on the minrtt-probe cadence regardless of mode |
| `last_compete_exit_jiffies` | `u32` | both | written on COMPETE→DELAY, read by DELAY's `keep_epoch` gate |
| `compete_enter_jiffies` | `u32` | meaningful only pre-latch in COMPETE | stale/unused after `dlv_rate_compete` latches, until next entry |
| `last_minrtt_probe_ns` | `u64` | both | |
| `probe_action_start_ns` | `u64` | both (while `minrtt_probing`) | |
| `mode` | `u8` | both | the mode selector itself |
| `minrtt_probing` | `u8` | both | |

### Union `u` (28 bytes, mode-dependent liveness — the addendum's required audit)

```c
union {
    struct { window_start_ack, cwnd_at_window_start, rtts_in_window,
              saved_bic_origin_point, saved_bic_K, detect_hold_until } delay;  /* 24B */
    struct { cnt, last_cwnd, last_time, bic_origin_point, bic_K, ack_cnt, tcp_cwnd } cubic; /* 28B */
} u;
```

**The two arms alias the same memory** — the source's own comment states this explicitly ("the
union's delay-arm shadow fields must be read before any `ca->u.cubic.*` write below, since they
alias the same memory," line 770). This means a **raw-byte comparison across a mode transition is
not merely unnecessary but actively misleading**: bytes that were the `delay` arm's
`saved_bic_origin_point`/`saved_bic_K` become, uninterpreted, part of the `cubic` arm's
`bic_origin_point`/`ack_cnt` the instant `ca->mode` flips — a byte-level diff would report a
"mutation" that is really just a reinterpretation, not a semantic change. This is the concrete
justification for the addendum's required mode-dependent comparison schema, found directly in this
source, not asserted abstractly.

| `ca->mode` | live semantic private fields (union) | inactive/dead (union) | transition callback |
| --- | --- | --- | --- |
| `MODE_DELAY` (0) | `u.delay.window_start_ack`, `u.delay.cwnd_at_window_start`, `u.delay.rtts_in_window`, `u.delay.saved_bic_origin_point`, `u.delay.saved_bic_K`, `u.delay.detect_hold_until` | `u.cubic.*` (all 7 fields) | `handle_delay_mode`'s detector (`cong_avoid`), transitions to `MODE_COMPETE` at line 778 |
| `MODE_COMPETE` (1) | `u.cubic.cnt`, `u.cubic.last_cwnd`, `u.cubic.last_time`, `u.cubic.bic_origin_point`, `u.cubic.bic_K`, `u.cubic.ack_cnt`, `u.cubic.tcp_cwnd` | `u.delay.*` (all 6 fields) | `revert_to_delay` (`cong_avoid`, called from `handle_compete_mode`), transitions to `MODE_DELAY` |

**Exception within `MODE_DELAY`:** `u.delay.saved_bic_origin_point`/`saved_bic_K` are themselves
only meaningful if a COMPETE epoch was actually interrupted (`epoch_start != 0` at the time of the
COMPETE→DELAY revert) — on the very first-ever DELAY period (before any COMPETE entry has
occurred), these two fields hold their `init`-time zero and are not yet meaningful shadow copies.
This is a *third* level of conditional liveness (mode AND epoch-history), noted for completeness;
the primary mode-dependent gate (which union arm) is the one the addendum's audit is centrally
about.

## Time dependencies

Two independent clocks, same class of hazard as CUBIC (`data/cubic_replay_capability_audit.md`
clock-window hazard section, ADR-018):

* **`tcp_jiffies32`** (global, non-per-socket) — used extensively: `bictcp_update`'s epoch math
  (identical structure to CUBIC's, lines 435–511, explicitly "adapted" from `bpf_cubic.c` per the
  top-of-file comment), `revert_to_delay`'s `detect_hold_until`/`last_compete_exit_jiffies`,
  `handle_compete_mode`'s `elapsed_jiffies` settle check, `handle_delay_mode`'s
  `detect_hold_until`/`gap_jiffies` checks.
* **`bpf_ktime_get_ns()`** (per-call, not per-socket-cached like CUBIC's `tp->tcp_mstamp`) — used
  in `covegas_cong_avoid`/`covegas_init`/`handle_minrtt_probe`/`covegas_pkts_acked` for the minrtt
  probe's 200ms hold timing and telemetry `ts_ns`. **This is architecturally different from CUBIC**:
  CUBIC's second clock (`tp->tcp_mstamp`) is a per-socket *cached* field the CC callback reads but
  does not compute; CoVegas's `now = bpf_ktime_get_ns()` is called **fresh, once per `cong_avoid`
  invocation, by the controller itself** — meaning the recorder's own before/after
  `bpf_jiffies64()`-style bracket (ADR-018's technique) does not directly apply to this second
  clock the same way; a separate bracket around this specific read (or capturing the value the
  controller itself computed, if directly observable) needs its own design decision in the ABI
  work, not silently assumed to inherit CUBIC's `tcp_mstamp` treatment.

**Whether the existing clock ambiguity matters to this controller:** almost certainly yes for
`tcp_jiffies32` (identical mechanism to CUBIC — a global clock the recorder can only bracket, not
inject) — this must be *proven* empirically once a recorder exists (Part E3's explicit instruction:
"Do not silently inherit CUBIC's clock exception. Prove whether it applies."), not assumed here.
The `bpf_ktime_get_ns()` dependency is a second, CoVegas-specific hazard CUBIC did not have in this
form, flagged here for the ABI design step.

## Replay ABI additions required (not assuming CUBIC v1 suffices)

Per this audit, CoVegas needs, beyond anything CUBIC v1 already carries:

* the full 17-field dedicated schema above (distinct field set from CUBIC's 16 — some overlap in
  role, e.g. `epoch_start`/`last_max_cwnd`/cubic-arm fields, but CoVegas's is its own struct, not
  reusable as-is);
* **`mode`** as an explicit recorded field (drives which union arm is semantically live —
  structurally new, CUBIC has no analogous mode selector);
* the union's two arms, recorded as **two mutually-exclusive optional field groups**, selected by
  the recorded `mode` at PRE and (independently) at POST — since a single event's PRE and POST
  `mode` could in principle differ (a transition event), the comparison schema must key off PRE
  mode for PRE-arm semantics and POST mode for POST-arm semantics, not one mode value for both;
  raw `icsk_ca_priv` bytes may still be archived diagnostically (per `docs/REPLAY_ABI.md`'s existing
  "Private state" section) but the *parsed* comparison must never treat the currently-dead arm's
  bytes as semantically meaningful;
* a second per-event clock bracket for `bpf_ktime_get_ns()`, separate from the `tcp_jiffies32`
  before/after pair already established for CUBIC;
* `sample->rtt_us` (signed, same as CUBIC's `pkts_acked`) and the `struct ack_sample` fields, same
  shape as CUBIC's v1 `pkts_acked` inputs.

This will require a new `trace_version` (v2) per `docs/REPLAY_ABI.md`'s versioning rule — **not**
assumed to fit inside v1, and **not** implemented as part of this audit (ABI v2 implementation is
recorder-build work, out of scope for D3's audit step; D3 only establishes what the contract must
contain).

## Reference strength (D4)

Unlike Reno/CUBIC, CoVegas has **no independent Linux-kernel reference** — it exists only as our
own BPF `struct_ops` implementation (`~/cn-spike/covegas/src/covegas.bpf.c`), never merged upstream,
never compiled into the kernel. The live reference for recording and the userspace replay model for
self-replay would both, unavoidably, derive from this same single implementation. Per the addendum
(item 6) and `docs/CORRECTNESS_ORACLES.md`'s Oracle C framing, this must be stated plainly, not
blurred:

> CoVegas self-replay validates CCReplay's ability to capture and reproduce the selected BPF
> implementation's callback inputs, semantic state, ordering, time dependencies, and private-state
> propagation. Because the live reference and userspace model derive from the same algorithm
> implementation, this oracle does not independently establish the correctness of the CoVegas
> algorithm itself.

This is acceptable for this project's actual question. The historical case study asks *"where do
the documented buggy and fixed CoVegas implementations first differ?"* — not *"is CoVegas itself
mathematically correct?"*. The two questions are not conflated in this audit or in any later report
derived from it.

## Source repo integrity

`~/cn-spike/covegas` read-only throughout this audit (file reads only). Verified unmodified below
(mtime sweep) before commit.
