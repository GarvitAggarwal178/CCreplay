from copy import deepcopy
from types import SimpleNamespace
import json
import random
import pytest
from ccreplay import controllers,replay_session as sessions
from ccreplay.transitions import iterate
from user.ccreplay_diff import _detect_version_and_parse,_initial_state

@pytest.fixture(scope='module')
def cubic_events():
    _,events,select,_=_detect_version_and_parse('raw/cubic_replay/primary/rep1.ccr')
    _,events,_=select(events)
    return sorted(events,key=lambda e:e['seq'])

@pytest.mark.parametrize('mode',['A','B'])
def test_both_modes_exact_random_indices_against_sequential_models(cubic_events,mode):
    ref=controllers.load_controller('cubic');cand=controllers.make_param('cubic','unusual',{'BETA':823})
    trusted=controllers.load_controller('cubic')
    selected=set(random.Random(12).sample(range(2500),15))|{0,2499}
    output={i:(r,c,rn,cn) for i,e,r,c,rp,cp,rn,cn,f,d,ca in iterate(cubic_events[:2500],ref,cand,trusted,mode) if i in selected}
    rs,cs=_initial_state(ref),_initial_state(cand)
    for i,e in enumerate(cubic_events[:2500]):
        if mode=='A':rs=trusted.private_pre_from_event(e);cs=trusted.private_pre_from_event(e)
        rc,rs=ref.transition(deepcopy(e),deepcopy(rs));cc,cs=cand.transition(deepcopy(e),deepcopy(cs))
        if i in selected:assert output[i]==(rc,cc,rs,cs)


def test_mutating_candidate_cannot_change_cache_reference_or_later_run(cubic_events):
    event=deepcopy(cubic_events[0]);original=deepcopy(event)
    ref=controllers.load_controller('cubic');base=controllers.load_controller('cubic')
    def mutate(e,state):
        result,n=base.transition(e,state)
        e['pre_snd_cwnd']=123456789
        if state is not None:state['cnt']=999
        return result,n
    candidate=SimpleNamespace(transition=mutate,INITIAL_PRIVATE_STATE=deepcopy(base.INITIAL_PRIVATE_STATE))
    rows=list(iterate([event],ref,candidate,ref,'B'))
    assert event==original
    assert rows[0][2]==controllers.load_controller('cubic').transition(deepcopy(original),_initial_state(ref))[0]


def test_full_computed_stream_persistence_and_checkpoint(tmp_path,monkeypatch):
    monkeypatch.setattr(sessions,'SESSIONS',tmp_path)
    sid=sessions.create('raw__cubic_replay__primary__rep1','cubic','cubic_bug_ssthresh')
    summary=sessions.run(sid)
    assert summary['n_events']==78688 and summary['first_difference']['event_index']==1704
    profile=summary['comparison_profile_v1']
    assert profile['types']['return_value']==14 and profile['types']['private_only']==0
    assert profile['metrics']['ssthresh.result']['count']==summary['callback_counts']['ssthresh']
    assert profile['metrics']['ssthresh.result']['mean_absolute_delta']==1
    event=sessions.detail(sid,1704)
    assert event['seq']=='1705'
    assert (event['reference']['computed']['result'],event['candidate']['computed']['result'])==(145,146)
    assert sessions.detail(sid,1703)['diff_fields']==[]
    assert sessions.detail(sid,1705)['diff_fields']==[]
    ck=sessions.checkpoint(sid,500)
    assert ck['values_and_private_state_verified'] and ck['nearest_checkpoint']['next_event_index']==1500
    assert ck['suffix_length']==205  # 1500..1704 inclusive
    aligned=sessions.checkpoint(sid,1704)  # divergence exactly on the checkpoint boundary
    assert aligned['nearest_checkpoint']['next_event_index']==1704 and aligned['suffix_length']==1
    assert aligned['values_and_private_state_verified']
    assert sessions.event_rows(sid,0,1,differences_only=True,anchor=1704)['events'][0]['index']>1704
    with pytest.raises(KeyError):sessions.detail(sid,78688)
    with pytest.raises(ValueError):sessions.event_rows(sid,-1,10)


def test_mode_dependent_comparison_never_unions_dead_reference_arm():
    from ccreplay.transitions import required_fields
    trusted=controllers.load_controller('covegas')
    event={'callback_id':2,'priv_pre_mode':1}
    ref={'priv_post_mode':0};cand={'priv_post_mode':1}
    assert required_fields(trusted,event,ref,cand)==trusted.comparison_fields(2,1,0)
