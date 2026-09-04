# CUBIC Callback Manifest (N1.5)

Pipeline mapping: this file is new relative to the pipeline doc's four named N1 deliverables — the
pipeline folds the manifest into the same investigation as N1.3/N1.4 but doesn't name a standalone
output file for it. It is split out here (rather than inlined into the capability audit) because
`data/cubic_replay_callback_coverage_plan.md` (N1.6) needs to reference it per-callback, and because
`docs/REPLAY_ABI.md`'s eventual v1 section will need this table directly. Referenced from
`data/cubic_replay_capability_audit.md`.

Derived from the selected reference (`~/cn-spike/bpf_src/bpf_cubic.c`, read-only, structurally
faithful port — see `data/cubic_replay_capability_audit.md` N1.1 for the caveat that field-level
read/write claims are inferred from this port, not from kernel disassembly). The reference source is
authoritative for this table; nothing here is carried over from Phase-1's Reno manifest except where
explicitly marked "shared with Reno."

Real kernel struct_ops table for comparison (BTF, `data/cubic_replay_capability_audit.md` N1.1):
`cubictcp_init`, `cubictcp_cong_avoid`, `cubictcp_recalc_ssthresh`, `cubictcp_state`,
`cubictcp_cwnd_event`, `cubictcp_acked`, plus shared `tcp_reno_undo_cwnd` — seven callbacks total,
matching the port's seven `SEC("struct_ops")` functions one-for-one by role.

| callback | args | return/result | shared TCP fields read | shared TCP fields mutated | private fields read | private fields mutated | observation inputs | time dependency |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `init` | `sk` | none (void) | none | none | none (fresh `icsk_ca_priv`) | ALL 16 semantic fields (via `bictcp_reset`+`bictcp_hystart_reset`; `curr_rtt`←`~0U`, others ←0) | none | reads `tp->tcp_mstamp` (via `bictcp_clock_us`) to seed `round_start`/`last_ack` |
| `cong_avoid` | `sk`, `ack`, `acked` | none (void) | `snd_cwnd`, `is_cwnd_limited` (gate, shared w/ Reno ADR-015), `snd_nxt` (via hystart-reset path) | none directly (mutates via private state → later `ssthresh`/`pkts_acked`) | reads: `end_seq`, `last_cwnd`, `last_time`, `epoch_start`, `bic_K`, `bic_origin_point`, `last_max_cwnd`, `ack_cnt`, `tcp_cwnd`, `cnt`, `delay_min`; writes: `cnt`, `last_cwnd`, `last_time`, `epoch_start`, `ack_cnt`, `tcp_cwnd`, `bic_K`, `bic_origin_point`, `last_max_cwnd` (via `bictcp_update`), plus HyStart-reset fields (`round_start`,`last_ack`,`end_seq`,`curr_rtt`,`sample_cnt`) when `after(ack, ca->end_seq)` | `ack` (input), `acked` (input, mutated in place by `tcp_slow_start` during slow start) | reads `tcp_jiffies32` (global, hazardous — see clock-window hazard section) heavily inside `bictcp_update`; reads `tp->tcp_mstamp` only via the conditional HyStart-reset branch |
| `ssthresh` (`recalc_ssthresh`) | `sk` | `u32` (new `snd_ssthresh`) | `snd_cwnd` | none directly (return value applied by kernel core, shared w/ Reno's class-4 pattern) | reads/writes: `last_max_cwnd`; writes: `epoch_start` ← 0 | none | none — no clock read in this callback |
| `set_state` | `sk`, `new_state` | none (void) | `snd_nxt` (via hystart-reset, only on `TCP_CA_Loss` branch) | none | on `TCP_CA_Loss` only: full reset via `bictcp_reset`+`bictcp_hystart_reset` (same field set as `init`); no-op for every other `new_state` value | `new_state` (input) | on `TCP_CA_Loss` only: reads `tp->tcp_mstamp` (via hystart-reset) |
| `cwnd_event` | `sk`, `event` | none (void) | `lsndtime` (new field, not in ABI v0) | `epoch_start` (private, listed below) — no shared-state mutation | reads/writes: `epoch_start` (idle-shift only, `CA_EVENT_TX_START` branch) | `event` (input) | reads `tcp_jiffies32` (global); only on `CA_EVENT_TX_START` |
| `pkts_acked` (`acked`) | `sk`, `sample` | none (void) | reads: `snd_cwnd` (HyStart gate `>= hystart_low_window`); **writes: `snd_ssthresh` directly** (architecturally new — see capability audit) | `snd_ssthresh` (direct write, not via return value) | reads: `epoch_start`, `found`, `delay_min`, `curr_rtt`, `sample_cnt`, `round_start`, `last_ack`; writes: `delay_min`, `found`, `curr_rtt`, `sample_cnt`, `last_ack` | `sample->rtt_us` (input, the callback's entire reason for existing), `sample->pkts_acked`/`in_flight` present in `struct ack_sample` but unused by this reference | reads `tcp_jiffies32` (global, epoch-freshness gate) AND `tp->tcp_mstamp` (via `bictcp_clock_us`, HyStart ack-train) — the only callback that reads BOTH clocks |
| `undo_cwnd` | `sk` | `u32` (new `snd_cwnd`) | `snd_cwnd`, `prior_cwnd` | none (return value applied by core) | none — delegates entirely to `tcp_reno_undo_cwnd`, **shared with Reno**, zero CUBIC-specific logic | none | none |

## Notes

* `sk->sk_pacing_rate` / `sk->sk_pacing_status` are read inside `pkts_acked`'s `hystart_update()` →
  `hystart_ack_delay()` call chain but are omitted from the table's "shared TCP fields read" column
  above only for space; they are tracked in `data/cubic_replay_contract_predictions.md`'s
  UNPREDICTED-inputs section and must appear in the eventual ABI v1 schema.
* `undo_cwnd` is architecturally identical to Reno's — zero new contract surface. This means R3B's
  "non-trivial private-state propagation" claim (`docs/LIMITATIONS.md` #13) cannot come from
  `undo_cwnd`; it must come from `delay_min` (`pkts_acked` → `cong_avoid`) or from the HyStart
  field cluster (`round_start`/`last_ack`/`end_seq`/`curr_rtt`/`sample_cnt`/`found`, all written by
  one callback and read by another).
* `init` and `set_state`'s `TCP_CA_Loss` branch both perform the *same* full private-state reset —
  this is a second, independent A/B check for Mode-B replay: does the reset produce byte-identical
  private state both times, from two different callback entry points?
