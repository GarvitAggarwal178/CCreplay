"""BatchGrowth: an independent teaching policy, not a Linux implementation.
No slow-start phase or private state; ABI v0 is only the input/output contract.
The next event receives its recorded PRE values, not this policy's last cwnd.
"""
from math import isqrt
from types import SimpleNamespace

NONE_PRIVATE_STATE = None
COMPARISON_FIELDS = {1: ['result', 'post_snd_cwnd', 'post_snd_cwnd_cnt'],
                     2: ['post_snd_cwnd', 'post_snd_cwnd_cnt'],
                     3: ['result', 'post_snd_cwnd', 'post_snd_cwnd_cnt']}

def transition(event, private_state):
    cwnd = event['pre_snd_cwnd']
    acked = event['in_acked']
    clamp = event['pre_snd_cwnd_clamp']
    callback = event['callback_id']
    output = {'result_valid': int(callback != 2), 'result': 0,
              'post_snd_cwnd': cwnd,
              'post_snd_cwnd_cnt': event['pre_snd_cwnd_cnt']}
    if callback == 1:
        output['result'] = max(2, cwnd - isqrt(cwnd))
        rule = 'Loss threshold'
        calculation = f'max(2, {cwnd} - isqrt({cwnd})) = {output["result"]}'
        meaning = 'Returned threshold; this callback does not assign cwnd.'
    elif callback == 2:
        if not event['pre_is_cwnd_limited'] or acked == 0:
            rule = 'Hold window'
            calculation = f'Window stays at {cwnd}: no eligible growth.'
        else:
            increment = min(4, acked)
            output['post_snd_cwnd'] = min(clamp, cwnd + increment)
            rule = 'Growth from acknowledged batch, capped at four'
            calculation = f'min({clamp}, {cwnd} + {increment}) = {output["post_snd_cwnd"]}'
        meaning = 'Computed post-callback cwnd for this input only.'
    elif callback == 3:
        output['result'] = max(cwnd, event['pre_prior_cwnd'])
        rule = 'Undo threshold'
        calculation = f'max({cwnd}, {event["pre_prior_cwnd"]}) = {output["result"]}'
        meaning = 'Returned undo value; this callback does not assign cwnd.'
    else:
        raise ValueError('Unsupported callback')
    output['decision'] = {'rule': rule, 'calculation': calculation, 'meaning': meaning}
    return output, None

CONTROLLER = SimpleNamespace(__name__='batch_growth', transition=transition,
    NONE_PRIVATE_STATE=None, COMPARISON_FIELDS=COMPARISON_FIELDS)
