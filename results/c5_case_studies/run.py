import sys, json
sys.path.insert(0, '.')
from ccreplay import traces as traces_mod
from ccreplay.diff import run_diff

cubic_rep1 = [t['id'] for t in traces_mod.list_traces() if t['path'] == 'raw/cubic_replay/primary/rep1.ccr'][0]
covegas_rep4 = [t['id'] for t in traces_mod.list_traces() if t['path'] == 'raw/covegas_campaign/rep4.ccr'][0]

cases = [
    ('positive_1_ssthresh', cubic_rep1, 'cubic', 'cubic_bug_ssthresh', 'DIVERGENCE'),
    ('positive_2_epoch_reset', cubic_rep1, 'cubic', 'cubic_bug_epoch_reset', 'DIVERGENCE'),
    ('positive_3_ack_accounting', cubic_rep1, 'cubic', 'cubic_bug_ack_accounting', 'DIVERGENCE'),
    ('negative_dormant_undo', cubic_rep1, 'cubic', 'cubic_bug_dormant_undo', 'NO DIVERGENCE'),
    ('historical_a3', covegas_rep4, 'covegas', 'covegas_v3_latch', 'DIVERGENCE'),
]

results = []
for name, trace_id, ref_id, cand_id, expected_result in cases:
    r = run_diff(trace_id, ref_id, cand_id)
    d = r.get('divergence')
    entry = {
        'case': name, 'trace_id': trace_id, 'reference': ref_id, 'candidate': cand_id,
        'expected_result': expected_result, 'observed_result': r['result'],
        'matches_expected': r['result'] == expected_result,
        'first_divergent_seq': d['first_divergent_event']['seq'] if d else None,
        'callback': d['callback'] if d else None,
        'kind': r.get('kind'),
    }
    results.append(entry)
    print(f"{name}: expected={expected_result} observed={r['result']} seq={entry['first_divergent_seq']} match={entry['matches_expected']}")

with open('results/c5_case_studies/results.json', 'w') as f:
    json.dump(results, f, indent=2, default=str)
