"""Actual builtin-source editor adapter must survive complete replay/checkpoints."""
from ccreplay import controllers, replay_session as sessions
from user.ccreplay_diff import diff_trace


def test_namespace_editor_source_and_saved_capsule_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(controllers, 'USER_DIR', tmp_path / 'controllers')
    controllers.USER_DIR.mkdir()
    monkeypatch.setattr(sessions, 'SESSIONS', tmp_path / 'sessions')
    source = controllers.get_source('reno') + "\nfrom types import SimpleNamespace\nCONTROLLER = SimpleNamespace(**{key: globals()[key] for key in ('transition','INITIAL_PRIVATE_STATE','NONE_PRIVATE_STATE','COMPARISON_FIELDS','comparison_fields') if key in globals()})\n"
    cid = controllers.save_user_controller('actual_editor', 'reno', source)
    original = (controllers.USER_DIR / (cid+'.py')).read_bytes()
    assert controllers.validate_controller(cid)['ok']
    assert diff_trace('raw/r0/rep1.ccr', None, controllers.load_controller('reno'), controllers.load_controller(cid))['result'] == 'NO DIVERGENCE'
    sid = sessions.create('raw__r0__rep1', 'reno', cid, 'B')
    assert sessions.run(sid)['n_disagree'] == 0
    sid_a = sessions.create('raw__r0__rep1', 'reno', cid, 'A')
    assert sessions.run(sid_a)['n_disagree'] == 0
    # Completed run reloads the saved namespace source, independent of the registry file.
    (controllers.USER_DIR / (cid+'.py')).unlink()
    rerun = sessions.create(None, None, None, original=sessions.read(sid))
    assert sessions.run(rerun)['n_disagree'] == 0
    changed = source.replace('max(pre["snd_cwnd"] >> 1, 2), private_state', '(max(pre["snd_cwnd"] >> 1, 2) + 1), private_state')
    assert changed != source
    candidate = controllers.save_user_controller('edited_rule', 'reno', changed)
    assert controllers.validate_controller(candidate)['ok']
    bad = sessions.create('raw__r0__rep1', 'reno', candidate, 'B')
    summary = sessions.run(bad)
    assert summary['n_disagree'] > 0
    assert sessions.checkpoint(bad, 500)['values_and_private_state_verified']
    event = sessions.detail(bad, summary['first_difference']['event_index'])
    assert event['candidate']['computed']['result'] == event['reference']['computed']['result'] + 1
    assert original.decode() == source
