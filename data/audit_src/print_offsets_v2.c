// Ground-truth layout tool for struct ccr_event_v2 (ABI v2).
#include <stdio.h>
#include <stddef.h>
#include <linux/types.h>
#include "../../bpf/ccr_event_v2.h"

#define P(field) printf("%-40s offset=%-4zu size=%-4zu\n", #field, \
	offsetof(struct ccr_event_v2, field), sizeof(((struct ccr_event_v2 *)0)->field))
#define PH(field) printf("%-40s offset=%-4zu size=%-4zu\n", #field, \
	offsetof(struct ccr_trace_header, field), sizeof(((struct ccr_trace_header *)0)->field))

int main(void)
{
	printf("sizeof(struct ccr_trace_header) = %zu\n", sizeof(struct ccr_trace_header));
	PH(magic); PH(trace_version); PH(recorder_version); PH(kernel_release);
	PH(reference_impl_id); PH(callback_manifest); PH(private_state_schema_id);
	PH(record_size); PH(creation_ts_ns);
	printf("sizeof(struct ccr_event_v2) = %zu\n", sizeof(struct ccr_event_v2));
	P(seq); P(sock_cookie); P(ts_ns); P(callback_id);
	P(clock_jiffies32_before); P(clock_jiffies32_after);
	P(clock_ktime_ns_before); P(clock_ktime_ns_after);
	P(in_ack); P(in_acked); P(in_sample_rtt_us); P(in_sample_pkts_acked); P(in_sample_in_flight);
	P(pre_snd_cwnd); P(pre_snd_ssthresh); P(pre_snd_cwnd_cnt); P(pre_snd_cwnd_clamp);
	P(pre_prior_cwnd); P(pre_max_packets_out); P(pre_is_cwnd_limited);
	P(pre_snd_nxt); P(pre_mss_cache); P(pre_rate_delivered); P(pre_rate_interval_us);
	P(pre_rate_app_limited); P(pre_srtt_us);
	P(priv_pre_min_rtt_us); P(priv_pre_recent_min_us); P(priv_pre_detect_count);
	P(priv_pre_last_max_cwnd); P(priv_pre_epoch_start); P(priv_pre_cwnd_before_minrtt_probe);
	P(priv_pre_minrtt_probe_min_us); P(priv_pre_last_queue_est_pkts); P(priv_pre_dlv_rate_bps);
	P(priv_pre_dlv_rate_compete); P(priv_pre_dlv_rate_max); P(priv_pre_last_compete_exit_jiffies);
	P(priv_pre_compete_enter_jiffies); P(priv_pre_last_minrtt_probe_ns);
	P(priv_pre_probe_action_start_ns); P(priv_pre_mode); P(priv_pre_minrtt_probing);
	P(priv_pre_delay_window_start_ack); P(priv_pre_delay_cwnd_at_window_start);
	P(priv_pre_delay_rtts_in_window); P(priv_pre_delay_saved_bic_origin_point);
	P(priv_pre_delay_saved_bic_K); P(priv_pre_delay_detect_hold_until);
	P(priv_pre_cubic_cnt); P(priv_pre_cubic_last_cwnd); P(priv_pre_cubic_last_time);
	P(priv_pre_cubic_bic_origin_point); P(priv_pre_cubic_bic_K); P(priv_pre_cubic_ack_cnt);
	P(priv_pre_cubic_tcp_cwnd);
	P(priv_pre_raw);
	P(result_valid); P(result);
	P(post_snd_cwnd); P(post_snd_cwnd_cnt); P(post_snd_ssthresh);
	P(priv_post_min_rtt_us); P(priv_post_recent_min_us); P(priv_post_detect_count);
	P(priv_post_last_max_cwnd); P(priv_post_epoch_start); P(priv_post_cwnd_before_minrtt_probe);
	P(priv_post_minrtt_probe_min_us); P(priv_post_last_queue_est_pkts); P(priv_post_dlv_rate_bps);
	P(priv_post_dlv_rate_compete); P(priv_post_dlv_rate_max); P(priv_post_last_compete_exit_jiffies);
	P(priv_post_compete_enter_jiffies); P(priv_post_last_minrtt_probe_ns);
	P(priv_post_probe_action_start_ns); P(priv_post_mode); P(priv_post_minrtt_probing);
	P(priv_post_delay_window_start_ack); P(priv_post_delay_cwnd_at_window_start);
	P(priv_post_delay_rtts_in_window); P(priv_post_delay_saved_bic_origin_point);
	P(priv_post_delay_saved_bic_K); P(priv_post_delay_detect_hold_until);
	P(priv_post_cubic_cnt); P(priv_post_cubic_last_cwnd); P(priv_post_cubic_last_time);
	P(priv_post_cubic_bic_origin_point); P(priv_post_cubic_bic_K); P(priv_post_cubic_ack_cnt);
	P(priv_post_cubic_tcp_cwnd);
	P(priv_post_raw);
	return 0;
}
