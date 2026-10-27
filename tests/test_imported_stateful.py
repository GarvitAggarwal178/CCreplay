"""Initialized state is private history, never alternate shared TCP evolution."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from ccreplay.teaching_workbench import run_job, capture_window

SAMPLES=Path(__file__).resolve().parents[1]/'examples/algorithm_workbench'

def config():
    scenario=json.loads((SAMPLES/'scenario.json').read_text())
    event=deepcopy(scenario['events'][0]);event.update(callback_id=2,in_acked=1,pre_is_cwnd_limited=1,pre_snd_cwnd=12)
    scenario['events']=[dict(event,seq=i+1) for i in range(8)]
    return {'source_a':(SAMPLES/'packet_credit.py').read_text(),
            'source_b':(SAMPLES/'callback_credit.py').read_text(),
            'scenario':scenario,'execution_mode':'stateful'}


def test_difference_arises_from_accumulated_independent_private_state():
    job=config();out=run_job(job)
    assert out['first_difference']==2
    assert out['rows'][0]['private_a']=={'pre':{'ack_credit':0},'post':{'ack_credit':1}}
    assert out['rows'][2]['private_b']=={'pre':{'eligible_callbacks':2},'post':{'eligible_callbacks':0}}
    assert (out['rows'][2]['a']['post_snd_cwnd'],out['rows'][2]['b']['post_snd_cwnd'])==(12,13)
    assert all(row['input']['pre_snd_cwnd']==12 for row in out['rows'])
    assert run_job(job)==out  # fresh seeds and modules on each execution
    job['source_b']=job['source_a'].replace('ack_credit','different_private_key')
    assert run_job(job)['disagreements']==0  # shape is not a correctness oracle
    job['source_b']=job['source_a']
    assert run_job(job)['first_difference'] is None
    job['source_b']=job['source_b'].replace('credit // 4','credit // 2').replace('credit %= 4','credit %= 2')
    assert run_job(job)['rows'][1]['b']['post_snd_cwnd']==13


@pytest.mark.parametrize('value',["float('nan')", "float('inf')", "{1: 'non-string key'}", "{1,2}", "(1,2)", "object()"])
def test_invalid_initial_or_next_state_is_readable(value):
    job=config();job['source_a']=job['source_a'].replace("{'ack_credit': 0}",value)
    with pytest.raises(ValueError,match='finite JSON'):run_job(job)
    job=config();job['source_a']=job['source_a'].replace("{'ack_credit': credit}",value)
    with pytest.raises(ValueError,match='finite JSON'):run_job(job)


def test_explicit_initialization_and_recording_offset_rules():
    job=config();job['source_a']=job['source_a'].replace("INITIAL_PRIVATE_STATE = {'ack_credit': 0}",'')
    with pytest.raises(ValueError,match='requires INITIAL'):run_job(job)
    job=config();job.update(input_kind='recording',trace_id='raw__r0__rep1',offset=5,limit=100)
    with pytest.raises(ValueError,match='must start at index 0'):capture_window(job)
    job['offset']=0;job['recording_snapshot']=capture_window(job)
    first=run_job(job);assert first['compared_events']==100
    job['offset']=5
    with pytest.raises(ValueError,match='must start at index 0'):run_job(job)


def test_saved_initialization_is_pinned_and_input_mutation_isolated(tmp_path):
    job=config();marker=tmp_path/'seed';marker.write_text('0')
    job['source_a']=job['source_a'].replace("INITIAL_PRIVATE_STATE = {'ack_credit': 0}",f"from pathlib import Path\nINITIAL_PRIVATE_STATE = {{'ack_credit': int(Path({str(marker)!r}).read_text())}}")
    first=run_job(job);marker.write_text('3');job['_initialization_json']=first['initialization_json']
    assert run_job(job)==first
    job['source_b']=job['source_b'].replace("count = private_state['eligible_callbacks']", "count = private_state['eligible_callbacks']; private_state['eligible_callbacks'] = 999; event['pre_snd_cwnd']=100")
    out=run_job(job)
    assert all(row['input']['pre_snd_cwnd']==12 for row in out['rows'])
    assert out['rows'][0]['private_b']['pre']=={'eligible_callbacks':0}
