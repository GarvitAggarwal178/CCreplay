"""Offline read-only scanner for the CoVegas A3 settle-latch case study.

Round-2 correction (see REPORT_EVIDENCE_RECONCILIATION_AND_A3_PREDICATE_AUDIT.md
and its follow-up): this version

  (1) applies the `tcp_is_cwnd_limited(...)` gate BEFORE `handle_minrtt_probe()`
      and mode dispatch, exactly as `user/covegas_model.py`'s cong_avoid path
      does (lines 523-542) and as `bpf/covegas_wrapper.bpf.c` does
      (`if (!tcp_is_cwnd_limited(sk)) return;` at the top of
      `ccr_covegas_cong_avoid`, before seq allocation / recording);
  (2) classifies workload phase with an explicit, artifact-derived offset
      bracket between the event clock (CLOCK_MONOTONIC, `bpf_ktime_get_ns`)
      and the cross-traffic schedule (CLOCK_REALTIME, `date +%s.%N`), and
      only asserts Predicate H when the phase is invariant over that bracket.

Predicate definitions and their source derivation:
`data/historical_a3_predicate_audit.md`.

  Predicate H -- historical off-period trigger:
    a DELAY->COMPETE mode transition on a cong_avoid event whose wall-clock
    time falls in a cross-traffic OFF period -- asserted only if robust to
    the event/schedule clock-offset uncertainty.

  Predicate D -- A3 implementation-divergence condition:
    a cong_avoid event where, on the recorded PRE state + recorded controller-
    visible clocks, the COMPLETE real control flow reaches
    handle_compete_mode's settle-latch guard
      (cwnd-limited, not probing, mode==COMPETE, dlv_rate_compete==0,
       settle time elapsed, dlv_rate_bps!=0)
    AND the v4 guard evaluates FALSE (dlv_rate_bps >= (dlv_rate_max*3)/4).
    On such an event the reconstructed v3 build (unconditional latch) and the
    fixed v4 build (revert_to_delay) diverge.

Does NOT modify any trace, run any replay diff, or run any network capture.
Reuses the validated model helpers (user/covegas_model.py).

Writes data/historical_a3_existing_trace_scan.md and a JSON sidecar.
"""
import sys
import json

sys.path.insert(0, ".")
sys.path.insert(0, "user")

from user.ccr_trace_v2 import (
    parse_trace_v2, select_dominant_connection, jiffies_clock_classification,
    CALLBACK_NAMES, MODE_DELAY, MODE_COMPETE,
)
from user.covegas_model import (
    pre_from_event, private_pre_from_event, handle_minrtt_probe, tcp_is_cwnd_limited,
    u32, RATE_SETTLE_MS, CONFIG_HZ, CCR_CB_CONG_AVOID,
)

SETTLE_THRESHOLD_JIFFIES = (RATE_SETTLE_MS * CONFIG_HZ) // 1000  # 250 at HZ=250

TRACES = [
    ("rep1", "raw/covegas_replay/primary/rep1"),
    ("rep2", "raw/covegas_replay/primary/rep2"),
    ("rep3", "raw/covegas_replay/primary/rep3"),
]

# Conservative lower edge of the event/schedule offset bracket. The rigorous
# upper edge is computed per-trace as (first_dominant_event.ts_ns -
# header.creation_ts_ns)/1e9  [recorder-start -> first-callback; the covegas
# process started AFTER the recorder, so the covegas-start -> first-callback
# offset is strictly smaller]. The lower edge is ~0 (the first `init`
# callback fires after connection setup, well after `date +%s.%N` captured
# cubic_rep1_start_ts); a small negative pad absorbs `date` exec time and
# monotonic-vs-realtime slew.
OFFSET_LOWER_PAD_S = -0.05


def read_ts(path):
    with open(path) as f:
        return float(f.read().strip())


def cwnd_limited(e):
    pre = pre_from_event(e)
    return tcp_is_cwnd_limited(pre["snd_cwnd"], pre["snd_ssthresh"],
                               pre["max_packets_out"], pre["is_cwnd_limited"])


def guard_passes(ca):
    """v4 A3 guard TRUE => latch (v3 and v4 agree). FALSE => v4 reverts, v3
    latches => Predicate D divergence."""
    return ca["dlv_rate_bps"] < (ca["dlv_rate_max"] * 3) // 4


def build_schedule(prefix):
    """Cross-traffic ON/OFF intervals, anchored to cubic_rep1_start_ts
    (`date +%s.%N`, captured in the driver script immediately after the
    covegas iperf3 client is backgrounded, before cross-traffic rep1)."""
    c1s = read_ts(f"{prefix}_cubic_rep1_start_ts.txt")
    starts_stops = [(c1s, read_ts(f"{prefix}_cubic_rep1_stop_ts.txt"))]
    for i in (2, 3):
        starts_stops.append((read_ts(f"{prefix}_cubic_rep{i}_start_ts.txt"),
                             read_ts(f"{prefix}_cubic_rep{i}_stop_ts.txt")))
    on = [(a - c1s, b - c1s) for a, b in starts_stops]
    return on  # relative to cubic_rep1_start_ts


def phase_bracketed(sched_pos_lo, sched_pos_hi, on_periods):
    """Return 'ON' / 'OFF' if the whole [lo,hi] window is in one phase,
    else 'ALIGNMENT-LIMITED'."""
    def phase(t):
        for a, b in on_periods:
            if a <= t < b:
                return "ON"
        return "OFF"
    plo, phi = phase(sched_pos_lo), phase(sched_pos_hi)
    # also sample the interior boundary points that fall inside [lo,hi]
    pts = {sched_pos_lo, sched_pos_hi}
    for a, b in on_periods:
        for edge in (a, b):
            if sched_pos_lo < edge < sched_pos_hi:
                pts.add(edge - 1e-9)
                pts.add(edge + 1e-9)
    phases = {phase(t) for t in pts}
    if phases == {"ON"}:
        return "ON"
    if phases == {"OFF"}:
        return "OFF"
    return "ALIGNMENT-LIMITED"


def nearest_boundary_distance(t, on_periods):
    edges = [0.0]
    for a, b in on_periods:
        edges += [a, b]
    return min(abs(t - e) for e in edges)


def scan_trace(label, prefix):
    trace = f"{prefix}.ccr"
    hdr, events = parse_trace_v2(trace)
    _, dom, other = select_dominant_connection(events)
    dom.sort(key=lambda e: e["seq"])
    t0 = dom[0]["ts_ns"]

    # --- offset bracket (event clock vs schedule clock) ---
    offset_hi = (dom[0]["ts_ns"] - hdr.creation_ts_ns) / 1e9   # rigorous upper bound
    offset_lo = OFFSET_LOWER_PAD_S
    on_periods = build_schedule(prefix)

    def rel_s(e):
        return (e["ts_ns"] - t0) / 1e9

    n_cong_avoid = sum(1 for e in dom if e["callback_id"] == CCR_CB_CONG_AVOID)

    # --- mode transitions (Predicate H input) ---
    delay_to_compete, compete_to_delay = [], []
    for e in dom:
        pre_m, post_m = e["priv_pre_mode"], e["priv_post_mode"]
        if pre_m == post_m:
            continue
        t = rel_s(e)
        lo, hi = t + offset_lo, t + offset_hi
        rec = {
            "seq": e["seq"], "rel_s": t,
            "sched_lo": lo, "sched_hi": hi,
            "phase_bracketed": phase_bracketed(lo, hi, on_periods),
            "nearest_boundary_s": nearest_boundary_distance(t + (offset_lo + offset_hi) / 2, on_periods),
            "callback": CALLBACK_NAMES.get(e["callback_id"]),
            "pre_mode": pre_m, "post_mode": post_m,
        }
        (delay_to_compete if pre_m == MODE_DELAY else compete_to_delay).append(rec)

    predicate_H_events = [r for r in delay_to_compete if r["phase_bracketed"] == "OFF"]
    alignment_limited_dtoc = [r for r in delay_to_compete if r["phase_bracketed"] == "ALIGNMENT-LIMITED"]

    # --- COMPETE episodes ---
    episodes, cur = [], None
    for e in dom:
        pre_m, post_m = e["priv_pre_mode"], e["priv_post_mode"]
        if pre_m == MODE_DELAY and post_m == MODE_COMPETE:
            cur = {"entry_seq": e["seq"], "entry_rel_s": rel_s(e), "exit_seq": None}
            episodes.append(cur)
        elif pre_m == MODE_COMPETE and post_m == MODE_DELAY and cur is not None:
            cur["exit_seq"] = e["seq"]
            cur = None

    def episode_for(seq):
        for ep in episodes:
            hi = ep["exit_seq"] if ep["exit_seq"] is not None else float("inf")
            if ep["entry_seq"] <= seq <= hi:
                return ep
        return None

    # --- Predicate D scan over cong_avoid events (CORRECTED control flow) ---
    counts = dict(
        cong_avoid=n_cong_avoid,
        cwnd_limited_pass=0,
        not_cwnd_limited=0,
        minrtt_probe_skipped=0,       # cwnd-limited AND handle_minrtt_probe()==0
        compete_dispatch=0,           # ...AND mode==COMPETE
        dlv_rate_compete_zero_block=0,  # ...AND dlv_rate_compete==0
        settle_time_gate_reached=0,   # ...AND elapsed>=250 AND dlv_rate_bps!=0  (guard evaluated)
        guard_passes=0,
        guard_failures=0,             # Predicate D
    )
    guard_failing = []
    settle_gate_jiffies_ambiguous = 0

    for e in dom:
        if e["callback_id"] != CCR_CB_CONG_AVOID:
            continue

        # GATE 0 (NEW): cwnd-limited, exactly as the model's cong_avoid path
        # checks BEFORE handle_minrtt_probe / dispatch.
        if not cwnd_limited(e):
            counts["not_cwnd_limited"] += 1
            continue
        counts["cwnd_limited_pass"] += 1

        ca = private_pre_from_event(e)
        pre = pre_from_event(e)
        ktime_now = e["clock_ktime_ns_before"]
        jiffies_now = e["clock_jiffies32_before"]

        probe_ran, _, _ = handle_minrtt_probe(dict(ca), pre, ktime_now, jiffies_now)
        if probe_ran:
            continue
        counts["minrtt_probe_skipped"] += 1

        if ca["mode"] != MODE_COMPETE:
            continue
        counts["compete_dispatch"] += 1

        if ca["dlv_rate_compete"] != 0:
            continue   # rate-jump revert branch: identical in v3 and v4
        counts["dlv_rate_compete_zero_block"] += 1

        ej = u32(u32(jiffies_now) - ca["compete_enter_jiffies"])
        if not (ej >= SETTLE_THRESHOLD_JIFFIES and ca["dlv_rate_bps"]):
            continue
        counts["settle_time_gate_reached"] += 1

        # jiffies bracket sensitivity of the settle-time gate
        ej_after = u32(u32(e["clock_jiffies32_after"]) - ca["compete_enter_jiffies"])
        gate_lo = ej >= SETTLE_THRESHOLD_JIFFIES
        gate_hi = ej_after >= SETTLE_THRESHOLD_JIFFIES
        jamb = jiffies_clock_classification(e) == "CLOCK_AMBIGUOUS"
        gate_flips = gate_lo != gate_hi
        if gate_flips:
            settle_gate_jiffies_ambiguous += 1

        if guard_passes(ca):
            counts["guard_passes"] += 1
            continue

        counts["guard_failures"] += 1
        ep = episode_for(e["seq"])
        t = rel_s(e)
        guard_failing.append({
            "trace": trace, "seq": e["seq"], "rel_s": t,
            "dlv_rate_bps": ca["dlv_rate_bps"], "dlv_rate_max": ca["dlv_rate_max"],
            "guard_threshold_3_4_max": (ca["dlv_rate_max"] * 3) // 4,
            "elapsed_jiffies_before": ej, "elapsed_jiffies_after": ej_after,
            "settle_threshold_jiffies": SETTLE_THRESHOLD_JIFFIES,
            "jiffies_ambiguous": jamb, "settle_gate_flips_across_bracket": gate_flips,
            "episode_entry_seq": ep["entry_seq"] if ep else None,
        })

    return {
        "trace": trace, "label": label,
        "offset_bracket_s": [round(offset_lo, 4), round(offset_hi, 4)],
        "offset_hi_source": "(first_dominant_event.ts_ns - header.creation_ts_ns)/1e9 -- recorder-start to first-callback, monotonic; rigorous upper bound on the covegas-start -> first-callback offset",
        "schedule_anchor": "cubic_rep1_start_ts.txt (date +%s.%N)",
        "on_periods_rel_cubic_rep1_start": [(round(a, 3), round(b, 3)) for a, b in on_periods],
        "n_dominant_events": len(dom), "n_other_events": len(other),
        "counts": counts,
        "settle_gate_jiffies_bracket_flips": settle_gate_jiffies_ambiguous,
        "delay_to_compete_transitions": delay_to_compete,
        "compete_to_delay_transitions": compete_to_delay,
        "predicate_H_events": predicate_H_events,
        "alignment_limited_delay_to_compete": alignment_limited_dtoc,
        "compete_episodes": episodes,
        "guard_failing_evaluations": guard_failing,
        "PREDICATE_H_PRESENT": len(predicate_H_events) > 0,
        "PREDICATE_H_ALIGNMENT_LIMITED": len(alignment_limited_dtoc) > 0,
        "PREDICATE_D_PRESENT": len(guard_failing) > 0,
        "H_AND_D_IN_SAME_EPISODE": any(
            g["episode_entry_seq"] is not None and
            any(h["seq"] == g["episode_entry_seq"] for h in predicate_H_events)
            for g in guard_failing),
        "ALL_SCANNED_D_SETTLE_GATE_EXACT": settle_gate_jiffies_ambiguous == 0,
    }


# Counts from the round-1 (pre-correction) scanner, recorded so the
# correction is explicit rather than silent.
ROUND1_COUNTS = {
    "rep1": {"compete_dispatch": 5733, "settle_block_entered": 312,
             "settle_time_gate_reached": 3, "guard_passes": 3, "guard_failures": 0},
    "rep2": {"compete_dispatch": 5441, "settle_block_entered": 319,
             "settle_time_gate_reached": 3, "guard_passes": 3, "guard_failures": 0},
    "rep3": {"compete_dispatch": 5716, "settle_block_entered": 300,
             "settle_time_gate_reached": 3, "guard_passes": 3, "guard_failures": 0},
}


def main():
    results = [scan_trace(label, prefix) for label, prefix in TRACES]
    with open("data/historical_a3_existing_trace_scan.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    L = []
    L.append("# CoVegas A3 Existing-Trace Scan (Predicate H vs Predicate D) — round 2 (corrected)\n")
    L.append("Generated by `user/scan_historical_a3.py` (offline, read-only — no trace modified, "
             "no replay diff run, no network capture). Predicate definitions and source derivation: "
             "`data/historical_a3_predicate_audit.md`.\n")
    L.append("## What changed from round 1\n")
    L.append("1. **cwnd-limited gate added.** The scanner now applies `tcp_is_cwnd_limited(...)` "
             "BEFORE `handle_minrtt_probe()` and mode dispatch, matching `user/covegas_model.py` "
             "cong_avoid (lines 523–524) and `bpf/covegas_wrapper.bpf.c` "
             "(`if (!tcp_is_cwnd_limited(sk)) return;`). Round 1 omitted this gate and therefore "
             "inspected an over-inclusive event set. Required ABI-v2 inputs for the gate: "
             "`pre_snd_cwnd`, `pre_snd_ssthresh`, `pre_max_packets_out`, `pre_is_cwnd_limited`.\n")
    L.append("2. **Explicit time-alignment bracket.** Phase is now classified against an "
             "artifact-derived offset bracket between the event clock (`CLOCK_MONOTONIC`, "
             "`bpf_ktime_get_ns`) and the cross-traffic schedule (`CLOCK_REALTIME`, `date +%s.%N`); "
             "Predicate H is asserted only when the phase is invariant over that bracket. Schedule "
             "anchor changed from the 1-second-quantized iperf3 `timesecs` to "
             "`cubic_rep1_start_ts.txt`.\n")

    L.append("\n## Before vs after (control-flow counts)\n")
    L.append("| trace | metric | round 1 | round 2 (corrected) |")
    L.append("| --- | --- | ---: | ---: |")
    for r in results:
        r1 = ROUND1_COUNTS[r["label"]]
        c = r["counts"]
        L.append(f"| {r['label']} | COMPETE dispatch events | {r1['compete_dispatch']} | {c['compete_dispatch']} |")
        L.append(f"| {r['label']} | settle block entered (dlv_rate_compete==0) | {r1['settle_block_entered']} | {c['dlv_rate_compete_zero_block']} |")
        L.append(f"| {r['label']} | settle guard evaluated | {r1['settle_time_gate_reached']} | {c['settle_time_gate_reached']} |")
        L.append(f"| {r['label']} | guard passes | {r1['guard_passes']} | {c['guard_passes']} |")
        L.append(f"| {r['label']} | guard failures / Predicate D | {r1['guard_failures']} | {c['guard_failures']} |")
    L.append("")

    L.append("## Per-trace detail\n")
    for r in results:
        c = r["counts"]
        L.append(f"### {r['label']} — `{r['trace']}`\n")
        L.append(f"- dominant-connection events: {r['n_dominant_events']}  (other: {r['n_other_events']})")
        L.append(f"- event/schedule offset bracket: **{r['offset_bracket_s']} s**; upper edge = "
                 f"{r['offset_hi_source']}")
        L.append(f"- schedule anchor: {r['schedule_anchor']}; ON periods (s, rel anchor): "
                 f"`{r['on_periods_rel_cubic_rep1_start']}`")
        L.append("")
        L.append("Full cong_avoid control-flow funnel (round 2):")
        L.append("```text")
        for k in ("cong_avoid", "not_cwnd_limited", "cwnd_limited_pass", "minrtt_probe_skipped",
                  "compete_dispatch", "dlv_rate_compete_zero_block", "settle_time_gate_reached",
                  "guard_passes", "guard_failures"):
            L.append(f"  {k:32s} {c[k]}")
        L.append(f"  settle_gate_jiffies_bracket_flips {r['settle_gate_jiffies_bracket_flips']}")
        L.append("```")
        L.append("")
        L.append("DELAY→COMPETE transitions (Predicate H candidates):\n")
        L.append("| seq | t_event (s) | sched window [lo,hi] (s) | phase (bracketed) | nearest boundary (s) |")
        L.append("| ---: | ---: | --- | --- | ---: |")
        for tr in r["delay_to_compete_transitions"]:
            L.append(f"| {tr['seq']} | {tr['rel_s']:.2f} | [{tr['sched_lo']:.2f}, {tr['sched_hi']:.2f}] | "
                     f"{tr['phase_bracketed']} | {tr['nearest_boundary_s']:.2f} |")
        L.append("")
        if r["guard_failing_evaluations"]:
            L.append("Predicate D events (v4 guard FALSE):\n")
            L.append("| seq | t (s) | dlv_rate_bps | (3/4)·dlv_rate_max | elapsed_jiffies before/after | "
                     "settle-gate flips across bracket |")
            L.append("| ---: | ---: | ---: | ---: | --- | --- |")
            for g in r["guard_failing_evaluations"]:
                L.append(f"| {g['seq']} | {g['rel_s']:.2f} | {g['dlv_rate_bps']} | "
                         f"{g['guard_threshold_3_4_max']} | {g['elapsed_jiffies_before']}/"
                         f"{g['elapsed_jiffies_after']} | {g['settle_gate_flips_across_bracket']} |")
        else:
            L.append("Predicate D events: **none** — every settle-latch guard evaluation "
                     f"({c['settle_time_gate_reached']} total, one per COMPETE episode) **passed** "
                     "(`dlv_rate_bps < (dlv_rate_max*3)/4`); reconstructed-v3 and v4 produce the "
                     "identical transition.")
        L.append("")
        L.append("```text")
        L.append(f"PREDICATE_H_PRESENT:            {'YES' if r['PREDICATE_H_PRESENT'] else 'NO'}")
        L.append(f"PREDICATE_H_ALIGNMENT_LIMITED:  {'YES' if r['PREDICATE_H_ALIGNMENT_LIMITED'] else 'NO'}")
        L.append(f"PREDICATE_D_PRESENT:            {'YES' if r['PREDICATE_D_PRESENT'] else 'NO'}")
        L.append(f"H_AND_D_IN_SAME_EPISODE:        {'YES' if r['H_AND_D_IN_SAME_EPISODE'] else 'NO'}")
        L.append(f"ALL_SCANNED_D_SETTLE_GATE_EXACT: {'YES' if r['ALL_SCANNED_D_SETTLE_GATE_EXACT'] else 'NO'}")
        L.append("```")
        L.append("")

    anyH = any(r["PREDICATE_H_PRESENT"] for r in results)
    anyD = any(r["PREDICATE_D_PRESENT"] for r in results)
    anyAL = any(r["PREDICATE_H_ALIGNMENT_LIMITED"] for r in results)
    anyFlip = any(r["settle_gate_jiffies_bracket_flips"] for r in results)
    L.append("## Aggregate\n")
    L.append("```text")
    L.append(f"ANY PREDICATE_H_PRESENT:              {'YES' if anyH else 'NO'}")
    L.append(f"ANY PREDICATE_H_ALIGNMENT_LIMITED:    {'YES' if anyAL else 'NO'}")
    L.append(f"ANY PREDICATE_D_PRESENT:              {'YES' if anyD else 'NO'}")
    L.append(f"ANY SETTLE-GATE JIFFIES BRACKET FLIP: {'YES' if anyFlip else 'NO'}")
    L.append(f"ALL SCANNED D CLASSIFICATIONS EXACT:  {'YES' if not anyFlip else 'NO'}")
    L.append("```")
    L.append("")

    with open("data/historical_a3_existing_trace_scan.md", "w") as f:
        f.write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
