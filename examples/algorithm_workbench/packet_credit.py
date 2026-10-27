"""Independent teaching policy: grow once per four eligible acknowledged packets."""
INITIAL_PRIVATE_STATE = {'ack_credit': 0}
COMPARISON_FIELDS = {1: ['result','post_snd_cwnd','post_snd_cwnd_cnt'],
                     2: ['post_snd_cwnd','post_snd_cwnd_cnt'],
                     3: ['result','post_snd_cwnd','post_snd_cwnd_cnt']}


def transition(event, private_state):
    credit = private_state['ack_credit']
    cwnd = event['pre_snd_cwnd']
    if event['callback_id'] == 2 and event['pre_is_cwnd_limited']:
        credit += event['in_acked']
        cwnd = min(event['pre_snd_cwnd_clamp'], cwnd + credit // 4)
        credit %= 4
    result = max(2, event['pre_snd_ssthresh']) if event['callback_id'] == 1 else max(cwnd, event['pre_prior_cwnd']) if event['callback_id'] == 3 else 0
    return {'result_valid': int(event['callback_id'] != 2), 'result': result,
            'post_snd_cwnd': cwnd, 'post_snd_cwnd_cnt': event['pre_snd_cwnd_cnt']}, {'ack_credit': credit}
