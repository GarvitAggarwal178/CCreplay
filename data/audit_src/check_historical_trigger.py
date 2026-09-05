"""Part 8 (addendum): verify the historical trigger (spurious COMPETE entry
during an off-period) is actually PRESENT in the E1 primary trace before
running the buggy-vs-fixed differential replay.

Uses the trace's own recorded mode transitions (priv_pre_mode -> priv_post_mode
on real events, not the model) and relative elapsed time since the first
event (ts_ns delta), cross-referenced against the known on/off schedule
derived from the real wall-clock cubic cross-traffic start/stop timestamps
captured during the E1 run.
"""
import sys
sys.path.insert(0, ".")
sys.path.insert(0, "user")
from user.ccr_trace_v2 import parse_trace_v2, select_dominant_connection, CALLBACK_NAMES

import json


def load_on_periods(prefix):
    """Reads rep<N>_covegas_iperf3.json + rep<N>_cubic_rep{1,2,3}_{start,stop}_ts.txt
    for the given prefix (e.g. raw/covegas_replay/primary/rep2) and returns
    on-periods as (start,end) seconds relative to the covegas connection's
    own wall-clock start -- ground truth from this run's own timestamps, not
    hardcoded from rep1."""
    with open(f"{prefix}_covegas_iperf3.json") as f:
        covegas_start = json.load(f)["start"]["timestamp"]["timesecs"]
    periods = []
    for i in (1, 2, 3):
        with open(f"{prefix}_cubic_rep{i}_start_ts.txt") as f:
            start = float(f.read().strip())
        with open(f"{prefix}_cubic_rep{i}_stop_ts.txt") as f:
            stop = float(f.read().strip())
        periods.append((start - covegas_start, stop - covegas_start))
    return periods


def phase_at(t, on_periods_rel):
    for (a, b) in on_periods_rel:
        if a <= t < b:
            return "ON"
    return "OFF"


def main():
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <rep_prefix e.g. raw/covegas_replay/primary/rep2>", file=sys.stderr)
        sys.exit(2)
    prefix = sys.argv[1]
    trace = f"{prefix}.ccr"
    on_periods_rel = load_on_periods(prefix)

    hdr, events = parse_trace_v2(trace)
    _, dominant_events, _ = select_dominant_connection(events)
    dominant_events.sort(key=lambda e: e["seq"])

    t0 = dominant_events[0]["ts_ns"]
    transitions = []
    for e in dominant_events:
        if e["priv_pre_mode"] != e["priv_post_mode"]:
            rel_s = (e["ts_ns"] - t0) / 1e9
            transitions.append({
                "seq": e["seq"], "callback": CALLBACK_NAMES.get(e["callback_id"]),
                "rel_s": rel_s, "phase": phase_at(rel_s, on_periods_rel),
                "pre_mode": e["priv_pre_mode"], "post_mode": e["priv_post_mode"],
            })

    print(f"trace: {trace}")
    print(f"total dominant events: {len(dominant_events)}")
    print(f"on-periods (relative seconds): {on_periods_rel}")
    print(f"total mode transitions found: {len(transitions)}")
    for t in transitions:
        direction = "DELAY->COMPETE" if t["pre_mode"] == 0 else "COMPETE->DELAY"
        print(f"  seq={t['seq']:6d} t={t['rel_s']:7.2f}s phase={t['phase']:3s} {direction} cb={t['callback']}")

    spurious = [t for t in transitions if t["pre_mode"] == 0 and t["post_mode"] == 1 and t["phase"] == "OFF"]
    print()
    print(f"DELAY->COMPETE transitions during an OFF period (the historical trigger): {len(spurious)}")
    for s in spurious:
        print(f"  TRIGGER PRESENT: seq={s['seq']} t={s['rel_s']:.2f}s")

    with open("data/historical_trigger_validation.md", "a") as f:
        f.write(f"## Attempt: `{trace}`\n\n")
        f.write("Real recorded mode transitions (`priv_pre_mode` -> `priv_post_mode` on actual trace "
                "events, not the model) cross-referenced against this run's own real wall-clock "
                "on/off schedule (`iperf3` timestamps for this exact rep, not hardcoded from a "
                "different run).\n\n")
        f.write(f"On-periods (seconds relative to the covegas connection's own first recorded event): "
                f"{[(round(a,2), round(b,2)) for a,b in on_periods_rel]}\n\n")
        f.write("### All mode transitions found\n\n")
        f.write("| seq | t (s) | phase | direction | callback |\n|---|---|---|---|---|\n")
        for t in transitions:
            direction = "DELAY->COMPETE" if t["pre_mode"] == 0 else "COMPETE->DELAY"
            f.write(f"| {t['seq']} | {t['rel_s']:.2f} | {t['phase']} | {direction} | {t['callback']} |\n")
        f.write("\n### Trigger classification for this attempt\n\n")
        if spurious:
            f.write(f"**PRESENT.** {len(spurious)} spurious DELAY->COMPETE transition(s) during an "
                    f"OFF period found:\n\n")
            for s in spurious:
                f.write(f"* seq={s['seq']}, t={s['rel_s']:.2f}s\n")
        else:
            f.write("**ABSENT** in this attempt. No DELAY->COMPETE transition occurred during an OFF "
                    "period.\n")
        f.write("\n---\n\n")

    sys.exit(0 if spurious else 1)


if __name__ == "__main__":
    main()
