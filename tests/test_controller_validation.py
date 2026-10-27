import pytest
from ccreplay import controllers

@pytest.mark.parametrize('params',[{'BETAA':819},{'BETA':True},{'BETA':819.2}])
def test_parameter_edits_reject_silent_typos_and_coercion(params):
    with pytest.raises(ValueError):
        controllers.make_param('cubic','test',params)

def test_complete_stream_and_reuse_catch_hidden_counter(tmp_path,monkeypatch):
    monkeypatch.setattr(controllers,'USER_DIR',tmp_path)
    source='''from ccreplay.controllers import clone_base
base=clone_base("cubic","counter")
original=base.transition
counter=0
def transition(event,state):
 global counter
 counter+=1
 computed,next_state=original(event,state)
 computed["post_snd_cwnd"]+=counter
 return computed,next_state
base.transition=transition
CONTROLLER=base
'''
    cid=controllers.save_user_controller('counter','cubic',source)
    result=controllers.validate_controller(cid)
    assert not result['ok']
    assert any(c['name']=='deterministic_rerun' and not c['ok'] for c in result['checks'])

def test_per_event_missing_field_cannot_hide_in_union(tmp_path,monkeypatch):
    monkeypatch.setattr(controllers,'USER_DIR',tmp_path)
    source=controllers.get_template('cubic').replace('return computed, next_ca','''if event["seq"] % 2:
        computed.pop("post_snd_cwnd",None)
    return computed, next_ca''')
    cid=controllers.save_user_controller('missing','cubic',source)
    result=controllers.validate_controller(cid)
    assert not result['ok']
    assert 'missing required fields' in str(result)

def test_saving_another_source_never_overwrites_old_revision(tmp_path,monkeypatch):
    monkeypatch.setattr(controllers,'USER_DIR',tmp_path)
    a=controllers.save_user_controller('same','cubic',controllers.get_template('cubic'))
    b=controllers.save_user_controller('same','cubic',controllers.get_template('cubic').replace('OFFSET = 0','OFFSET = 1'))
    assert a!=b
    assert 'OFFSET = 0' in controllers.get_source(a)


def test_saved_source_dependency_changes_refuse_instead_of_substitute(monkeypatch,tmp_path):
    from ccreplay import revisions
    monkeypatch.setattr(controllers,'PARAM_STORE',tmp_path/'params.json')
    cid=controllers.save_param_variant('cubic','identity_test',{'BETA':823})
    cap=revisions.snapshot(cid)
    cap['dependencies']['ccreplay/controllers.py']='0'*64
    with pytest.raises(ValueError,match='dependency changed'):
        revisions.verify(cap)
