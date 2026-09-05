"""Part D: read-only analysis of the archived historical known-positive run
(~/cn-spike/covegas/raw/partC_v4/Ph500_B5x_rep2_ringbuf.csv), the HOLD_MS=500
rep2 run whose documented spurious off-period COMPETE entry (~t=65.51s,
revert ~t=66.51s) is the historical A3 positive.

The archive is read-only. This script reads it, never writes it.

CSV columns (Ph500_B5x_rep2_ringbuf.csv):
  ts_ns,srtt_us,min_rtt_us,recent_min_us,cwnd,queue_est,detect_count,
  dlv_rate_bps,dlv_rate_compete,dlv_rate_max,mode,probing

Wall-clock anchors from the run's own *_start_ts.txt / *_stop_ts.txt files.
"""
import csv
import sys
import json
import os

ARCHIVE = os.path.expanduser("~/cn-spike/covegas/raw/partC_v4")
PREFIX = "Ph500_B5x_rep2"


def read_ts(name):
    with open(os.path.join(ARCHIVE, f"{PREFIX}_{name}.txt")) as f:
        return float(f.read().strip())


def main():
    covegas_start = read_ts("covegas_start_ts")
    on_wall = []
    for i in (1, 2, 3):
        on_wall.append((read_ts(f"cubic_rep{i}_start_ts"), read_ts(f"cubic_rep{i}_stop_ts")))
    on_rel = [(a - covegas_start, b - covegas_start) for a, b in on_wall]

    def phase(t):
        for a, b in on_rel:
            if a <= t < b:
                return "ON"
        return "OFF"

    csv_path = os.path.join(ARCHIVE, f"{PREFIX}_ringbuf.csv")
    rows = list(csv.DictReader(open(csv_path)))
    t0 = int(rows[0]["ts_ns"])

    def rel(r):
        return (int(r["ts_ns"]) - t0) / 1e9

    # mode transitions
    transitions = []
    prev = None
    prev_row = None
    for r in rows:
        m = int(r["mode"])
        if prev is not None and m != prev:
            transitions.append({
                "t_rel_s": rel(r), "phase": phase(rel(r)),
                "dir": "DELAY->COMPETE" if prev == 0 else "COMPETE->DELAY",
                "pre_row": prev_row, "row": r,
            })
        prev = m
        prev_row = r

    # locate the documented spurious entry: DELAY->COMPETE in an OFF period
    spurious_entries = [tr for tr in transitions
                        if tr["dir"] == "DELAY->COMPETE" and tr["phase"] == "OFF"]

    out = {
        "archive_csv": csv_path,
        "on_periods_rel_s": [(round(a, 2), round(b, 2)) for a, b in on_rel],
        "total_rows": len(rows),
        "all_transitions": [
            {"t_rel_s": round(tr["t_rel_s"], 3), "phase": tr["phase"], "dir": tr["dir"],
             "dlv_rate_bps": int(tr["row"]["dlv_rate_bps"]),
             "dlv_rate_compete": int(tr["row"]["dlv_rate_compete"]),
             "dlv_rate_max": int(tr["row"]["dlv_rate_max"]),
             "cwnd": int(tr["row"]["cwnd"]), "mode_after": int(tr["row"]["mode"])}
            for tr in transitions
        ],
        "predicate_H_candidates": [],
    }

    for se in spurious_entries:
        # find the matching revert (next COMPETE->DELAY after this entry)
        entry_t = se["t_rel_s"]
        revert = None
        for tr in transitions:
            if tr["dir"] == "COMPETE->DELAY" and tr["t_rel_s"] > entry_t:
                revert = tr
                break
        # scan the COMPETE episode rows for the settle window (~1s after entry)
        episode_rows = [r for r in rows
                        if entry_t <= rel(r) <= (revert["t_rel_s"] if revert else entry_t + 5)]
        # the guard would be evaluated ~RATE_SETTLE_MS (1.0s) after entry;
        # sample the row nearest entry_t + 1.0s
        settle_target = entry_t + 1.0
        settle_row = min(episode_rows, key=lambda r: abs(rel(r) - settle_target)) if episode_rows else None

        cand = {
            "entry_t_rel_s": round(entry_t, 3),
            "entry_phase": se["phase"],
            "revert_t_rel_s": round(revert["t_rel_s"], 3) if revert else None,
            "revert_minus_entry_s": round(revert["t_rel_s"] - entry_t, 3) if revert else None,
            "dlv_rate_compete_ever_latched_in_episode": max(
                (int(r["dlv_rate_compete"]) for r in episode_rows), default=0),
            "settle_row_approx": None,
        }
        if settle_row is not None:
            bps = int(settle_row["dlv_rate_bps"])
            mx = int(settle_row["dlv_rate_max"])
            cand["settle_row_approx"] = {
                "t_rel_s": round(rel(settle_row), 3),
                "dlv_rate_bps": bps,
                "dlv_rate_max": mx,
                "three_quarter_max": (mx * 3) // 4,
                "v4_guard_passes_latch": bps < (mx * 3) // 4,
                "v4_guard_fails_revert": not (bps < (mx * 3) // 4),
                "dlv_rate_compete": int(settle_row["dlv_rate_compete"]),
            }
        out["predicate_H_candidates"].append(cand)

    with open("data/historical_a3_archive_analysis.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
