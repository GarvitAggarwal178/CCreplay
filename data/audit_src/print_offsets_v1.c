// Ground-truth layout tool for struct ccr_event_v1 (ABI v1), same discipline
// as Phase-1's print_offsets.c: never hand-derive a binary format string.
#include <stdio.h>
#include <stddef.h>
#include <linux/types.h>
#include "../../bpf/ccr_event_v1.h"

#define P(field) printf("%-28s offset=%-4zu size=%-4zu\n", #field, \
	offsetof(struct ccr_event_v1, field), sizeof(((struct ccr_event_v1 *)0)->field))

int main(void)
{
	printf("sizeof(struct ccr_trace_header) = %zu\n", sizeof(struct ccr_trace_header));
#define PH(field) printf("%-28s offset=%-4zu size=%-4zu\n", #field, \
	offsetof(struct ccr_trace_header, field), sizeof(((struct ccr_trace_header *)0)->field))
	PH(magic); PH(trace_version); PH(recorder_version); PH(kernel_release);
	PH(reference_impl_id); PH(callback_manifest); PH(private_state_schema_id);
	PH(record_size); PH(creation_ts_ns);
	printf("sizeof(struct ccr_event_v1) = %zu\n", sizeof(struct ccr_event_v1));
	P(seq); P(sock_cookie); P(ts_ns); P(callback_id);
	P(clock_jiffies32_before); P(clock_jiffies32_after); P(pre_tcp_mstamp);
	P(in_ack); P(in_acked); P(in_new_state); P(in_cwnd_event);
	P(in_sample_rtt_us); P(in_sample_pkts_acked); P(in_sample_in_flight);
	P(pre_snd_cwnd); P(pre_snd_ssthresh); P(pre_snd_cwnd_cnt); P(pre_snd_cwnd_clamp);
	P(pre_prior_cwnd); P(pre_max_packets_out); P(pre_is_cwnd_limited);
	P(pre_snd_nxt); P(pre_snd_una); P(pre_lsndtime);
	P(pre_sk_pacing_rate); P(pre_sk_pacing_status); P(pre_sk_gso_max_size);
	P(priv_pre_cnt); P(priv_pre_last_max_cwnd); P(priv_pre_last_cwnd); P(priv_pre_last_time);
	P(priv_pre_bic_origin_point); P(priv_pre_bic_K); P(priv_pre_delay_min); P(priv_pre_epoch_start);
	P(priv_pre_ack_cnt); P(priv_pre_tcp_cwnd); P(priv_pre_sample_cnt); P(priv_pre_found);
	P(priv_pre_round_start); P(priv_pre_end_seq); P(priv_pre_last_ack); P(priv_pre_curr_rtt);
	P(priv_pre_raw);
	P(result_valid); P(result);
	P(post_snd_cwnd); P(post_snd_cwnd_cnt); P(post_snd_ssthresh);
	P(priv_post_cnt); P(priv_post_last_max_cwnd); P(priv_post_last_cwnd); P(priv_post_last_time);
	P(priv_post_bic_origin_point); P(priv_post_bic_K); P(priv_post_delay_min); P(priv_post_epoch_start);
	P(priv_post_ack_cnt); P(priv_post_tcp_cwnd); P(priv_post_sample_cnt); P(priv_post_found);
	P(priv_post_round_start); P(priv_post_end_seq); P(priv_post_last_ack); P(priv_post_curr_rtt);
	P(priv_post_raw);
	return 0;
}
