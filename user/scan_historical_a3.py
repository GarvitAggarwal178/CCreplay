"""Offline read-only scanner for the CoVegas A3 settle-latch case study.

Scans the three existing CoVegas primary traces (raw/covegas_replay/primary/
rep{1,2,3}.ccr) for two DISTINCT predicates, defined and derived from source
in data/historical_a3_predicate_audit.md:

  Predicate H -- historical off-period trigger:
    a DELAY->COMPETE mode transition on a cong_avoid event whose wall-clock
    time falls in a cross-traffic OFF period.

  Predicate D -- A3 implementation-divergence condition:
    a cong_avoid event where, on the recorded PRE state + recorded controller-
    visible clocks, control reaches handle_compete_mode's settle-latch guard
    (mode==COMPETE, dlv_rate_compete==0, settle time elapsed, dlv_rate_bps!=0),
    AND the v4 guard evaluates FALSE (dlv_rate_bps >= (dlv_rate_max*3)/4).
    On such an event the reconstructed v3 build (unconditional latch) and the
    fixed v4 build (revert_to_delay) diverge.

This scanner does NOT modify any trace, does NOT run a replay diff, and does
NOT run any network capture. It re-uses the validated model helpers
(user/covegas_model.py) and the phase mapping from
data/audit_src/check_historical_trigger.py so the predicate evaluation is
identical to production replay semantics.

Writes data/historical_a3_existing_trace_scan.md and a JSON sidecar.
"""
import sys
import json

sys.path.insert(0, ".")
sys.path.insert(0, "user")
sys.path.insert(0, "data/audit_src")

from user.ccr_trace_v2 import (
    parse_trace_v2, select_dominant_connection, jiffies_clock_classification,
    CALLBACK_NAMES, MODE_DELAY, MODE_COMPETE,
)
from user.covegas_model import (
    pre_from_event, private_pre_from_event, handle_minrtt_probe,
    u32, RATE_SETTLE_MS, CONFIG_HZ, CCR_CB_CONG_AVOID,
)
from check_historical_trigger import load_on_periods, phase_at

SETTLE_THRESHOLD_JIFFIES = (RATE_SETTLE_MS * CONFIG_HZ) // 1000  # 250 at HZ=250

TRACES = [
    ("rep1", "raw/covegas_replay/primary/rep1"),
    ("rep2", "raw/covegas_replay/primary/rep2"),
    ("rep3", "raw/covegas_replay/primary/rep3"),
]


def guard_passes(ca):
    """v4 A3 guard: True => latch (v3 and v4 agree). False => v4 reverts, v3
    latches => Predicate D divergence."""
    return ca["dlv_rate_bps"] < (ca["dlv_rate_max"] * 3) // 4


def elapsed_jiffies(jiffies_now, ca):
    return u32(u32(jiffies_now) - ca["compete_enter_jiffies"])


def scan_trace(label, prefix):
    trace = f"{prefix}.ccr"
    on_periods_rel = load_on_periods(prefix)

    _, events = parse_trace_v2(trace)
    _, dom, _ = select_dominant_connection(events)
    dom.sort(key=lambda e: e["seq"])
    t0 = dom[0]["ts_ns"]

    n_cong_avoid = sum(1 for e in dom if e["callback_id"] == CCR_CB_CONG_AVOID)

    # --- mode transitions (Predicate H) ---
    delay_to_compete = []
    compete_to_delay = []
    for e in dom:
        pre_m, post_m = e["priv_pre_mode"], e["priv_post_mode"]
        if pre_m == post_m:
            continue
        rel_s = (e["ts_ns"] - t0) / 1e9
        rec = {
            "seq": e["seq"], "rel_s": rel_s,
            "phase": phase_at(rel_s, on_periods_rel),
            "callback": CALLBACK_NAMES.get(e["callback_id"]),
            "pre_mode": pre_m, "post_mode": post_m,
        }
        if pre_m == MODE_DELAY and post_m == MODE_COMPETE:
            delay_to_compete.append(rec)
        elif pre_m == MODE_COMPETE and post_m == MODE_DELAY:
            compete_to_delay.append(rec)

    predicate_H_events = [r for r in delay_to_compete if r["phase"] == "OFF"]

    # --- COMPETE episodes: (entry_seq, entry_rel_s, entry_phase, exit_seq_or_None) ---
    episodes = []
    cur = None
    for e in dom:
        pre_m, post_m = e["priv_pre_mode"], e["priv_post_mode"]
        if pre_m == MODE_DELAY and post_m == MODE_COMPETE:
            rel_s = (e["ts_ns"] - t0) / 1e9
            cur = {"entry_seq": e["seq"], "entry_rel_s": rel_s,
                   "entry_phase": phase_at(rel_s, on_periods_rel), "exit_seq": None}
            episodes.append(cur)
        elif pre_m == MODE_COMPETE and post_m == MODE_DELAY and cur is not None:
            cur["exit_seq"] = e["seq"]
            cur = None

    def episode_for(seq):
        for ep in episodes:
            lo = ep["entry_seq"]
            hi = ep["exit_seq"] if ep["exit_seq"] is not None else float("inf")
            if lo <= seq <= hi:
                return ep
        return None

    # --- Predicate D scan over cong_avoid events ---
    settle_latch_reached = 0     # guard actually evaluated this event
    guard_passing = 0
    guard_failing = []          # Predicate D
    compete_dispatch = 0        # reached handle_compete_mode at all
    settle_block_entered = 0    # mode==COMPETE and dlv_rate_compete==0

    for e in dom:
        if e["callback_id"] != CCR_CB_CONG_AVOID:
            continue
        ca = private_pre_from_event(e)
        pre = pre_from_event(e)
        ktime_now = e["clock_ktime_ns_before"]
        jiffies_now = e["clock_jiffies32_before"]

        probe_ran, _, _ = handle_minrtt_probe(dict(ca), pre, ktime_now, jiffies_now)
        if probe_ran:
            continue
        if ca["mode"] != MODE_COMPETE:
            continue
        compete_dispatch += 1
        if ca["dlv_rate_compete"] != 0:
            # rate-jump revert branch: identical in v3 and v4, not Predicate D
            continue
        settle_block_entered += 1
        ej = elapsed_jiffies(jiffies_now, ca)
        if not (ej >= SETTLE_THRESHOLD_JIFFIES and ca["dlv_rate_bps"]):
            continue
        settle_latch_reached += 1

        # jiffies-ambiguity sensitivity on the settle-time gate
        jamb = jiffies_clock_classification(e) == "CLOCK_AMBIGUOUS"
        ej_after = u32(u32(e["clock_jiffies32_after"]) - ca["compete_enter_jiffies"])
        gate_flips_under_after = (ej >= SETTLE_THRESHOLD_JIFFIES) != (ej_after >= SETTLE_THRESHOLD_JIFFIES)

        if guard_passes(ca):
            guard_passing += 1
            continue

        # Predicate D
        ep = episode_for(e["seq"])
        rel_s = (e["ts_ns"] - t0) / 1e9
        guard_failing.append({
            "trace": trace, "seq": e["seq"],
            "rel_s": rel_s, "phase": phase_at(rel_s, on_periods_rel),
            "pre_mode": ca["mode"],
            "dlv_rate_bps": ca["dlv_rate_bps"],
            "dlv_rate_max": ca["dlv_rate_max"],
            "dlv_rate_compete_pre": ca["dlv_rate_compete"],
            "guard_threshold_3_4_max": (ca["dlv_rate_max"] * 3) // 4,
            "elapsed_jiffies": ej,
            "settle_threshold_jiffies": SETTLE_THRESHOLD_JIFFIES,
            "jiffies_ambiguous": jamb,
            "settle_gate_flips_under_after_snapshot": gate_flips_under_after,
            "episode_entry_seq": ep["entry_seq"] if ep else None,
            "episode_entry_phase": ep["entry_phase"] if ep else None,
            "episode_entry_is_predicate_H": bool(ep and ep["entry_phase"] == "OFF"),
        })

    predicate_D_present = len(guard_failing) > 0
    predicate_H_present = len(predicate_H_events) > 0
    h_and_d_same_episode = any(g["episode_entry_is_predicate_H"] for g in guard_failing)

    return {
        "trace": trace, "label": label,
        "on_periods_rel": [(round(a, 2), round(b, 2)) for a, b in on_periods_rel],
        "total_dominant_events": len(dom),
        "total_cong_avoid": n_cong_avoid,
        "delay_to_compete_transitions": delay_to_compete,
        "compete_to_delay_transitions": compete_to_delay,
        "predicate_H_events": predicate_H_events,
        "compete_episodes": episodes,
        "compete_dispatch_events": compete_dispatch,
        "settle_block_entered": settle_block_entered,
        "settle_latch_evaluations_reached": settle_latch_reached,
        "guard_passing_evaluations": guard_passing,
        "guard_failing_evaluations": guard_failing,
        "PREDICATE_H_PRESENT": predicate_H_present,
        "PREDICATE_D_PRESENT": predicate_D_present,
        "H_AND_D_IN_SAME_EPISODE": h_and_d_same_episode,
    }


def main():
    results = [scan_trace(label, prefix) for label, prefix in TRACES]

    with open("data/historical_a3_existing_trace_scan.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    lines = []
    lines.append("# CoVegas A3 Existing-Trace Scan (Predicate H vs Predicate D)\n")
    lines.append("Generated by `user/scan_historical_a3.py` (offline, read-only — no trace modified, "
                 "no replay diff run, no network capture). Predicate definitions and their source "
                 "derivation: `data/historical_a3_predicate_audit.md`.\n")
    lines.append(f"Settle-time threshold: `(RATE_SETTLE_MS * CONFIG_HZ) / 1000` = "
                 f"`(1000 * {CONFIG_HZ}) / 1000` = **{SETTLE_THRESHOLD_JIFFIES} jiffies**.\n")

    lines.append("## Per-trace summary\n")
    lines.append("| trace | dom events | cong_avoid | DELAY→COMPETE | …during OFF (Pred H) | "
                 "COMPETE→DELAY | settle-latch evals | guard-pass | guard-fail (Pred D) |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in results:
        lines.append(
            f"| {r['label']} | {r['total_dominant_events']} | {r['total_cong_avoid']} | "
            f"{len(r['delay_to_compete_transitions'])} | {len(r['predicate_H_events'])} | "
            f"{len(r['compete_to_delay_transitions'])} | {r['settle_latch_evaluations_reached']} | "
            f"{r['guard_passing_evaluations']} | {len(r['guard_failing_evaluations'])} |")
    lines.append("")

    for r in results:
        lines.append(f"## {r['label']} — `{r['trace']}`\n")
        lines.append(f"- Cross-traffic ON periods (s, relative to covegas first event): "
                     f"`{r['on_periods_rel']}`")
        lines.append(f"- COMPETE dispatch events (mode==COMPETE, not probing): "
                     f"{r['compete_dispatch_events']}")
        lines.append(f"- Settle-latch block entered (…and dlv_rate_compete==0): "
                     f"{r['settle_block_entered']}")
        lines.append(f"- Settle-latch guard actually evaluated (…and settle time elapsed and "
                     f"dlv_rate_bps!=0): {r['settle_latch_evaluations_reached']}")
        lines.append("")
        lines.append("### All DELAY→COMPETE / COMPETE→DELAY transitions\n")
        lines.append("| seq | t (s) | phase | direction | callback |")
        lines.append("| ---: | ---: | --- | --- | --- |")
        for t in sorted(r["delay_to_compete_transitions"] + r["compete_to_delay_transitions"],
                        key=lambda x: x["seq"]):
            d = "DELAY→COMPETE" if t["pre_mode"] == MODE_DELAY else "COMPETE→DELAY"
            lines.append(f"| {t['seq']} | {t['rel_s']:.2f} | {t['phase']} | {d} | {t['callback']} |")
        lines.append("")
        lines.append("### COMPETE episodes\n")
        lines.append("| entry seq | entry t (s) | entry phase | exit seq |")
        lines.append("| ---: | ---: | --- | ---: |")
        for ep in r["compete_episodes"]:
            lines.append(f"| {ep['entry_seq']} | {ep['entry_rel_s']:.2f} | {ep['entry_phase']} | "
                         f"{ep['exit_seq'] if ep['exit_seq'] is not None else '(none — ran to end)'} |")
        lines.append("")
        if r["guard_failing_evaluations"]:
            lines.append("### Predicate D events (v4 guard failed → v3/v4 diverge)\n")
            lines.append("| seq | t (s) | phase | dlv_rate_bps | (3/4)·dlv_rate_max | elapsed jiffies | "
                         "jiffies-ambiguous | gate flips under _after | episode entry seq | "
                         "episode entry phase | H+D same episode |")
            lines.append("| ---: | ---: | --- | ---: | ---: | ---: | --- | --- | ---: | --- | --- |")
            for g in r["guard_failing_evaluations"]:
                lines.append(
                    f"| {g['seq']} | {g['rel_s']:.2f} | {g['phase']} | {g['dlv_rate_bps']} | "
                    f"{g['guard_threshold_3_4_max']} | {g['elapsed_jiffies']} | "
                    f"{g['jiffies_ambiguous']} | {g['settle_gate_flips_under_after_snapshot']} | "
                    f"{g['episode_entry_seq']} | {g['episode_entry_phase']} | "
                    f"{g['episode_entry_is_predicate_H']} |")
        else:
            lines.append("### Predicate D events\n")
            lines.append("None — every settle-latch guard evaluation in this trace **passed** "
                         "(`dlv_rate_bps < (dlv_rate_max*3)/4`), so the reconstructed v3 "
                         "unconditional latch and the fixed v4 guarded latch produce the identical "
                         "transition. No v3-vs-v4 divergence point exists in this trace.")
        lines.append("")
        lines.append("### Classifications\n")
        lines.append(f"```text")
        lines.append(f"PREDICATE_H_PRESENT: {'YES' if r['PREDICATE_H_PRESENT'] else 'NO'}")
        lines.append(f"PREDICATE_D_PRESENT: {'YES' if r['PREDICATE_D_PRESENT'] else 'NO'}")
        lines.append(f"H_AND_D_IN_SAME_EPISODE: {'YES' if r['H_AND_D_IN_SAME_EPISODE'] else 'NO'}")
        lines.append(f"```")
        lines.append("")

    # aggregate
    anyH = any(r["PREDICATE_H_PRESENT"] for r in results)
    anyD = any(r["PREDICATE_D_PRESENT"] for r in results)
    anyBoth = any(r["H_AND_D_IN_SAME_EPISODE"] for r in results)
    lines.append("## Aggregate across all three traces\n")
    lines.append("```text")
    lines.append(f"ANY PREDICATE_H_PRESENT: {'YES' if anyH else 'NO'}")
    lines.append(f"ANY PREDICATE_D_PRESENT: {'YES' if anyD else 'NO'}")
    lines.append(f"ANY H_AND_D_IN_SAME_EPISODE: {'YES' if anyBoth else 'NO'}")
    lines.append("```")
    lines.append("")

    with open("data/historical_a3_existing_trace_scan.md", "w") as f:
        f.write("\n".join(lines))

    print("\n".join(lines))


if __name__ == "__main__":
    main()
