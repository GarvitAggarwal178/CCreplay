#!/usr/bin/env python3
"""Measures CCReplay Studio's cold/warm API latency and server RSS against a
FRESH server instance (started by this script, so "cold" is real, not
assumed). Used to check plan §3 A3.2's "190k-event view stays responsive
(<2 s load)" done-when with actual numbers instead of a guess. Prints a
plain-text report; does not assert pass/fail (this is a measurement, not a
gate) -- the report is read and the result is written into STUDIO_STATUS.md
by hand so any judgment call about what counts as "responsive" is visible.
"""
import json
import pathlib
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
PORT = 8766
BASE = f"http://127.0.0.1:{PORT}"
PIDFILE = ROOT / ".autorun" / f"server-measure-{PORT}.pid"


def timed_get(url):
    t0 = time.monotonic()
    with urllib.request.urlopen(url, timeout=30) as r:
        body = r.read()
    return time.monotonic() - t0, len(body)


def rss_kb(pid):
    try:
        status = pathlib.Path(f"/proc/{pid}/status").read_text()
        for line in status.splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except Exception:
        return None
    return None


def main():
    subprocess.run(["bash", str(ROOT / "run_studio.sh"), "--stop"], cwd=str(ROOT),
                    capture_output=True)
    time.sleep(0.5)
    proc = subprocess.run(
        ["bash", str(ROOT / "run_studio.sh"), "--port", str(PORT), "--daemon"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    print(proc.stdout)
    pidfile = ROOT / ".autorun" / "server.pid"
    pid = int(pidfile.read_text().strip())
    time.sleep(1.0)  # let uvicorn finish binding

    report = {}

    t_cold, n_cold = timed_get(BASE + "/api/traces")
    report["cold_list_traces_s"] = round(t_cold, 3)
    report["cold_list_traces_bytes"] = n_cold

    t_warm, n_warm = timed_get(BASE + "/api/traces")
    report["warm_list_traces_s"] = round(t_warm, 3)

    # Largest single trace in the library (plan's "190k-event view" refers to
    # the combined CoVegas primary set across 3 files, 63k-64k events each;
    # there is no single 190k-event trace -- the largest single file is
    # raw/smoketest/t1.ccr at 160,518 events).
    traces = json.loads(urllib.request.urlopen(BASE + "/api/traces", timeout=30).read())
    largest = max(traces, key=lambda t: t.get("n_dominant_events", 0))
    report["largest_trace_path"] = largest["path"]
    report["largest_trace_events"] = largest["n_dominant_events"]

    t_series, n_series = timed_get(
        f"{BASE}/api/traces/{largest['id']}/series?fields=pre_snd_cwnd,pre_snd_ssthresh&max_points=4000"
    )
    report["largest_trace_series_s"] = round(t_series, 3)

    t_events, n_events = timed_get(f"{BASE}/api/traces/{largest['id']}/events?offset=0&limit=100")
    report["largest_trace_events_page_s"] = round(t_events, 3)

    report["server_rss_kb_after_largest_trace_load"] = rss_kb(pid)

    subprocess.run(["bash", str(ROOT / "run_studio.sh"), "--stop"], cwd=str(ROOT),
                    capture_output=True)

    print(json.dumps(report, indent=2))

    out = ROOT / ".autorun" / "load_measurement.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nwritten to {out}")


if __name__ == "__main__":
    main()
