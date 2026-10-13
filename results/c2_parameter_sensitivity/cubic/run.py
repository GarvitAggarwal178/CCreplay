import sys, json, csv, time
sys.path.insert(0, '.')
from ccreplay.sweep import run_sweep
from ccreplay import traces as traces_mod

cubic_traces = [t['id'] for t in traces_mod.list_traces()
                if t['path'] in ('raw/cubic_replay/primary/rep1.ccr',
                                 'raw/cubic_replay/primary/rep2.ccr',
                                 'raw/cubic_replay/primary/rep3.ccr')]

sweeps = {
    'beta': ('BETA', [512, 614, 717, 819, 921]),
    'bic_scale': ('BIC_SCALE', [10, 20, 41, 82, 164]),
    'fast_convergence': ('FAST_CONVERGENCE', [0, 1]),
    'tcp_friendliness': ('TCP_FRIENDLINESS', [0, 1]),
    'hystart': ('HYSTART', [0, 1]),
}

for name, (param, values) in sweeps.items():
    result = run_sweep('cubic', param, values, cubic_traces)
    with open(f'results/c2_parameter_sensitivity/cubic/{name}.json', 'w') as f:
        json.dump(result, f, indent=2, default=str)
    with open(f'results/c2_parameter_sensitivity/cubic/{name}.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['param','value','trace_id','n_events','n_disagree','disagreement_rate',
                    'result_median_delta','post_snd_cwnd_median_delta','first_disagreement_seq'])
        for p in result['points']:
            w.writerow([p.get('param'), p.get('value'), p.get('trace_id'), p.get('n_events'),
                        p.get('n_disagree'), p.get('disagreement_rate'),
                        p.get('result_median_delta'), p.get('post_snd_cwnd_median_delta'),
                        p.get('first_disagreement_seq')])
