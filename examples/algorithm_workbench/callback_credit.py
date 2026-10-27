"""Independent teaching policy: grow once per three eligible callback invocations."""
INITIAL_PRIVATE_STATE = {'eligible_callbacks': 0}
COMPARISON_FIELDS = {1: ['result','post_snd_cwnd','post_snd_cwnd_cnt'],
                     2: ['post_snd_cwnd','post_snd_cwnd_cnt'],
                     3: ['result','post_snd_cwnd','post_snd_cwnd_cnt']}


def transition(event, private_state):
    count = private_state['eligible_callbacks']
    cwnd = event['pre_snd_cwnd']
    if event['callback_id'] == 2 and event['pre_is_cwnd_limited'] and event['in_acked']:
        count += 1
        if count >= 3:
            cwnd = min(event['pre_snd_cwnd_clamp'], cwnd + 1)
            count = 0
    result = max(2, event['pre_snd_ssthresh']) if event['callback_id'] == 1 else max(cwnd, event['pre_prior_cwnd']) if event['callback_id'] == 3 else 0
    return {'result_valid': int(event['callback_id'] != 2), 'result': result,
            'post_snd_cwnd': cwnd, 'post_snd_cwnd_cnt': event['pre_snd_cwnd_cnt']}, {'eligible_callbacks': count}
