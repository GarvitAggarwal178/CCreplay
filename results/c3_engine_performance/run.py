import sys, time, csv, json, resource
sys.path.insert(0, '.')
from ccreplay import traces as traces_mod
from ccreplay.diff import run_diff, run_all_decisions, _detect_version_and_parse

cases = [
    ('reno', 'raw/r0/rep1.ccr'),
    ('reno', 'raw/smoketest/t1.ccr'),
    ('cubic', 'raw/cubic_replay/primary/rep1.ccr'),
    ('covegas', 'raw/covegas_replay/primary/rep1.ccr'),
]

rows = []
for ref_id, path in cases:
    trace = next(t for t in traces_mod.list_traces() if t['path'] == path)
    trace_id = trace['id']
    n_events = trace['n_dominant_events']
    abi = trace['abi']

    for rep in range(5):
        t0 = time.perf_counter()
        hdr, events, select_dominant_connection, CALLBACK_NAMES = _detect_version_and_parse(str(traces_mod.resolve_id(trace_id)))
        _, dominant_events, _ = select_dominant_connection(events)
        dominant_events.sort(key=lambda e: e['seq'])
        t_parse = time.perf_counter() - t0
        rows.append({'abi': abi, 'trace_path': path, 'n_events': n_events, 'metric': 'parse', 'rep': rep,
                      'seconds': t_parse, 'events_per_sec': n_events / t_parse if t_parse > 0 else None,
                      'peak_rss_kb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})

        t0 = time.perf_counter()
        run_all_decisions(trace_id, ref_id, ref_id, mode='B')
        t_replay = time.perf_counter() - t0
        rows.append({'abi': abi, 'trace_path': path, 'n_events': n_events, 'metric': 'replay_mode_b', 'rep': rep,
                      'seconds': t_replay, 'events_per_sec': n_events / t_replay if t_replay > 0 else None,
                      'peak_rss_kb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})

        t0 = time.perf_counter()
        run_diff(trace_id, ref_id, ref_id)
        t_diff = time.perf_counter() - t0
        rows.append({'abi': abi, 'trace_path': path, 'n_events': n_events, 'metric': 'diff', 'rep': rep,
                      'seconds': t_diff, 'events_per_sec': n_events / t_diff if t_diff > 0 else None,
                      'peak_rss_kb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})

        t0 = time.perf_counter()
        run_all_decisions(trace_id, ref_id, ref_id, mode='A')
        t_all = time.perf_counter() - t0
        rows.append({'abi': abi, 'trace_path': path, 'n_events': n_events, 'metric': 'all_decisions_mode_a', 'rep': rep,
                      'seconds': t_all, 'events_per_sec': n_events / t_all if t_all > 0 else None,
                      'peak_rss_kb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})
        print(f"{path} rep{rep}: parse={t_parse:.3f}s replay={t_replay:.3f}s diff={t_diff:.3f}s all={t_all:.3f}s")

with open('results/c3_engine_performance/results.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['abi','trace_path','n_events','metric','rep','seconds','events_per_sec','peak_rss_kb'])
    w.writeheader()
    for r in rows:
        w.writerow(r)
with open('results/c3_engine_performance/results.json', 'w') as f:
    json.dump(rows, f, indent=2, default=str)
