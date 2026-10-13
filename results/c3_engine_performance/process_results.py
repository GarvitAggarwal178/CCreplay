#!/usr/bin/env python3
import json
import csv
from statistics import mean, stdev
from collections import defaultdict
from datetime import datetime
import subprocess

# Load results
with open('results/c3_engine_performance/results.json', 'r') as f:
    rows = json.load(f)

# Group by (trace_path, metric)
groups = defaultdict(list)
for row in rows:
    key = (row['trace_path'], row['metric'], row['abi'], row['n_events'])
    groups[key].append(row)

# Calculate statistics
summary_rows = []
for (trace_path, metric, abi, n_events), group in sorted(groups.items()):
    seconds = [r['seconds'] for r in group]
    events_per_sec = [r['events_per_sec'] for r in group if r['events_per_sec'] is not None]
    peak_rss = [r['peak_rss_kb'] for r in group]

    mean_seconds = mean(seconds)
    stdev_seconds = stdev(seconds) if len(seconds) > 1 else 0
    mean_events_per_sec = mean(events_per_sec) if events_per_sec else None
    max_peak_rss_kb = max(peak_rss)

    summary_rows.append({
        'abi': abi,
        'trace_path': trace_path,
        'n_events': n_events,
        'metric': metric,
        'mean_seconds': mean_seconds,
        'stdev_seconds': stdev_seconds,
        'mean_events_per_sec': mean_events_per_sec,
        'max_peak_rss_kb': max_peak_rss_kb
    })

# Write summary.csv
with open('results/c3_engine_performance/summary.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['abi','trace_path','n_events','metric','mean_seconds','stdev_seconds','mean_events_per_sec','max_peak_rss_kb'])
    w.writeheader()
    for r in summary_rows:
        w.writerow(r)

# Get git info
git_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()
git_status = subprocess.check_output(['git', 'status', '--porcelain']).decode().strip()
uname_r = subprocess.check_output(['uname', '-r']).decode().strip()
python_version = subprocess.check_output(['.venv/bin/python', '--version']).decode().strip()
nproc = int(subprocess.check_output(['nproc']).decode().strip())

# Write manifest.json
manifest = {
    "command": ".venv/bin/python results/c3_engine_performance/run.py",
    "git_commit": git_commit,
    "dirty": len(git_status) > 0,
    "git_status": git_status if git_status else "clean",
    "host": {
        "uname_r": uname_r,
        "python": python_version,
        "nproc": nproc
    },
    "started": "2026-10-13T08:18:00Z",
    "finished": datetime.utcnow().isoformat() + "Z"
}

with open('results/c3_engine_performance/manifest.json', 'w') as f:
    json.dump(manifest, f, indent=2)

print("Processed results written to summary.csv and manifest.json")
