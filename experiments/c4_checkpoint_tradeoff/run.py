import pathlib
import sys
HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments._support import output_directory, require_recordings

OUT_DIR = output_directory('c4_checkpoint_tradeoff', existing=False)
import sys, time, json, csv

from ccreplay import controllers as controllers_mod, traces as traces_mod
from user.ccreplay_checkpoint import run_with_checkpoints, nearest_checkpoint_at_or_before, replay_suffix_from_checkpoint, same_divergence

cases = [
    ('seeded_bug', [t['id'] for t in traces_mod.list_traces() if t['path'] == 'raw/cubic_replay/primary/rep1.ccr'][0], 'cubic', 'cubic_bug_ssthresh'),
    ('historical', [t['id'] for t in traces_mod.list_traces() if t['path'] == 'raw/covegas_campaign/rep4.ccr'][0], 'covegas', 'covegas_v3_latch'),
]
intervals = [50, 100, 250, 500, 1000, 2500, 5000]

rows = []
for case_name, trace_id, ref_id, cand_id in cases:
    trace_path = str(traces_mod.resolve_id(trace_id))
    ref_mod = controllers_mod.load_controller(ref_id)
    cand_mod = controllers_mod.load_controller(cand_id)
    for interval in intervals:
        t0 = time.perf_counter()
        checkpoints, first_divergence, dominant_events, CALLBACK_NAMES = run_with_checkpoints(trace_path, ref_mod, cand_mod, interval)
        t_build = time.perf_counter() - t0
        ckpt_bytes = len(json.dumps(checkpoints, default=str))
        if first_divergence is None:
            rows.append({'case': case_name, 'interval': interval, 'n_checkpoints': len(checkpoints),
                         'checkpoint_bytes': ckpt_bytes, 'suffix_length': None, 't_build_s': t_build,
                         't_reproduce_s': None, 'identical': None, 'note': 'no divergence found'})
            continue
        D = first_divergence['event_index']
        ckpt = nearest_checkpoint_at_or_before(checkpoints, D)
        t1 = time.perf_counter()
        suffix_divergence = replay_suffix_from_checkpoint(ckpt, dominant_events, ref_mod, cand_mod, D)
        t_reproduce = time.perf_counter() - t1
        identical = same_divergence(first_divergence, suffix_divergence)
        rows.append({'case': case_name, 'interval': interval, 'n_checkpoints': len(checkpoints),
                     'checkpoint_bytes': ckpt_bytes, 'suffix_length': D - ckpt['next_event_index'] + 1,
                     't_build_s': t_build, 't_reproduce_s': t_reproduce, 'identical': identical,
                     'checkpoint_event_index': ckpt['next_event_index'], 'divergence_seq': first_divergence['seq']})
        print(f"{case_name} interval={interval}: checkpoints={len(checkpoints)} suffix={D-ckpt['next_event_index']+1} identical={identical}")

with open(OUT_DIR / 'results.json', 'w') as f:
    json.dump(rows, f, indent=2, default=str)
with open(OUT_DIR / 'results.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    for r in rows:
        w.writerow(r)
