"""List every settle-latch guard evaluation in the three CoVegas primary traces
(the events used for Phase 2/4/5 of docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md).
Offline, read-only.
"""
import sys
import json
sys.path.insert(0, ".")
sys.path.insert(0, "user")
from user.ccr_trace_v2 import parse_trace_v2, select_dominant_connection, MODE_COMPETE, CCR_CB_CONG_AVOID
from user.covegas_model import (pre_from_event, private_pre_from_event, handle_minrtt_probe,
                                tcp_is_cwnd_limited, u32, RATE_SETTLE_MS, CONFIG_HZ, ALL_PRIVATE_FIELDS)

THR = (RATE_SETTLE_MS * CONFIG_HZ) // 1000
rows = []
for rep in ("rep1", "rep2", "rep3"):
    p = "raw/covegas_replay/primary/" + rep
    hdr, ev = parse_trace_v2(p + ".ccr")
    _, dom, _ = select_dominant_connection(ev)
    dom.sort(key=lambda e: e["seq"])
    t0 = dom[0]["ts_ns"]
    for e in dom:
        if e["callback_id"] != CCR_CB_CONG_AVOID:
            continue
        pre = pre_from_event(e)
        ca = private_pre_from_event(e)
        if not tcp_is_cwnd_limited(pre["snd_cwnd"], pre["snd_ssthresh"], pre["max_packets_out"], pre["is_cwnd_limited"]):
            continue
        if handle_minrtt_probe(dict(ca), pre, e["clock_ktime_ns_before"], e["clock_jiffies32_before"])[0]:
            continue
        if ca["mode"] != MODE_COMPETE:
            continue
        if ca["dlv_rate_compete"] != 0:
            continue
        ej = u32(u32(e["clock_jiffies32_before"]) - ca["compete_enter_jiffies"])
        eja = u32(u32(e["clock_jiffies32_after"]) - ca["compete_enter_jiffies"])
        if not (ej >= THR and ca["dlv_rate_bps"]):
            continue
        bps = ca["dlv_rate_bps"]
        mx = ca["dlv_rate_max"]
        rows.append({
            "rep": rep, "seq": e["seq"],
            "rel_s": round((e["ts_ns"] - t0) / 1e9, 3),
            "dlv_rate_bps": bps, "dlv_rate_max": mx,
            "ratio": round(bps / mx, 6),
            "three_quarter_max": (mx * 3) // 4,
            "guard_passes": bps < (mx * 3) // 4,
            "elapsed_jiffies_before": ej, "elapsed_jiffies_after": eja,
            "settle_gate_flips": (ej >= THR) != (eja >= THR),
            "minrtt_probing_pre": ca["minrtt_probing"],
            "epoch_start_pre": ca["epoch_start"],
            "in_ack": e["in_ack"], "in_acked": e["in_acked"],
            "priv_pre": {f: e["priv_pre_" + f] for f in ALL_PRIVATE_FIELDS},
            "priv_post_recorded": {f: e["priv_post_" + f] for f in ALL_PRIVATE_FIELDS},
            "post_snd_cwnd_recorded": e["post_snd_cwnd"],
            "post_snd_cwnd_cnt_recorded": e["post_snd_cwnd_cnt"],
            "priv_post_mode_recorded": e["priv_post_mode"],
        })

with open("data/a3_settle_latch_events.json", "w") as f:
    json.dump(rows, f, indent=2, default=str)

print("settle-latch guard evaluations:", len(rows))
for r in rows:
    print("  {rep} seq={seq} t={rel_s}s  bps={dlv_rate_bps} max={dlv_rate_max} ratio={ratio} "
          "3/4max={three_quarter_max} guard_pass={guard_passes} ej={elapsed_jiffies_before}/{elapsed_jiffies_after} "
          "flips={settle_gate_flips} probing_pre={minrtt_probing_pre} epoch_pre={epoch_start_pre} "
          "acked={in_acked}".format(**r))
