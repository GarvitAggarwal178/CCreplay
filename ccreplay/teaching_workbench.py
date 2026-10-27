"""Executable teaching workbench. User source executes only inside a worker.
The policies use event-local ABI-v0 inputs, with explicit event-local or initialized stateful execution.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import types

CALLBACKS = {1: 'ssthresh', 2: 'cong_avoid', 3: 'undo_cwnd'}
FIELDS = {1: ['result', 'post_snd_cwnd', 'post_snd_cwnd_cnt'],
          2: ['post_snd_cwnd', 'post_snd_cwnd_cnt'],
          3: ['result', 'post_snd_cwnd', 'post_snd_cwnd_cnt']}
INPUTS = ('seq', 'callback_id', 'in_ack', 'in_acked', 'pre_snd_cwnd',
          'pre_snd_ssthresh', 'pre_snd_cwnd_cnt', 'pre_snd_cwnd_clamp',
          'pre_prior_cwnd', 'pre_max_packets_out', 'pre_is_cwnd_limited')
MAX_SOURCE = 100_000
MAX_EVENTS = 1000

def digest(value):
    raw = value.encode() if isinstance(value, str) else json.dumps(value, sort_keys=True, allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()

def validate_scenario(scenario):
    if scenario.get('schema') != 'ccreplay.teaching.v1' or scenario.get('provenance') != 'synthetic':
        raise ValueError('Custom JSON must declare schema ccreplay.teaching.v1 and provenance synthetic')
    events = scenario.get('events')
    if not isinstance(events, list) or not 1 <= len(events) <= MAX_EVENTS:
        raise ValueError('Provide 1 to 1000 callback inputs')
    last = -1
    for e in events:
        if not isinstance(e, dict):
            raise ValueError('Each event must be an object')
        for key in INPUTS:
            v = e.get(key)
            if type(v) is not int or not 0 <= v <= 0xffffffff:
                raise ValueError(f'{key} must be an unsigned 32-bit integer')
        if e['seq'] <= last or e['callback_id'] not in CALLBACKS:
            raise ValueError('Sequence numbers must increase and callbacks must be 1, 2 or 3')
        if not 2 <= e['pre_snd_cwnd'] <= e['pre_snd_cwnd_clamp']:
            raise ValueError('Require 2 <= cwnd <= clamp')
        if e['pre_is_cwnd_limited'] not in (0, 1):
            raise ValueError('pre_is_cwnd_limited must be 0 or 1')
        last = e['seq']
    return copy.deepcopy(events)

def load_source(source, name):
    if not isinstance(source, str) or not 1 <= len(source.encode()) <= MAX_SOURCE:
        raise ValueError('Algorithm source must be 1 to 100000 bytes')
    module = types.ModuleType(name)
    module.__file__ = '<algorithm-source>'
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    controller = getattr(module, 'CONTROLLER', module)
    if not callable(getattr(controller, 'transition', None)):
        raise ValueError('Source must expose transition(event, private_state)')
    if getattr(controller, 'COMPARISON_FIELDS', None) != FIELDS:
        raise ValueError('This workbench requires the ABI-v0 comparison schema')
    return controller

def json_state(value, label):
    """Require actual bounded JSON data, not arbitrary Python objects or NaN."""
    import math
    def check(v, depth=0):
        if depth > 64:
            raise ValueError(f'{label}: state nesting exceeds 64 levels')
        if v is None or type(v) in (bool, str, int): return
        if type(v) is float and math.isfinite(v): return
        if type(v) is list:
            for item in v: check(item, depth+1)
            return
        if type(v) is dict and all(type(k) is str for k in v):
            for item in v.values(): check(item, depth+1)
            return
        raise ValueError(f'{label}: private state must contain finite JSON values and string keys')
    check(value)
    if len(json.dumps(value, allow_nan=False).encode()) > 131072:
        raise ValueError(f'{label}: private state exceeds 128 KiB')
    return copy.deepcopy(value)


def run_source(source, name, events, execution_mode='event_local', include_states=False, initial_json=None):
    controller = load_source(source, name)
    initial = None
    if execution_mode == 'stateful':
        if hasattr(controller, 'INITIAL_PRIVATE_STATE'):
            initial = json_state(controller.INITIAL_PRIVATE_STATE, name+' initialization')
        elif hasattr(controller, 'NONE_PRIVATE_STATE'):
            initial = json_state(controller.NONE_PRIVATE_STATE, name+' initialization')
        else:
            raise ValueError(name+': stateful mode requires INITIAL_PRIVATE_STATE or NONE_PRIVATE_STATE')
    elif execution_mode != 'event_local':
        raise ValueError('Unknown execution mode')
    if execution_mode == 'stateful' and initial_json is not None:
        initial = json_state(json.loads(initial_json), name+' saved initialization')
    state = copy.deepcopy(initial)
    outputs = []
    states = []
    for event in events:
        before = copy.deepcopy(state)
        returned = controller.transition(copy.deepcopy(event), copy.deepcopy(state))
        if not isinstance(returned, (tuple, list)) or len(returned) != 2:
            raise ValueError('transition must return (output_dict, next_private_state)')
        output, next_state = returned
        if execution_mode == 'event_local' and next_state is not None:
            raise ValueError('Event-local mode requires no private state; select initialized stateful mode')
        state = json_state(next_state, name+' next state')
        if not isinstance(output, dict):
            raise ValueError('transition must return (output_dict, next_private_state)')
        for key in ('result_valid', 'result', 'post_snd_cwnd', 'post_snd_cwnd_cnt'):
            if type(output.get(key)) is not int or not 0 <= output[key] <= 0xffffffff:
                raise ValueError(f'Invalid output field {key}')
        if output['result_valid'] != int(event['callback_id'] != 2):
            raise ValueError('result_valid must match the callback return contract')
        if not 2 <= output['post_snd_cwnd'] <= event['pre_snd_cwnd_clamp']:
            raise ValueError('Output cwnd is outside the permitted range')
        explanation = output.get('decision', {})
        if not isinstance(explanation, dict) or any(not isinstance(v, str) or len(v) > 1000 for v in explanation.values()):
            raise ValueError('decision must contain short plain-text explanations')
        json.dumps(output, allow_nan=False)
        outputs.append(copy.deepcopy(output))
        states.append({'pre': before, 'post': copy.deepcopy(state)})
    return (outputs, states, initial) if include_states else outputs


def compare_sources(source_a, source_b, events, provenance, execution_mode='event_local', initialization=None):
    initialization = initialization or {}
    a, sa, ia = run_source(source_a, 'algorithm_a', events, execution_mode, True, initialization.get('a'))
    b, sb, ib = run_source(source_b, 'algorithm_b', events, execution_mode, True, initialization.get('b'))
    if (a,sa,ia) != run_source(source_a, 'algorithm_a_repeat', events, execution_mode, True, initialization.get('a')) or (b,sb,ib) != run_source(source_b, 'algorithm_b_repeat', events, execution_mode, True, initialization.get('b')):
        raise ValueError('Repeated execution produced different output streams or private states')
    from ccreplay.storage import json_safe
    rows = []
    for i, (event, out_a, out_b) in enumerate(zip(events, a, b)):
        fields = FIELDS[event['callback_id']]
        differences = [key for key in fields if out_a[key] != out_b[key]]
        rows.append({'index': i, 'seq': event['seq'], 'callback': CALLBACKS[event['callback_id']],
                     'input': event, 'a': out_a, 'b': out_b, 'different_fields': differences,
                     'private_a': json_safe(sa[i]), 'private_b': json_safe(sb[i])})
    return {'contract': 'TCP callbacks v0', 'execution_mode': execution_mode, 'provenance': provenance,
            'source_a_sha256': digest(source_a), 'source_b_sha256': digest(source_b),
            'inputs_sha256': digest(events), 'initialization': json_safe({'a':ia,'b':ib}),
            'initialization_sha256': digest({'a':ia,'b':ib}),
            'initialization_json': {'a':json.dumps(ia,allow_nan=False), 'b':json.dumps(ib,allow_nan=False)}, 'warmup_events': 0,
            'repeat_check': 'equal outputs and private states on two fresh loads',
            'compared_events': len(rows), 'disagreements': sum(bool(r['different_fields']) for r in rows),
            'first_difference': next((r['index'] for r in rows if r['different_fields']), None), 'rows': rows}


def capture_window(job):
    """Freeze only the compared inputs; retain exact original recording identity."""
    from ccreplay import traces
    from user.ccreplay_diff import _detect_version_and_parse
    trace_id = job['trace_id']
    if traces.get_abi(trace_id) != 0:
        raise ValueError('These algorithms require a v0 recording')
    path = traces.resolve_id(trace_id)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    _, all_events, select_connection, _ = _detect_version_and_parse(str(path))
    _, events, _ = select_connection(all_events)
    events.sort(key=lambda e: e['seq'])
    total = len(events)
    offset, limit = job.get('offset', 0), job.get('limit', 100)
    if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= MAX_EVENTS:
        raise ValueError('Invalid recording window')
    if job.get('execution_mode','event_local') == 'stateful' and offset != 0:
        raise ValueError('Stateful recorded windows must start at index 0 to establish initialized private history; prefix warmup is not supported')
    events = events[offset:offset + limit]
    if not events:
        raise ValueError('Recording window is empty')
    if hashlib.sha256(path.read_bytes()).hexdigest() != before:
        raise ValueError('Recording changed while copying inputs')
    return {'events': events, 'inputs_sha256': digest(events), 'provenance': {
        'kind': 'recording', 'label': trace_id, 'start_index':offset,
        'scope': f'Connection window [{offset}, {offset + len(events)}) of {total} events',
        'trace_sha256': before, 'snapshot': 'Immutable compared callback inputs'}}


def run_job(job):
    if os.environ.get('CCREPLAY_DEMO_MODE') == '1':
        raise ValueError('Custom execution requires the local application')
    if job.get('input_kind', 'scenario') == 'scenario':
        scenario = job['scenario']
        events = validate_scenario(scenario)
        provenance = {'kind': 'synthetic', 'label': str(scenario.get('name', 'Custom input sequence'))[:200], 'scope': 'Complete supplied sequence'}
    elif job['input_kind'] == 'recording':
        snapshot = job.get('recording_snapshot')
        if snapshot is None:
            snapshot = capture_window(job)
        if job.get('execution_mode','event_local') == 'stateful' and (job.get('offset',0) != 0 or snapshot['provenance'].get('start_index',0) != 0):
            raise ValueError('Stateful recorded windows must start at index 0; prefix warmup is not supported')
        events = snapshot['events']
        if digest(events) != snapshot['inputs_sha256']:
            raise ValueError('Saved recording input hash changed')
        provenance = snapshot['provenance']
    else:
        raise ValueError('Unknown input kind')
    return compare_sources(job['source_a'], job['source_b'], events, provenance, job.get('execution_mode','event_local'), job.get('_initialization_json'))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run two independent teaching controllers')
    parser.add_argument('--algorithm-a', required=True, type=Path)
    parser.add_argument('--algorithm-b', required=True, type=Path)
    parser.add_argument('--scenario', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    result = run_job({'source_a': args.algorithm_a.read_text(), 'source_b': args.algorithm_b.read_text(),
                      'scenario': json.loads(args.scenario.read_text())})
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(f"Compared {result['compared_events']} events; {result['disagreements']} differ; first index {result['first_difference']}")
