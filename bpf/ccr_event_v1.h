/* Shared EventRecord layout for CCReplay's CUBIC wrapper recorder — Replay
 * ABI v1 (ADR-021). Included from both bpf/cubic_wrapper.bpf.c (BPF
 * compilation) and user/ccr_recorder_cubic.c (plain userspace compilation).
 * Reuses struct ccr_trace_header from ccr_event.h unchanged (ADR-021: no
 * header format change) and CCR_TRACE_MAGIC. Does not modify, include as
 * dependency, or reuse struct ccr_event (v0/Reno) — the two record types are
 * independent per trace_version. See docs/REPLAY_ABI.md's "v1 concrete
 * instantiation — CUBIC" section for the field-by-field rationale, and
 * docs/DECISIONS.md ADR-017..021.
 */
#ifndef __CCR_EVENT_V1_H__
#define __CCR_EVENT_V1_H__

#ifndef __VMLINUX_H__
#include <linux/types.h>
#endif

#include "ccr_event.h" /* struct ccr_trace_header, CCR_TRACE_MAGIC only */

#define CCR_TRACE_VERSION_1 1u

/* CUBIC's real struct tcp_congestion_ops table (data/kernel_source_ref/
 * tcp_cubic.c lines 478-488) — seven callbacks, unlike Reno's three. */
#define CCR_CB_INIT        4u
#define CCR_CB_SET_STATE   5u
#define CCR_CB_CWND_EVENT  6u
#define CCR_CB_PKTS_ACKED  7u
/* CCR_CB_SSTHRESH(1)/CONG_AVOID(2)/UNDO_CWND(3) reused unchanged from
 * ccr_event.h — same semantic meaning, shared across v0 and v1. */

/* Bit positions in TraceHeader.callback_manifest (7-bit mask, v1). */
#define CCR_MANIFEST_INIT        (1u << 3)
#define CCR_MANIFEST_SET_STATE   (1u << 4)
#define CCR_MANIFEST_CWND_EVENT  (1u << 5)
#define CCR_MANIFEST_PKTS_ACKED  (1u << 6)
#define CCR_CUBIC_MANIFEST \
	(CCR_MANIFEST_SSTHRESH | CCR_MANIFEST_CONG_AVOID | CCR_MANIFEST_UNDO_CWND | \
	 CCR_MANIFEST_INIT | CCR_MANIFEST_SET_STATE | CCR_MANIFEST_CWND_EVENT | \
	 CCR_MANIFEST_PKTS_ACKED)

/* private_state_schema_id values (TraceHeader). 0 = NONE (v0 Reno, ADR-014). */
#define CCR_PRIVATE_SCHEMA_CUBIC_V1 1u

/* Clock classification (ADR-018) is derived at parse time from
 * clock_jiffies32_before == clock_jiffies32_after, not stored as a separate
 * field — storing it here would be a redundant derived value the parser can
 * (and must) recompute for verification rather than trust blindly. */

/* Raw icsk_ca_priv archive size. struct bictcp is 60 bytes (N1.3); the full
 * ICSK_CA_PRIV_SIZE array is 13*8=104 bytes. Archiving the full 104 bytes
 * (not just 60) is deliberate: it also captures any bytes beyond struct
 * bictcp's own extent, which should be all-zero and is itself a useful
 * diagnostic invariant to check, not just dead space to trim. */
#define CCR_ICSK_CA_PRIV_BYTES 104

struct ccr_event_v1 {
	__u64 seq;
	__u64 sock_cookie;
	__u64 ts_ns;
	__u32 callback_id;
	__u32 _pad0;

	/* Controller-visible time (ADR-018). tcp_jiffies32 snapshotted
	 * immediately before/after the kfunc call; CLOCK_STABLE iff equal.
	 * tp->tcp_mstamp needs only one PRE snapshot (TCP core, not the CC
	 * callback, is the only writer). */
	__u32 clock_jiffies32_before;
	__u32 clock_jiffies32_after;
	__u64 pre_tcp_mstamp;

	/* CallbackInputs. Fields not meaningful for a given callback_id are
	 * zero. in_ack is recorded even though the real kernel's cong_avoid
	 * does not read it (data/cubic_replay_kernel_source_correction.md) —
	 * recording an unread-but-plausible input is harmless and documents
	 * the finding; omitting it would not be an error either, but keeping
	 * cong_avoid's argument list complete (ack, acked) matches Reno's v0
	 * convention and costs nothing. */
	__u32 in_ack;
	__u32 in_acked;
	__u32 in_new_state;       /* set_state */
	__u32 in_cwnd_event;      /* cwnd_event: enum tcp_ca_event */
	__s64 in_sample_rtt_us;   /* pkts_acked: struct ack_sample.rtt_us, signed */
	__s32 in_sample_pkts_acked; /* pkts_acked: struct ack_sample.pkts_acked (unread by reference; recorded for completeness) */
	__s32 in_sample_in_flight;  /* pkts_acked: struct ack_sample.in_flight (unread by reference; recorded for completeness) */

	/* SharedTcpPreState / Observations. First six fields are the v0 Reno
	 * set, unchanged meaning; the rest are CUBIC-specific additions
	 * (docs/REPLAY_ABI.md v1 section). */
	__u32 pre_snd_cwnd;
	__u32 pre_snd_ssthresh;
	__u32 pre_snd_cwnd_cnt;
	__u32 pre_snd_cwnd_clamp;
	__u32 pre_prior_cwnd;
	__u32 pre_max_packets_out;
	__u8  pre_is_cwnd_limited;
	__u8  _pad1[3];
	__u32 pre_snd_nxt;
	__u32 pre_snd_una;
	__u32 pre_lsndtime;
	__u64 pre_sk_pacing_rate;
	__u32 pre_sk_pacing_status;
	__u32 pre_sk_gso_max_size;

	/* Private PRE state: 16 semantic struct bictcp fields (ADR-019).
	 * `unused` (offset 40 in the real struct) is deliberately excluded. */
	__u32 priv_pre_cnt;
	__u32 priv_pre_last_max_cwnd;
	__u32 priv_pre_last_cwnd;
	__u32 priv_pre_last_time;
	__u32 priv_pre_bic_origin_point;
	__u32 priv_pre_bic_K;
	__u32 priv_pre_delay_min;
	__u32 priv_pre_epoch_start;
	__u32 priv_pre_ack_cnt;
	__u32 priv_pre_tcp_cwnd;
	__u8  priv_pre_sample_cnt;
	__u8  priv_pre_found;
	__u8  _pad2[2];
	__u32 priv_pre_round_start;
	__u32 priv_pre_end_seq;
	__u32 priv_pre_last_ack;
	__u32 priv_pre_curr_rtt;

	/* Raw icsk_ca_priv bytes, PRE — diagnostic archive, not the
	 * correctness oracle (docs/REPLAY_ABI.md "Private state"). */
	__u8 priv_pre_raw[CCR_ICSK_CA_PRIV_BYTES];

	/* CallbackResult */
	__u32 result_valid;
	__u32 result;

	/* ControllerOwnedPostState. post_snd_ssthresh is new relative to v0
	 * (ADR-020) — required because pkts_acked writes tp->snd_ssthresh
	 * directly, outside any callback's return value. */
	__u32 post_snd_cwnd;
	__u32 post_snd_cwnd_cnt;
	__u32 post_snd_ssthresh;

	/* Private POST state, mirrors PRE field-for-field. */
	__u32 priv_post_cnt;
	__u32 priv_post_last_max_cwnd;
	__u32 priv_post_last_cwnd;
	__u32 priv_post_last_time;
	__u32 priv_post_bic_origin_point;
	__u32 priv_post_bic_K;
	__u32 priv_post_delay_min;
	__u32 priv_post_epoch_start;
	__u32 priv_post_ack_cnt;
	__u32 priv_post_tcp_cwnd;
	__u8  priv_post_sample_cnt;
	__u8  priv_post_found;
	__u8  _pad3[2];
	__u32 priv_post_round_start;
	__u32 priv_post_end_seq;
	__u32 priv_post_last_ack;
	__u32 priv_post_curr_rtt;

	/* Raw icsk_ca_priv bytes, POST — diagnostic archive. */
	__u8 priv_post_raw[CCR_ICSK_CA_PRIV_BYTES];
};

#endif
