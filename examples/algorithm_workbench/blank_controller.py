"""Trusted local callback policy, ABI v0. Shared PRE inputs are always recorded.

Edit transition's numeric outputs. Select initialized stateful mode to carry
JSON private state; supply INITIAL_PRIVATE_STATE instead of NONE_PRIVATE_STATE.
Each side owns its state. A returned threshold does not assign post cwnd.
"""
NONE_PRIVATE_STATE = None
COMPARISON_FIELDS = {
    1: ['result', 'post_snd_cwnd', 'post_snd_cwnd_cnt'],
    2: ['post_snd_cwnd', 'post_snd_cwnd_cnt'],
    3: ['result', 'post_snd_cwnd', 'post_snd_cwnd_cnt'],
}


def transition(event, private_state):
    callback = event['callback_id']
    result = 0
    if callback == 1:
        result = max(2, event['pre_snd_ssthresh'])
    elif callback == 3:
        result = max(event['pre_snd_cwnd'], event['pre_prior_cwnd'])
    return {
        'result_valid': int(callback != 2), 'result': result,
        'post_snd_cwnd': event['pre_snd_cwnd'],
        'post_snd_cwnd_cnt': event['pre_snd_cwnd_cnt'],
    }, private_state
