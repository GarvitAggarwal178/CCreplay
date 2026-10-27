"""Phase 3 Part C analysis: Welch 90% CI + TOST verdicts with the margins
FROZEN in data/phase3_kali/SPEC.md Part C (throughput +/-1% of the control
mean, mean RTT +/-2 ms). Also the descriptive direct-overhead numbers from
the bpf_stats runs.

Usage: python3 scripts/kali/nonint_analyze.py raw/kali_6.19.14/nonint data/phase3_kali/nonint/analysis.json
"""
import glob
import json
import os
import re
import sys

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from experiments.kali import lab_metrics as lm  # noqa: E402

THROUGHPUT_MARGIN_FRAC = 0.01   # SPEC Part C, frozen
RTT_MARGIN_MS = 2.0             # SPEC Part C, frozen
MIN_VALID_PER_ARM = 8           # docs/EVALUATION.md section 3


def run_rows(raw_dir):
    rows = []
    for ip in sorted(glob.glob(os.path.join(raw_dir, "run*_iperf3.json"))):
        prefix = ip[: -len("_iperf3.json")]
        m = re.match(r"run(\d+)_([RC])$", os.path.basename(prefix))
        if not m:
            continue
        row = {"run": int(m.group(1)), "arm": m.group(2)}
        try:
            row.update(lm.iperf3_metrics(ip))
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
        try:
            meta = json.load(open(prefix + ".meta.json"))
            row.update(invocations_all_callbacks=meta.get("invocations"), emitted=meta.get("emitted"),
                       drops=meta.get("drops"))
        except (OSError, json.JSONDecodeError) as exc:
            row["meta_error"] = str(exc)
        rows.append(row)
    return rows


def overhead(raw_dir):
    out = []
    for mp in sorted(glob.glob(os.path.join(raw_dir, "stats*_R.meta.json"))):
        meta = json.load(open(mp))
        per_cb = {}
        for cb, s in (meta.get("bpf_stats") or {}).items():
            per_cb[cb] = {"run_cnt": s["run_cnt"], "run_time_ns": s["run_time_ns"],
                          "ns_per_call": s["run_time_ns"] / s["run_cnt"] if s["run_cnt"] else None}
        out.append({"run": os.path.basename(mp), "bpf_stats": per_cb})
    return out


def analyze(rows):
    valid = [r for r in rows if "error" not in r and r.get("mean_rtt_ms") is not None]
    R = [r for r in valid if r["arm"] == "R"]
    C = [r for r in valid if r["arm"] == "C"]
    res = {"n_valid": {"R": len(R), "C": len(C)},
           "n_invalid": len(rows) - len(valid),
           "margins": {"throughput_frac_of_control_mean": THROUGHPUT_MARGIN_FRAC, "mean_rtt_ms": RTT_MARGIN_MS}}
    if len(R) < MIN_VALID_PER_ARM or len(C) < MIN_VALID_PER_ARM:
        res["verdict"] = "INCOMPLETE"
        res["reason"] = f"fewer than {MIN_VALID_PER_ARM} valid runs in an arm"
        return res
    metrics = {}
    for name, key, margin in (
        ("throughput", "throughput_bps", THROUGHPUT_MARGIN_FRAC * lm.mean([r["throughput_bps"] for r in C])),
        ("mean_rtt", "mean_rtt_ms", RTT_MARGIN_MS),
    ):
        a = [r[key] for r in R]
        b = [r[key] for r in C]
        d, lo, hi, df, se = lm.welch_ci(a, b, 0.90)
        metrics[name] = {
            "mean_R": lm.mean(a), "mean_C": lm.mean(b),
            "sd_R": lm.var(a) ** 0.5, "sd_C": lm.var(b) ** 0.5,
            "diff_R_minus_C": d, "ci90": [lo, hi], "welch_df": df, "se": se,
            "margin": margin, "verdict": lm.tost_verdict(lo, hi, margin),
        }
    res["metrics"] = metrics
    v = [m["verdict"] for m in metrics.values()]
    res["verdict"] = ("PASS" if all(x == "EQUIVALENT" for x in v)
                      else "FAIL" if any(x == "NOT EQUIVALENT" for x in v) else "INCONCLUSIVE")
    # Descriptive (SPEC: cong_avoid count; the C arm emits no per-callback
    # events and bpf_stats is off, so the all-callback invocation total is used).
    inv = {arm: [r["invocations_all_callbacks"] for r in (R if arm == "R" else C)
                 if r.get("invocations_all_callbacks") is not None] for arm in "RC"}
    res["descriptive"] = {
        "invocations_all_callbacks_mean": {k: (lm.mean(v) if v else None) for k, v in inv.items()},
        "retransmits_mean": {"R": lm.mean([r["retransmits"] for r in R]), "C": lm.mean([r["retransmits"] for r in C])},
    }
    return res


def main(raw_dir, out_path):
    rows = run_rows(raw_dir)
    res = analyze(rows)
    res["runs"] = rows
    res["direct_overhead_bpf_stats"] = overhead(raw_dir)
    with open(out_path, "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps({k: res[k] for k in ("verdict", "n_valid", "n_invalid")}, indent=1))
    for name, m in res.get("metrics", {}).items():
        print(name, m["verdict"], "diff", round(m["diff_R_minus_C"], 4), "ci90", [round(x, 4) for x in m["ci90"]], "margin", round(m["margin"], 4))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
