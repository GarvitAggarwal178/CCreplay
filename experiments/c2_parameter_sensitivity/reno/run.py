import pathlib
import sys
HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from experiments._support import output_directory, require_recordings

OUT_DIR = output_directory('c2_parameter_sensitivity-reno', existing=False)
import sys, json, csv

from ccreplay import controllers as controllers_mod, traces as traces_mod
from ccreplay.diff import all_decisions_core

reno_traces = require_recordings(['raw/r0/rep1.ccr', 'raw/r0/rep2.ccr', 'raw/r0/rep3.ccr'])

ratios = [(1, 2, '1/2 (standard)'), (6, 10, '6/10'), (7, 10, '7/10'), (3, 4, '3/4')]
ref_mod = controllers_mod.load_controller('reno')

rows = []
for num, den, label in ratios:
    cand_mod = controllers_mod.make_param('reno', f'c2_reno_{num}_{den}', {'num': num, 'den': den})
    for trace_id in reno_traces:
        trace_path = traces_mod.resolve_id(trace_id)
        trace_abi = traces_mod.get_abi(trace_id)
        result = all_decisions_core(trace_path, trace_abi, ref_mod, cand_mod, 'A')
        result_stats = result['delta_stats'].get('result', {})
        rows.append({
            'ratio_label': label, 'num': num, 'den': den, 'trace_id': trace_id,
            'n_events': result['n_events'], 'n_disagree': result['n_disagree'],
            'disagreement_rate': result['disagreement_rate'],
            'per_callback_disagree': result['per_callback_disagree'],
            'result_median_delta': result_stats.get('median'),
            'first_disagreement_seq': result['first_disagreement_seq'],
        })

with open(OUT_DIR / 'results.json', 'w') as f:
    json.dump(rows, f, indent=2, default=str)
with open(OUT_DIR / 'results.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['ratio_label','num','den','trace_id','n_events','n_disagree',
                'disagreement_rate','result_median_delta','first_disagreement_seq'])
    for r in rows:
        w.writerow([r['ratio_label'], r['num'], r['den'], r['trace_id'], r['n_events'],
                    r['n_disagree'], r['disagreement_rate'], r['result_median_delta'],
                    r['first_disagreement_seq']])
