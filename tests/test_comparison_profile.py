"""Derived summaries must preserve callback denominators and distinct units/types."""
from ccreplay.replay_session import accumulate_profile
from backend import lab
from fastapi import HTTPException
import pytest


def test_profile_separates_private_return_and_computed_window():
    p = {}
    accumulate_profile(p, 'ssthresh', {'result': 10}, {'result': 12}, ['result'], ['result'])
    accumulate_profile(p, 'ssthresh', {'result': 10}, {'result': 7}, ['result'], ['result'])
    accumulate_profile(p, 'ssthresh', {'result': 10}, {'result': 10}, ['result'], [])
    accumulate_profile(p, 'cong_avoid', {'post_snd_cwnd': 20, 'priv_post_cnt': 1},
                       {'post_snd_cwnd': 20, 'priv_post_cnt': 999}, ['post_snd_cwnd', 'priv_post_cnt'], ['priv_post_cnt'])
    assert p['types'] == {'private_only': 1, 'return_value': 2, 'computed_post': 0}
    m = p['metrics']['ssthresh.result']
    assert (m['count'], m['changed'], m['min_delta'], m['max_delta'], m['max_absolute_delta']) == (3, 2, -3, 2, 3)
    assert m['mean_absolute_delta'] == pytest.approx(5 / 3)
    assert p['metrics']['cong_avoid.post_snd_cwnd']['max_absolute_delta'] == 0
    assert not any('priv' in k for k in p['metrics'])


def test_profile_ignores_nonfinite_absent_and_nonreturn_results():
    p = {}
    for v in [None, True, float('nan'), float('inf')]:
        accumulate_profile(p, 'ssthresh', {'result': v}, {'result': 2}, ['result'], [])
    accumulate_profile(p, 'cong_avoid', {'result': 1, 'post_snd_cwnd': 10},
                       {'result': 2, 'post_snd_cwnd': 14}, ['post_snd_cwnd'], ['post_snd_cwnd'])
    assert list(p['metrics']) == ['cong_avoid.post_snd_cwnd']
    assert p['types']['computed_post'] == 1


@pytest.mark.parametrize('status,capture,instrumentation', [('running', False, 'native-uninstrumented'), ('completed', True, 'recorded-wrapper')])
def test_native_comparison_rejects_ineligible_runs(monkeypatch, status, capture, instrumentation):
    monkeypatch.setattr(lab, 'get_run', lambda rid: {'status': status, 'instrumentation': instrumentation, 'config': {'capture': capture}})
    with pytest.raises(HTTPException):
        lab.compare('left', 'right')


def test_native_comparison_preserves_expected_controller_difference(monkeypatch):
    def run(rid):
        return {'id': rid, 'status': 'completed', 'instrumentation': 'native-uninstrumented',
                'config': {'controller': rid, 'capture': False, 'rate_mbit': 10}}
    monkeypatch.setattr(lab, 'get_run', run)
    monkeypatch.setattr(lab, 'cursor_data', lambda *args: {'items': []})
    result = lab.compare('reno', 'cubic')
    assert list(result['configuration_differences']) == ['controller']
    with pytest.raises(HTTPException):
        lab.compare('reno', 'reno')
