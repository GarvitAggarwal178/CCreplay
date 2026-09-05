/* Shared EventRecord layout for CCReplay's CoVegas wrapper recorder — Replay
 * ABI v2 (ADR-022..024). Included from both bpf/covegas_wrapper.bpf.c and
 * user/ccr_recorder_covegas.c. Reuses struct ccr_trace_header from
 * ccr_event.h unchanged (no header format change, same discipline as v1/
 * ADR-021) and CCR_TRACE_MAGIC. Independent of struct ccr_event (v0) and
 * struct ccr_event_v1 (v1). See docs/REPLAY_ABI.md's "v2 concrete
 * instantiation — CoVegas" section and data/covegas_replay_capability_audit.md.
 */
#ifndef __CCR_EVENT_V2_H__
#define __CCR_EVENT_V2_H__

#ifndef __VMLINUX_H__
#include <linux/types.h>
#endif

#include "ccr_event.h" /* struct ccr_trace_header, CCR_TRACE_MAGIC only */

#define CCR_TRACE_VERSION_2 2u

/* CoVegas's five callbacks (struct tcp_congestion_ops covegas, covegas.bpf.c
 * lines 936-944) -- no set_state/cwnd_event, unlike CUBIC. Reuses
 * CCR_CB_SSTHRESH(1)/CONG_AVOID(2)/UNDO_CWND(3) from ccr_event.h unchanged;
 * CCR_CB_INIT(4)/CCR_CB_PKTS_ACKED(7) defined here directly (not by
 * including ccr_event_v1.h, to keep v2 independent of v1) with the same
 * numeric values ccr_event_v1.h uses, for cross-controller readability only
 * -- not a structural dependency. */
#ifndef CCR_CB_INIT
#define CCR_CB_INIT 4u
#endif
#ifndef CCR_CB_PKTS_ACKED
#define CCR_CB_PKTS_ACKED 7u
#endif
#define CCR_MANIFEST_INIT_V2       (1u << 3)
#define CCR_MANIFEST_PKTS_ACKED_V2 (1u << 6)
#define CCR_COVEGAS_MANIFEST \
	(CCR_MANIFEST_SSTHRESH | CCR_MANIFEST_CONG_AVOID | CCR_MANIFEST_UNDO_CWND | \
	 CCR_MANIFEST_INIT_V2 | CCR_MANIFEST_PKTS_ACKED_V2)

#define CCR_PRIVATE_SCHEMA_COVEGAS_V2 2u

#define CCR_COVEGAS_MODE_DELAY   0u
#define CCR_COVEGAS_MODE_COMPETE 1u

#define CCR_ICSK_CA_PRIV_BYTES_V2 104

struct ccr_event_v2 {
	__u64 seq;
	__u64 sock_cookie;
	__u64 ts_ns;
	__u32 callback_id;
	__u32 _pad0;

	/* Two independent clock brackets (ADR-024). */
	__u32 clock_jiffies32_before;
	__u32 clock_jiffies32_after;
	__u64 clock_ktime_ns_before;
	__u64 clock_ktime_ns_after;

	/* CallbackInputs */
	__u32 in_ack;
	__u32 in_acked;
	__s64 in_sample_rtt_us;
	__s32 in_sample_pkts_acked;
	__s32 in_sample_in_flight;

	/* SharedTcpPreState / Observations */
	__u32 pre_snd_cwnd;
	__u32 pre_snd_ssthresh;
	__u32 pre_snd_cwnd_cnt;
	__u32 pre_snd_cwnd_clamp;
	__u32 pre_prior_cwnd;
	__u32 pre_max_packets_out;
	__u8  pre_is_cwnd_limited;
	__u8  _pad1[3];
	__u32 pre_snd_nxt;
	__u32 pre_mss_cache;
	__u32 pre_rate_delivered;
	__u32 pre_rate_interval_us;
	__u8  pre_rate_app_limited;
	__u8  _pad2[3];
	__u32 pre_srtt_us;

	/* Private PRE state: 17 dedicated fields (D3). */
	__u32 priv_pre_min_rtt_us;
	__u32 priv_pre_recent_min_us;
	__u32 priv_pre_detect_count;
	__u32 priv_pre_last_max_cwnd;
	__u32 priv_pre_epoch_start;
	__u32 priv_pre_cwnd_before_minrtt_probe;
	__u32 priv_pre_minrtt_probe_min_us;
	__u32 priv_pre_last_queue_est_pkts;
	__u32 priv_pre_dlv_rate_bps;
	__u32 priv_pre_dlv_rate_compete;
	__u32 priv_pre_dlv_rate_max;
	__u32 priv_pre_last_compete_exit_jiffies;
	__u32 priv_pre_compete_enter_jiffies;
	__u64 priv_pre_last_minrtt_probe_ns;
	__u64 priv_pre_probe_action_start_ns;
	__u8  priv_pre_mode;
	__u8  priv_pre_minrtt_probing;
	__u8  _pad3[6];

	/* Private PRE state: union, both arms always recorded (mode at PRE
	 * time selects which is semantically live -- ADR-023). */
	__u32 priv_pre_delay_window_start_ack;
	__u32 priv_pre_delay_cwnd_at_window_start;
	__u32 priv_pre_delay_rtts_in_window;
	__u32 priv_pre_delay_saved_bic_origin_point;
	__u32 priv_pre_delay_saved_bic_K;
	__u32 priv_pre_delay_detect_hold_until;
	__u32 priv_pre_cubic_cnt;
	__u32 priv_pre_cubic_last_cwnd;
	__u32 priv_pre_cubic_last_time;
	__u32 priv_pre_cubic_bic_origin_point;
	__u32 priv_pre_cubic_bic_K;
	__u32 priv_pre_cubic_ack_cnt;
	__u32 priv_pre_cubic_tcp_cwnd;

	/* Raw icsk_ca_priv bytes, PRE -- diagnostic archive only. */
	__u8 priv_pre_raw[CCR_ICSK_CA_PRIV_BYTES_V2];

	/* CallbackResult */
	__u32 result_valid;
	__u32 result;

	/* ControllerOwnedPostState */
	__u32 post_snd_cwnd;
	__u32 post_snd_cwnd_cnt;
	__u32 post_snd_ssthresh;

	/* Private POST state: mirrors PRE field-for-field. */
	__u32 priv_post_min_rtt_us;
	__u32 priv_post_recent_min_us;
	__u32 priv_post_detect_count;
	__u32 priv_post_last_max_cwnd;
	__u32 priv_post_epoch_start;
	__u32 priv_post_cwnd_before_minrtt_probe;
	__u32 priv_post_minrtt_probe_min_us;
	__u32 priv_post_last_queue_est_pkts;
	__u32 priv_post_dlv_rate_bps;
	__u32 priv_post_dlv_rate_compete;
	__u32 priv_post_dlv_rate_max;
	__u32 priv_post_last_compete_exit_jiffies;
	__u32 priv_post_compete_enter_jiffies;
	__u64 priv_post_last_minrtt_probe_ns;
	__u64 priv_post_probe_action_start_ns;
	__u8  priv_post_mode;
	__u8  priv_post_minrtt_probing;
	__u8  _pad4[6];

	__u32 priv_post_delay_window_start_ack;
	__u32 priv_post_delay_cwnd_at_window_start;
	__u32 priv_post_delay_rtts_in_window;
	__u32 priv_post_delay_saved_bic_origin_point;
	__u32 priv_post_delay_saved_bic_K;
	__u32 priv_post_delay_detect_hold_until;
	__u32 priv_post_cubic_cnt;
	__u32 priv_post_cubic_last_cwnd;
	__u32 priv_post_cubic_last_time;
	__u32 priv_post_cubic_bic_origin_point;
	__u32 priv_post_cubic_bic_K;
	__u32 priv_post_cubic_ack_cnt;
	__u32 priv_post_cubic_tcp_cwnd;

	__u8 priv_post_raw[CCR_ICSK_CA_PRIV_BYTES_V2];
};

#endif
