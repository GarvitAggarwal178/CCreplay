"""Phase 3 Part B summarizer: results/lab/raw/<config>_rep<n>_* ->
results/lab/<config>_rep<n>.json (one per run, listed by the Studio Lab page).
Live network measurements of native kernel CC, not replay output.

Usage: python3 scripts/kali/lab_summarize.py results/lab/raw results/lab
"""
import glob
import json
import os
import sys

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from experiments.kali import lab_metrics as lm  # noqa: E402


def flow(raw_prefix, port):
    f = {"port": port}
    try:
        f.update(lm.iperf3_metrics(f"{raw_prefix}_iperf3_{port}.json"))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        f["error"] = f"{type(exc).__name__}: {exc}"
    try:
        s = lm.ss_srtt_samples(f"{raw_prefix}_ss_{port}.log")
        f.update(srtt_samples=len(s), srtt_p50_ms=lm.percentile(s, 50), srtt_p95_ms=lm.percentile(s, 95))
    except OSError as exc:
        f["ss_error"] = str(exc)
    return f


def main(raw_dir, out_dir):
    vm = open(os.path.join(raw_dir, "vm_info.txt")).read() if os.path.exists(os.path.join(raw_dir, "vm_info.txt")) else ""
    n = 0
    for cfg_path in sorted(glob.glob(os.path.join(raw_dir, "*_config.json"))):
        prefix = cfg_path[: -len("_config.json")]
        cfg = json.load(open(cfg_path))
        flows = [flow(prefix, 5201)]
        if cfg["competing_cca"] != "-":
            flows.append(flow(prefix, 5301))
        flows[0]["cca"] = cfg["cca"]
        if len(flows) > 1:
            flows[1]["cca"] = cfg["competing_cca"]
        result = {
            "kind": "ccreplay_network_lab_run",
            "note": "live network measurement of native kernel congestion control; not CCReplay replay output",
            "testbed": "Kali VM, Gate-3-R2 namespace topology (data/phase3_kali/SPEC.md Part B)",
            "config": cfg, "flows": flows, "vm_info": vm,
            "raw_prefix": os.path.relpath(prefix, out_dir).replace(os.sep, "/"),
        }
        name = f"{cfg['config']}_rep{cfg['rep']}.json"
        with open(os.path.join(out_dir, name), "w", newline="\n") as f:  # LF on every OS (byte-exact evidence)
            json.dump(result, f, indent=1)
        n += 1
        print(name, [(x.get("cca"), round(x.get("throughput_bps", 0) / 1e6, 2), x.get("mean_rtt_ms"), x.get("error")) for x in flows])
    print(f"{n} lab result files written to {out_dir}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
