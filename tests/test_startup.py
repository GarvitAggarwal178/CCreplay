"""The root exception is explicit and requires the fixed-loopback launcher."""
import pytest
from backend import app as studio


@pytest.fixture
def startup(monkeypatch):
    calls = []
    monkeypatch.setattr(studio.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(studio.app.state, 'root_loopback_launcher', False, raising=False)
    monkeypatch.setattr(studio.jobs, 'reconcile', lambda: calls.append('reconcile'))
    monkeypatch.delenv('CCREPLAY_ALLOW_ROOT', raising=False)
    return calls


@pytest.mark.parametrize('override', [None, '', '0', 'true'])
def test_root_refused_by_default(startup, monkeypatch, override):
    if override is not None:
        monkeypatch.setenv('CCREPLAY_ALLOW_ROOT', override)
    with pytest.raises(RuntimeError, match='normal user'):
        studio.reconcile_jobs()
    assert not startup


def test_root_override_rejects_unverified_asgi_binding(startup, monkeypatch):
    monkeypatch.setenv('CCREPLAY_ALLOW_ROOT', '1')
    with pytest.raises(RuntimeError, match='loopback-only launcher'):
        studio.reconcile_jobs()
    assert not startup


def test_explicit_loopback_override_warns_and_starts(startup, monkeypatch, caplog):
    monkeypatch.setenv('CCREPLAY_ALLOW_ROOT', '1')
    monkeypatch.setattr(studio.app.state, 'root_loopback_launcher', True)
    studio.reconcile_jobs()
    assert startup == ['reconcile']
    assert 'ROOT PRIVILEGES' in caplog.text and '127.0.0.1' in caplog.text


def test_normal_user_unchanged(startup, monkeypatch):
    monkeypatch.setattr(studio.os, 'geteuid', lambda: 1000)
    studio.reconcile_jobs()
    assert startup == ['reconcile']
