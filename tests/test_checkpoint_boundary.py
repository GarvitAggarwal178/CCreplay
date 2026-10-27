"""Checkpoint save/resume boundary regression.

Convention (schema 2): a checkpoint stores next_event_index K and private
state immediately before event K; resume executes K..D inclusive. The
pre-fix code stored the same state but resumed at K+1, skipping event K.
"""
import types
from copy import deepcopy

import pytest

import user.ccreplay_checkpoint as ck

N_EVENTS = 12


def _model(name, bug_at=None):
    """Stateful counter: result depends on how many transitions ran before,
    so skipping any transition shifts every later value."""
    mod = types.SimpleNamespace(__name__=name, INITIAL_PRIVATE_STATE={"n": 0},
                                COMPARISON_FIELDS={1: ["result"]})

    def transition(event, private):
        n = private["n"] + 1
        result = n + (1 if bug_at is not None and n == bug_at else 0)
        return {"result": result}, {"n": n}

    mod.transition = transition
    return mod


@pytest.fixture
def synthetic(monkeypatch):
    events = [{"seq": i, "callback_id": 1} for i in range(N_EVENTS)]
    monkeypatch.setattr(ck, "_detect_version_and_parse", lambda _: (
        types.SimpleNamespace(trace_version=0), events,
        lambda es: (1, deepcopy(es), []), {1: "counter_transition"}))
    return events


def _reproduce(interval, bug_at):
    ref, cand = _model("reference"), _model("candidate", bug_at)
    cps, full, dom, _ = ck.run_with_checkpoints("synthetic", ref, cand, interval)
    D = full["event_index"]
    cp = ck.nearest_checkpoint_at_or_before(cps, D)
    return cp, full, ck.replay_suffix_from_checkpoint(cp, dom, ref, cand, D), D


def test_difference_after_checkpoint_boundary(synthetic):
    # bug on 6th transition -> D=5; interval 2 -> checkpoint before event 4 (n=4)
    cp, full, resumed, D = _reproduce(2, 6)
    assert D == 5 and cp["next_event_index"] == 4 and cp["ref_state"] == {"n": 4}
    assert resumed is not None and ck.same_divergence(full, resumed)
    assert (resumed["ref_computed"], resumed["cand_computed"]) == ({"result": 6}, {"result": 7})
    assert resumed["ref_post_state"] == resumed["cand_post_state"] == {"n": 6}
    assert ck.suffix_length(cp, D) == 2


def test_difference_exactly_on_checkpoint_boundary(synthetic):
    # D=4 coincides with the checkpoint's next event: that event must execute.
    cp, full, resumed, D = _reproduce(2, 5)
    assert D == 4 and cp["next_event_index"] == 4
    assert resumed is not None and ck.same_divergence(full, resumed)
    assert ck.suffix_length(cp, D) == 1


def test_first_event_difference_uses_initial_state(synthetic):
    cp, full, resumed, D = _reproduce(3, 1)
    assert D == 0 and cp["next_event_index"] == 0 and cp["ref_state"] == {"n": 0}
    assert ck.same_divergence(full, resumed)


def test_last_event_difference(synthetic):
    cp, full, resumed, D = _reproduce(5, N_EVENTS)
    assert D == N_EVENTS - 1 and cp["next_event_index"] == 10
    assert ck.same_divergence(full, resumed) and ck.suffix_length(cp, D) == 2


def test_every_interval_reproduces_exactly(synthetic):
    for interval in range(1, N_EVENTS + 1):
        cp, full, resumed, D = _reproduce(interval, 7)
        assert ck.same_divergence(full, resumed), interval


def test_old_schema_checkpoint_rejected(synthetic):
    ref, cand = _model("reference"), _model("candidate", 6)
    cps, full, dom, _ = ck.run_with_checkpoints("synthetic", ref, cand, 2)
    old = dict(cps[2], schema_version=1)
    with pytest.raises(ValueError, match="schema_version"):
        ck.replay_suffix_from_checkpoint(old, dom, ref, cand, full["event_index"])


def test_same_divergence_compares_values_not_just_position(synthetic):
    ref, cand = _model("reference"), _model("candidate", 6)
    _, full, _, _ = ck.run_with_checkpoints("synthetic", ref, cand, 2)
    forged = dict(full, cand_computed={"result": 99})
    assert not ck.same_divergence(full, forged)
    assert not ck.same_divergence(full, dict(full, ref_post_state={"n": 0}))
    assert not ck.same_divergence(full, None)


def test_pre_fix_resume_would_miss_difference(synthetic):
    """Failure-proof: emulate the old K+1 resume and show it loses the diff."""
    ref, cand = _model("reference"), _model("candidate", 6)
    cps, full, dom, _ = ck.run_with_checkpoints("synthetic", ref, cand, 2)
    cp = ck.nearest_checkpoint_at_or_before(cps, full["event_index"])
    skipped = dict(cp, next_event_index=cp["next_event_index"] + 1)
    assert ck.replay_suffix_from_checkpoint(skipped, dom, ref, cand, full["event_index"]) is None
