"""Phase 8 -- per-capture analysis for the final historical campaign.

Usage:  python3 data/audit_src/campaign_analyze_one.py <prefix>
        (prefix e.g. raw/covegas_campaign/run01)

Runs, in order:
  1. integrity validation (validate_run_v2)
  2. H scan  -- DELAY->COMPETE transitions, phase over the derived offset
                interval; H requires ROBUST_OFF
  3. D scan  -- source-derived Predicate-D control flow (both jiffies endpoints)
  4. same-episode H+D classification, and for every H episode the reason D
     did / did not occur

Appends a machine-readable record to data/historical_capture_campaign_results.json
and prints the per-attempt block. Offline; does not modify the trace.
"""
import sys
import json
import os

sys.path.insert(0, ".")
sys.path.insert(0, "user")

from user.ccr_trace_v2 import (parse_trace_v2, select_dominant_connection, validate_run_v2,
                               jiffies_clock_classification, CALLBACK_NAMES, MODE_DELAY, MODE_COMPETE)
from user.covegas_model import (pre_from_event, private_pre_from_event, handle_minrtt_probe,
                                tcp_is_cwnd_limited, u32, RATE_SETTLE_MS, CONFIG_HZ, MINRTT_PERIOD_MS,
                                CCR_CB_CONG_AVOID)

THR = (RATE_SETTLE_MS * CONFIG_HZ) // 1000
TOPOLOGY_BASE_RTT_S = 0.040
RESULTS = "data/historical_capture_campaign_results.json"


def read_ts(p):
    with open(p) as f:
        return float(f.read().strip())


def build_schedule(prefix):
    c1s = read_ts(prefix + "_cubic_rep1_start_ts.txt")
    ss = [(c1s, read_ts(prefix + "_cubic_rep1_stop_ts.txt"))]
    for i in (2, 3):
        ss.append((read_ts(prefix + "_cubic_rep%d_start_ts.txt" % i),
                   read_ts(prefix + "_cubic_rep%d_stop_ts.txt" % i)))
    return [(a - c1s, b - c1s) for a, b in ss], c1s


def phase(t, on):
    for a, b in on:
        if a <= t < b:
            return "ON"
    return "OFF"


def phase_over(lo, hi, on):
    pts = {lo, hi}
    for a, b in on:
        for edge in (a, b):
            if lo < edge < hi:
                pts.add(edge - 1e-9)
                pts.add(edge + 1e-9)
    ph = {phase(x, on) for x in pts}
    if ph == {"ON"}:
        return "ROBUST_ON"
    if ph == {"OFF"}:
        return "ROBUST_OFF"
    return "ALIGNMENT_LIMITED"


def analyze(prefix):
    trace, meta = prefix + ".ccr", prefix + ".meta.json"
    rec = {"prefix": prefix, "trace": trace}

    # 1. integrity
    try:
        v = validate_run_v2(trace, meta)
        rec["valid"] = bool(v["pass"])
        rec["drops"] = v["meta"]["drops"]
        rec["sequence_gaps"] = len(v["global_sequence"]["gaps"])
        rec["dominant_events"] = v["dominant_connection"]["n_events"]
        rec["dominant_fraction"] = round(v["dominant_connection"]["n_events"] / max(1, v["n_events"]), 5)
        rec["callback_counts"] = v["callback_counts"]
        rec["integrity_checks"] = v["checks"]
    except Exception as e:
        rec["valid"] = False
        rec["integrity_error"] = "%s: %s" % (type(e).__name__, e)
        rec["H_COUNT"] = rec["D_COUNT"] = rec["H_AND_D_SAME_EPISODE_COUNT"] = 0
        rec["outcome_class"] = "INVALID"
        return rec

    hdr, events = parse_trace_v2(trace)
    _, dom, other = select_dominant_connection(events)
    dom.sort(key=lambda e: e["seq"])
    t0 = dom[0]["ts_ns"]
    on, _ = build_schedule(prefix)
    offset_hi = (dom[0]["ts_ns"] - hdr.creation_ts_ns) / 1e9
    offset_lo = TOPOLOGY_BASE_RTT_S - max(0.0, (read_ts(prefix + "_cubic_rep1_stop_ts.txt")
                                                - read_ts(prefix + "_cubic_rep1_start_ts.txt")) - 20.0)
    rec["offset_interval_s"] = [round(offset_lo, 4), round(offset_hi, 4)]
    rec["on_periods_rel"] = [(round(a, 2), round(b, 2)) for a, b in on]

    def rel(e):
        return (e["ts_ns"] - t0) / 1e9

    # episodes + transitions
    episodes, cur = [], None
    d2c, c2d = [], []
    for e in dom:
        pm, qm = e["priv_pre_mode"], e["priv_post_mode"]
        if pm == qm:
            continue
        t = rel(e)
        pov = phase_over(t + offset_lo, t + offset_hi, on)
        r = {"seq": e["seq"], "t": round(t, 3), "phase_over_interval": pov,
             "dir": "D->C" if pm == MODE_DELAY else "C->D"}
        if pm == MODE_DELAY and qm == MODE_COMPETE:
            d2c.append(r)
            cur = {"entry_seq": e["seq"], "entry_t": round(t, 3), "entry_phase": pov, "exit_seq": None}
            episodes.append(cur)
        elif pm == MODE_COMPETE and qm == MODE_DELAY and cur is not None:
            cur["exit_seq"] = e["seq"]
            c2d.append(r)
            cur = None

    H_events = [r for r in d2c if r["phase_over_interval"] == "ROBUST_OFF"]
    rec["all_delay_to_compete"] = d2c
    rec["H_events"] = H_events
    rec["H_COUNT"] = len(H_events)

    def episode_for(seq):
        for ep in episodes:
            hi = ep["exit_seq"] if ep["exit_seq"] is not None else float("inf")
            if ep["entry_seq"] <= seq <= hi:
                return ep
        return None

    # D scan + per-episode diagnostic
    D_events = []
    episode_diag = {}
    for ep in episodes:
        episode_diag[ep["entry_seq"]] = {"entry_phase": ep["entry_phase"], "reason": None, "settle_seq": None}

    for e in dom:
        if e["callback_id"] != CCR_CB_CONG_AVOID:
            continue
        pre = pre_from_event(e)
        ca = private_pre_from_event(e)
        ep = episode_for(e["seq"])
        if not tcp_is_cwnd_limited(pre["snd_cwnd"], pre["snd_ssthresh"], pre["max_packets_out"], pre["is_cwnd_limited"]):
            continue
        probe = handle_minrtt_probe(dict(ca), pre, e["clock_ktime_ns_before"], e["clock_jiffies32_before"])[0]
        if ca["mode"] != MODE_COMPETE:
            continue
        if probe:
            if ep and episode_diag.get(ep["entry_seq"]) and episode_diag[ep["entry_seq"]]["reason"] is None:
                episode_diag[ep["entry_seq"]]["reason"] = "probe_active_through_settle_window"
            continue
        if ca["dlv_rate_compete"] != 0:
            continue
        ej = u32(u32(e["clock_jiffies32_before"]) - ca["compete_enter_jiffies"])
        eja = u32(u32(e["clock_jiffies32_after"]) - ca["compete_enter_jiffies"])
        if ca["dlv_rate_bps"] == 0:
            if ep and episode_diag.get(ep["entry_seq"]) and episode_diag[ep["entry_seq"]]["reason"] is None:
                episode_diag[ep["entry_seq"]]["reason"] = "dlv_rate_bps_zero"
            continue
        if not (ej >= THR):
            continue  # settle time not yet reached at this event
        # settle-latch guard is evaluated at this event
        flips = (ej >= THR) != (eja >= THR)
        guard_fail = not (ca["dlv_rate_bps"] < (ca["dlv_rate_max"] * 3) // 4)
        if ep and episode_diag.get(ep["entry_seq"]):
            episode_diag[ep["entry_seq"]]["settle_seq"] = e["seq"]
            episode_diag[ep["entry_seq"]]["ratio"] = round(ca["dlv_rate_bps"] / ca["dlv_rate_max"], 6)
            episode_diag[ep["entry_seq"]]["settle_gate_flips"] = flips
            episode_diag[ep["entry_seq"]]["reason"] = "guard_failed" if guard_fail else "guard_passed"
        if guard_fail:
            D_events.append({
                "seq": e["seq"], "t": round(rel(e), 3),
                "dlv_rate_bps": ca["dlv_rate_bps"], "dlv_rate_max": ca["dlv_rate_max"],
                "ratio": round(ca["dlv_rate_bps"] / ca["dlv_rate_max"], 6),
                "elapsed_jiffies_before": ej, "elapsed_jiffies_after": eja,
                "settle_gate_flips": flips,
                "episode_entry_seq": ep["entry_seq"] if ep else None,
                "episode_entry_phase": ep["entry_phase"] if ep else None,
            })

    rec["D_events"] = D_events
    rec["D_COUNT"] = len(D_events)
    rec["episode_diagnostic"] = episode_diag

    same = [d for d in D_events if d["episode_entry_phase"] == "ROBUST_OFF"]
    rec["H_AND_D_SAME_EPISODE_COUNT"] = len(same)
    rec["H_AND_D_SAME_EPISODE"] = same

    if rec["H_AND_D_SAME_EPISODE_COUNT"] > 0:
        rec["outcome_class"] = "H+D_SAME_EPISODE"
    elif rec["H_COUNT"] > 0 and rec["D_COUNT"] > 0:
        rec["outcome_class"] = "H_AND_D_DIFFERENT_EPISODES"
    elif rec["H_COUNT"] > 0:
        rec["outcome_class"] = "H_ONLY"
    elif rec["D_COUNT"] > 0:
        rec["outcome_class"] = "D_ONLY"
    else:
        rec["outcome_class"] = "NEITHER"
    return rec


def main():
    prefix = sys.argv[1]
    rec = analyze(prefix)
    allrecs = []
    if os.path.exists(RESULTS):
        allrecs = json.load(open(RESULTS))
    allrecs.append(rec)
    with open(RESULTS, "w") as f:
        json.dump(allrecs, f, indent=2, default=str)

    print("ATTEMPT PREFIX:            ", prefix)
    print("VALID:                    ", rec.get("valid"))
    print("DROPS:                    ", rec.get("drops"))
    print("SEQUENCE GAPS:            ", rec.get("sequence_gaps"))
    print("DOMINANT EVENTS:          ", rec.get("dominant_events"), "(fraction", rec.get("dominant_fraction"), ")")
    print("H COUNT:                  ", rec.get("H_COUNT"))
    print("D COUNT:                  ", rec.get("D_COUNT"))
    print("H+D SAME EPISODE COUNT:   ", rec.get("H_AND_D_SAME_EPISODE_COUNT"))
    print("OUTCOME CLASS:            ", rec.get("outcome_class"))
    for r in rec.get("all_delay_to_compete", []):
        print("   D->C seq=%s t=%s  %s" % (r["seq"], r["t"], r["phase_over_interval"]))
    for es, d in rec.get("episode_diagnostic", {}).items():
        print("   episode entry_seq=%s entry_phase=%s  D-reason=%s ratio=%s" %
              (es, d.get("entry_phase"), d.get("reason"), d.get("ratio")))
    stop = rec.get("H_AND_D_SAME_EPISODE_COUNT", 0) > 0
    print("STOP CAMPAIGN:            ", "YES -- H+D same episode acquired" if stop else "NO")
    sys.exit(3 if stop else (0 if rec.get("valid") else 1))


if __name__ == "__main__":
    main()
