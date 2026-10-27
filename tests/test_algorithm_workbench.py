import copy
import json
from pathlib import Path
import pytest
from ccreplay.teaching_workbench import run_job, validate_scenario

SAMPLES = Path(__file__).resolve().parents[1] / 'examples' / 'algorithm_workbench'

def job():
    return {'source_a': (SAMPLES / 'step_growth.py').read_text(),
            'source_b': (SAMPLES / 'batch_growth.py').read_text(),
            'scenario': json.loads((SAMPLES / 'scenario.json').read_text())}

def test_hand_calculated_results_and_callback_semantics():
    result = run_job(job())
    assert result['compared_events'] == 12
    assert result['disagreements'] == 5
    assert result['first_difference'] == 1
    assert [(r['a']['post_snd_cwnd'], r['b']['post_snd_cwnd']) for r in result['rows']] == [
        (13,13),(13,15),(19,22),(18,18),(18,18),(20,20),
        (24,24),(2,2),(16,16),(100,100),(20,20),(33,36)]
    assert [(result['rows'][i]['a']['result'], result['rows'][i]['b']['result']) for i in (6,7,8,9)] == [(16,20),(2,2),(24,24),(66,90)]
    assert result['rows'][6]['a']['post_snd_cwnd'] == 24  # ssthresh only returns a value
    assert result['rows'][1]['input']['pre_snd_cwnd'] == 12  # no feedback from event 0
    assert result['rows'][1]['b']['decision']['calculation'] == 'min(100, 12 + 3) = 15'

def test_editing_python_changes_real_output():
    original = job()
    edited = copy.deepcopy(original)
    edited['source_b'] = edited['source_b'].replace('increment = min(4, acked)', 'increment = 2')
    first, second = run_job(original), run_job(edited)
    assert first['rows'][1]['b']['post_snd_cwnd'] == 15
    assert second['rows'][1]['b']['post_snd_cwnd'] == 14
    assert first['source_b_sha256'] != second['source_b_sha256']

def test_equal_sources_have_no_differences():
    config = job(); config['source_b'] = config['source_a']
    result = run_job(config)
    assert result['disagreements'] == 0 and result['first_difference'] is None

@pytest.mark.parametrize('change', [lambda x: x.update(provenance='recording'),
    lambda x: x['events'][0].update(in_acked=-1),
    lambda x: x['events'][0].update(pre_is_cwnd_limited=2),
    lambda x: x['events'][0].update(callback_id=9),
    lambda x: x['events'][1].update(seq=1),
    lambda x: x['events'][0].update(pre_snd_cwnd_clamp=1)])
def test_invalid_inputs_are_rejected(change):
    scenario = job()['scenario']; change(scenario)
    with pytest.raises(ValueError): validate_scenario(scenario)

def test_sources_cannot_mutate_shared_inputs():
    config = job()
    config['source_a'] = config['source_a'].replace("cwnd = event['pre_snd_cwnd']", "cwnd = event['pre_snd_cwnd']; event['pre_snd_cwnd'] = 99")
    result = run_job(config)
    assert result['rows'][1]['input']['pre_snd_cwnd'] == 12
    assert result['rows'][1]['b']['post_snd_cwnd'] == 15

def test_stateful_source_is_not_silently_misrepresented():
    config = job(); config['source_a'] = config['source_a'].replace('return output, None', "return output, {'counter': 1}")
    with pytest.raises(ValueError, match='no private state'): run_job(config)

def test_no_false_determinism_claim(tmp_path):
    config = job()
    marker = repr(str(tmp_path / 'counter'))
    config['source_a'] = "from pathlib import Path\np = Path(" + marker + ")\np.write_text(str(int(p.read_text()) + 1) if p.exists() else '1')\nCOUNT = int(p.read_text())\n" + config['source_a']
    config['source_a'] = config['source_a'].replace("output['decision'] =", "output['post_snd_cwnd_cnt'] = COUNT\n    output['decision'] =")
    with pytest.raises(ValueError, match='different output streams'): run_job(config)

def test_api_demo_mode_blocks_execution(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.algorithm_workbench import router
    monkeypatch.setenv('CCREPLAY_DEMO_MODE', '1')
    app = FastAPI(); app.include_router(router)
    with TestClient(app) as client:
        assert client.get('/api/algorithm-workbench/presets').status_code == 200
        assert client.post('/api/algorithm-workbench/compare', json=job()).status_code == 403

def test_api_validates_without_running_source(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.algorithm_workbench import router, jobs
    captured = []
    monkeypatch.delenv('CCREPLAY_DEMO_MODE', raising=False)
    monkeypatch.setattr(jobs, 'create_experiment', lambda kind, config: captured.append((kind, config)) or 'sample')
    app = FastAPI(); app.include_router(router)
    config = job(); config['source_a'] = "raise RuntimeError('must only run in child')"
    with TestClient(app) as client:
        response = client.post('/api/algorithm-workbench/compare', json=config)
        assert response.status_code == 200 and response.json()['id'] == 'sample'
    assert captured[0][1]['source_a'] == config['source_a']

def test_real_api_to_worker_to_saved_result(monkeypatch, tmp_path):
    import time
    from fastapi.testclient import TestClient
    from backend.app import app
    from backend import jobs
    monkeypatch.delenv('CCREPLAY_DEMO_MODE', raising=False)
    monkeypatch.setattr(jobs, 'DB_PATH', tmp_path / 'studio.db')
    (tmp_path / 'jobs').mkdir()
    monkeypatch.setattr(jobs, 'JOBS_DIR', tmp_path / 'jobs')
    client = TestClient(app)
    response = client.post('/api/algorithm-workbench/compare', json=job())
    assert response.status_code == 200
    identifier = response.json()['id']
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        saved = client.get('/api/experiments/' + identifier).json()
        if saved['status'] in ('done', 'error'): break
        time.sleep(.02)
    assert saved['status'] == 'done', saved
    assert saved['result']['rows'][1]['a']['post_snd_cwnd'] == 13
    assert saved['result']['rows'][1]['b']['post_snd_cwnd'] == 15
    assert saved['config']['source_a'] == job()['source_a']
    exported = client.get('/api/experiments/' + identifier + '/export').json()
    assert exported['result'] == saved['result']


def test_worker_demo_mode_cannot_be_bypassed_by_rerun(monkeypatch):
    monkeypatch.setenv('CCREPLAY_DEMO_MODE', '1')
    with pytest.raises(ValueError, match='local application'): run_job(job())


def test_recorded_window_is_immutable_and_hash_checked(monkeypatch):
    from ccreplay.teaching_workbench import capture_window
    from ccreplay import traces
    config = job()
    config.update(input_kind='recording', trace_id='raw__r0__rep1', offset=0, limit=100)
    config['recording_snapshot'] = capture_window(config)
    monkeypatch.setattr(traces, 'resolve_id', lambda _: (_ for _ in ()).throw(FileNotFoundError('removed')))
    result = run_job(config)
    assert result['compared_events'] == 100
    assert result['disagreements'] == 29
    assert 'of 37260 events' in result['provenance']['scope']
    config['recording_snapshot']['events'][0]['in_acked'] += 1
    with pytest.raises(ValueError, match='input hash changed'):
        run_job(config)


def test_demo_mode_rejects_saved_rerun_at_route(monkeypatch):
    from backend.app import app
    from backend import jobs
    from fastapi.testclient import TestClient
    monkeypatch.setenv('CCREPLAY_DEMO_MODE', '1')
    monkeypatch.setattr(jobs, 'get_experiment', lambda _: {'type': 'algorithm_workbench', 'config': job()})
    assert TestClient(app).post('/api/experiments/saved/rerun').status_code == 403


def test_hanging_source_is_killed_by_existing_worker(tmp_path, monkeypatch):
    from backend import jobs
    monkeypatch.setattr(jobs, 'JOBS_DIR', tmp_path)
    config = job()
    config.update(type='algorithm_workbench', source_a='while True: pass')
    result = jobs._run_worker_subprocess(config, timeout_s=.2)
    assert result['ok'] is False and 'timed out' in result['error'].lower()
