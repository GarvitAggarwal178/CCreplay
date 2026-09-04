"""Userspace Reno replay model.

Implements tcp_is_cwnd_limited / tcp_slow_start / tcp_cong_avoid_ai exactly
as the target kernel's real tcp_reno_* functions behave, per the exact
field set and gating logic empirically discovered and validated in
data/capability_audit.md section F (100.0000% exact match on 24,651 real
kernel cong_avoid events before this model was ever used for a gate) and
section E (ssthresh/undo_cwnd formulas, 5/5 and 8/8 real events).

Reno has NO controller-private state (ADR-014): every field this model
reads or writes is classified SharedTcpPreState / ControllerOwnedPostState
in docs/REPLAY_ABI.md. This module exposes a `NONE_PRIVATE_STATE` sentinel
purely so Mode B (replay_r2.py) can thread "current private state" through
its loop per docs/SEMANTICS.md's algorithm shape, without inventing any
actual state (RECORDER.md: "do not invent private state merely because the
generic schema supports it").
"""

NONE_PRIVATE_STATE = None  # Reno has no controller-private state (ADR-014)


def tcp_is_cwnd_limited(cwnd, ssthresh, max_packets_out, is_cwnd_limited_bit):
    if cwnd < ssthresh:  # tcp_in_slow_start
        return cwnd < 2 * max_packets_out
    return bool(is_cwnd_limited_bit)


def tcp_slow_start(cwnd, ssthresh, clamp, acked):
    new_cwnd = min(cwnd + acked, ssthresh)
    acked -= (new_cwnd - cwnd)
    new_cwnd = min(new_cwnd, clamp)
    return new_cwnd, acked


def tcp_cong_avoid_ai(cwnd, cwnd_cnt, clamp, w, acked):
    if cwnd_cnt >= w:
        cwnd_cnt = 0
        cwnd += 1
    cwnd_cnt += acked
    if cwnd_cnt >= w:
        delta = cwnd_cnt // w
        cwnd_cnt -= delta * w
        cwnd += delta
    cwnd = min(cwnd, clamp)
    return cwnd, cwnd_cnt


def model_cong_avoid(pre, ack, acked, private_state):
    """Returns (post_snd_cwnd, post_snd_cwnd_cnt, next_private_state).
    `private_state` is accepted and returned unchanged -- Reno has none
    (ADR-014) -- purely so Mode B's loop shape matches docs/SEMANTICS.md
    for a controller that does carry private state.
    """
    cwnd = pre["snd_cwnd"]
    ssthresh = pre["snd_ssthresh"]
    cwnd_cnt = pre["snd_cwnd_cnt"]
    clamp = pre["snd_cwnd_clamp"]
    max_packets_out = pre["max_packets_out"]
    is_lim = pre["is_cwnd_limited"]

    if not tcp_is_cwnd_limited(cwnd, ssthresh, max_packets_out, is_lim):
        return cwnd, cwnd_cnt, private_state

    if cwnd < ssthresh:  # slow start
        cwnd, acked = tcp_slow_start(cwnd, ssthresh, clamp, acked)
        if acked == 0:
            return cwnd, cwnd_cnt, private_state

    cwnd, cwnd_cnt = tcp_cong_avoid_ai(cwnd, cwnd_cnt, clamp, cwnd, acked)
    return cwnd, cwnd_cnt, private_state


def model_ssthresh(pre, private_state):
    """Returns (result, next_private_state). tcp_reno_ssthresh: pure
    function of snd_cwnd, confirmed exactly on 5/5 real events (capability
    audit section A/E)."""
    return max(pre["snd_cwnd"] >> 1, 2), private_state


def model_undo_cwnd(pre, private_state):
    """Returns (result, next_private_state). tcp_reno_undo_cwnd: pure
    function of snd_cwnd/prior_cwnd, confirmed exactly on 8/8 real events
    (capability audit section E, auxiliary reorder capture)."""
    return max(pre["snd_cwnd"], pre["prior_cwnd"]), private_state


def pre_from_event(e):
    """Extract the model's PRE-state dict from a parsed ccr_event record
    (see user/ccr_trace.py EVENT_FIELDS)."""
    return {
        "snd_cwnd": e["pre_snd_cwnd"],
        "snd_ssthresh": e["pre_snd_ssthresh"],
        "snd_cwnd_cnt": e["pre_snd_cwnd_cnt"],
        "snd_cwnd_clamp": e["pre_snd_cwnd_clamp"],
        "max_packets_out": e["pre_max_packets_out"],
        "is_cwnd_limited": e["pre_is_cwnd_limited"],
        "prior_cwnd": e["pre_prior_cwnd"],
    }


CCR_CB_SSTHRESH = 1
CCR_CB_CONG_AVOID = 2
CCR_CB_UNDO_CWND = 3


def transition(event, private_state):
    """Single dispatch point used by both Mode A (replay_r1.py, called with
    private_state always NONE_PRIVATE_STATE) and Mode B (replay_r2.py,
    called with the threaded-through private_state). Returns a dict of
    computed fields comparable against the recorded event, plus the next
    private_state.
    """
    pre = pre_from_event(event)
    cb = event["callback_id"]

    if cb == CCR_CB_SSTHRESH:
        result, next_state = model_ssthresh(pre, private_state)
        return {
            "result_valid": 1, "result": result,
            "post_snd_cwnd": pre["snd_cwnd"], "post_snd_cwnd_cnt": pre["snd_cwnd_cnt"],
        }, next_state

    if cb == CCR_CB_CONG_AVOID:
        post_cwnd, post_cwnd_cnt, next_state = model_cong_avoid(
            pre, event["in_ack"], event["in_acked"], private_state)
        return {
            "result_valid": 0, "result": 0,
            "post_snd_cwnd": post_cwnd, "post_snd_cwnd_cnt": post_cwnd_cnt,
        }, next_state

    if cb == CCR_CB_UNDO_CWND:
        result, next_state = model_undo_cwnd(pre, private_state)
        return {
            "result_valid": 1, "result": result,
            "post_snd_cwnd": pre["snd_cwnd"], "post_snd_cwnd_cnt": pre["snd_cwnd_cnt"],
        }, next_state

    raise ValueError(f"unknown callback_id {cb}")


# Declared exact semantic comparison schema (docs/CORRECTNESS_ORACLES.md
# "Every R1/R2/R3 report lists: ... fields compared per callback").
COMPARISON_FIELDS = {
    CCR_CB_SSTHRESH: ["result"],
    CCR_CB_CONG_AVOID: ["post_snd_cwnd", "post_snd_cwnd_cnt"],
    CCR_CB_UNDO_CWND: ["result"],
}
CALLBACK_NAMES = {CCR_CB_SSTHRESH: "ssthresh", CCR_CB_CONG_AVOID: "cong_avoid", CCR_CB_UNDO_CWND: "undo_cwnd"}
