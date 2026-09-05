# Phase 1 — CoVegas Control-Flow Audit

Gates only the historical A3 track. Offline, statement-by-statement.

## 1.1 `handle_minrtt_probe()` return-zero state-preservation property

**Question:** *Does every path that mutates CoVegas private state return non-zero / TRUE, and does
every return-zero / FALSE path leave the private state semantically unchanged?*

### Sources compared

- `user/covegas_model.py` `handle_minrtt_probe` (lines 293–330)
- `bpf/covegas_wrapper.bpf.c` `handle_minrtt_probe` (lines 349–398)
- `~/cn-spike/covegas/src/covegas.bpf.c` `handle_minrtt_probe` (lines 606–662) — structurally
  byte-identical to the CCReplay copy (ADR-022)

### Model (`user/covegas_model.py:293`)

```python
def handle_minrtt_probe(ca, pre, ktime_now, jiffies_now):
    ca = dict(ca)                                   # LOCAL COPY -- caller's ca is never touched
    if ca["minrtt_probing"]:
        ...
        if u64(ktime_now) - ca["probe_action_start_ns"] >= dur_ns:
            ...                                      # writes: min_rtt_us, epoch_start, minrtt_probing, last_minrtt_probe_ns
            return True, ca, cwnd_override           # <-- MUTATING path -> True
        return True, ca, None                        # <-- probe still running: NO writes -> True
    period_ns = (MINRTT_SKIP_MS*1e6) if (mode==COMPETE and dlv_rate_compete!=0) else (MINRTT_PERIOD_MS*1e6)
    if u64(ktime_now) - ca["last_minrtt_probe_ns"] >= period_ns:
        ...                                          # writes: cwnd_before_minrtt_probe, minrtt_probe_min_us,
                                                     #         minrtt_probing, probe_action_start_ns, dlv_rate_max
        return True, ca, 4                           # <-- MUTATING path -> True
    return False, ca, None                           # <-- the ONLY False path: NO writes reached
```

### Path table

| path | condition | private-state writes | return |
| --- | --- | --- | --- |
| P1 | `minrtt_probing` AND `now - probe_action_start_ns >= dur_ns` | `min_rtt_us`, `epoch_start` (COMPETE+epoch only), `minrtt_probing←0`, `last_minrtt_probe_ns←now` | **True** |
| P2 | `minrtt_probing` AND NOT elapsed | none | **True** |
| P3 | NOT `minrtt_probing` AND `now - last_minrtt_probe_ns >= period_ns` | `cwnd_before_minrtt_probe`, `minrtt_probe_min_us←~0`, `minrtt_probing←1`, `probe_action_start_ns←now`, `dlv_rate_max` (decay) | **True** |
| P4 | NOT `minrtt_probing` AND NOT elapsed | none | **False** |

- Every **write** path (P1, P3) returns **True**.
- The only **False** path (P4) is reached before any assignment statement → private state
  semantically unchanged.
- (P2 returns True with no writes — consistent: the property is *writes ⟹ True*, not
  *True ⟹ writes*.)

`tp->snd_cwnd` (shared TCP state, re-injected from the trace at replay, not CoVegas private state)
is the only thing the probe paths touch outside `ca`, and only on True-returning paths.

The BPF version and the read-only source have the identical branch structure (verified): a single
trailing `return 0` reached only when NOT probing and the period has not elapsed, with no writes on
that path; `return 1` on both mutation paths and on the "probe still running" path.

```text
MINRTT_RETURN_ZERO_STATE_PRESERVATION = CONFIRMED
```

The scanner passes `dict(ca)` and, when `probe_ran == False`, proceeds with its **original** `ca`.
The model's `cong_avoid` uses `next_ca` (the returned copy). When `probe_ran == False` these are
semantically identical (P4), so the scanner's later gates read exactly the values the model would.
**The scanner is not rewritten to carry an equivalent object — it does not need to.**

## 1.2 Predicate-D scanner control-flow audit

Scanner (`user/scan_historical_a3.py`, Predicate-D loop) vs. the real `cong_avoid` path
(`user/covegas_model.py:523-542` → `handle_compete_mode:360-379`; identical logic in
`bpf/covegas_wrapper.bpf.c` / `~/cn-spike/covegas/src/covegas.bpf.c`):

| # | real control flow | scanner gate | match |
| --- | --- | --- | --- |
| 0 | `if (!tcp_is_cwnd_limited(sk)) return;` (recorder, before record) / `if not tcp_is_cwnd_limited(...): return out, ca` (model:524) | `if not cwnd_limited(e): not_cwnd_limited += 1; continue` | **yes** — same predicate, checked first |
| 1 | `if (handle_minrtt_probe(...)) return;` (model:533, uses `next_ca` after) | `probe_ran, _, _ = handle_minrtt_probe(dict(ca), ...); if probe_ran: continue` | **yes** — return-zero property (1.1) makes original `ca` == `next_ca` |
| 2 | `if (ca->mode == MODE_COMPETE) handle_compete_mode(...)` (model:538, `next_ca["mode"]`) | `if ca["mode"] != MODE_COMPETE: continue` | **yes** — only reached when `probe_ran == False` (P4), so `ca["mode"] == next_ca["mode"]` |
| 3 | `if (ca->dlv_rate_compete == 0) {` (handle_compete_mode:366) | `if ca["dlv_rate_compete"] != 0: continue` (rate-jump `else if` branch — identical in v3/v4, not Predicate D) | **yes** |
| 4 | `elapsed_jiffies = (u32)(tcp_jiffies32 - ca->compete_enter_jiffies); if (elapsed_jiffies >= (RATE_SETTLE_MS*HZ)/1000 && ca->dlv_rate_bps)` (:367-368) | `ej = u32(u32(jiffies_now) - ca["compete_enter_jiffies"]); if not (ej >= 250 and ca["dlv_rate_bps"]): continue` — evaluated under **both** `clock_jiffies32_before` and `_after` (`settle_gate_jiffies_bracket_flips`) | **yes** |
| 5 (guard) | `if (ca->dlv_rate_bps < (ca->dlv_rate_max * 3) / 4) { latch } else { revert; return }` (:369-373) | `guard_passes = ca["dlv_rate_bps"] < (ca["dlv_rate_max"] * 3) // 4` → pass = latch (v3==v4); fail = Predicate D | **yes** |

No earlier gate is omitted. Integer arithmetic matches (`u32`, `//`). `RATE_SETTLE_MS = 1000`,
`CONFIG_HZ = 250` → settle threshold `250` jiffies.

Time-origin investigation **not reopened**. Accepted result for the current traces:

> All nine current DELAY→COMPETE transitions fall in ON periods under the derived alignment
> interval (`Δ ∈ [≈ −0.65, +0.30] s`, upper rigorous / lower loose) and remain ON throughout a
> `Δ ∈ {−1 … +1} s` sensitivity sweep. No current Replay ABI-v2 trace contains the historical
> off-period trigger.

Historical-archive wording remains sensitivity-only (no rigorous cross-clock anchor).

## Phase 1 verdict

```text
MINRTT_RETURN_ZERO_STATE_PRESERVATION = CONFIRMED
SCANNER_CONTROL_FLOW_AUDIT            = no earlier gate omitted; integer arithmetic matches
A3_TRACK_BLOCKED                      = NO
```
