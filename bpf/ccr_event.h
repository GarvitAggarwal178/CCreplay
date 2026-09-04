/* Shared EventRecord layout for CCReplay's Reno wrapper recorder.
 * Included from both bpf/reno_wrapper.bpf.c (BPF compilation) and
 * user/ccr_recorder.c (plain userspace compilation) so the binary layout
 * cannot drift between producer and consumer. Uses <linux/types.h> fixed-
 * width types, valid in both contexts. See docs/REPLAY_ABI.md v0 Reno
 * instantiation for the field-by-field rationale.
 */
#ifndef __CCR_EVENT_H__
#define __CCR_EVENT_H__

/* __u8/__u32/__u64 come from vmlinux.h when compiling the BPF side (it is
 * always included first, via bpf_tracing_net.h) and from linux/types.h on
 * the plain-userspace side. Including linux/types.h after vmlinux.h has
 * already defined the kernel posix types conflicts (duplicate typedefs),
 * so it is included conditionally on vmlinux.h's own header guard.
 */
#ifndef __VMLINUX_H__
#include <linux/types.h>
#endif

#define CCR_TRACE_MAGIC "CCRPLAY0"
#define CCR_TRACE_VERSION 0u

#define CCR_CB_SSTHRESH    1u
#define CCR_CB_CONG_AVOID  2u
#define CCR_CB_UNDO_CWND   3u

/* Bit positions in TraceHeader.callback_manifest. */
#define CCR_MANIFEST_SSTHRESH    (1u << 0)
#define CCR_MANIFEST_CONG_AVOID  (1u << 1)
#define CCR_MANIFEST_UNDO_CWND   (1u << 2)
#define CCR_RENO_MANIFEST \
	(CCR_MANIFEST_SSTHRESH | CCR_MANIFEST_CONG_AVOID | CCR_MANIFEST_UNDO_CWND)

struct ccr_event {
	__u64 seq;
	__u64 sock_cookie;
	__u64 ts_ns;
	__u32 callback_id;
	__u32 _pad0;

	/* CallbackInputs */
	__u32 in_ack;
	__u32 in_acked;

	/* SharedTcpPreState / Observations */
	__u32 pre_snd_cwnd;
	__u32 pre_snd_ssthresh;
	__u32 pre_snd_cwnd_cnt;
	__u32 pre_snd_cwnd_clamp;
	__u32 pre_prior_cwnd;
	__u32 pre_max_packets_out;
	__u8  pre_is_cwnd_limited;
	__u8  _pad1[3];

	/* CallbackResult */
	__u32 result_valid;
	__u32 result;

	/* ControllerOwnedPostState */
	__u32 post_snd_cwnd;
	__u32 post_snd_cwnd_cnt;
};

/* On-disk TraceHeader, written once at the start of every .ccr trace file. */
struct ccr_trace_header {
	char  magic[8];              /* CCR_TRACE_MAGIC, not NUL-terminated */
	__u32 trace_version;         /* CCR_TRACE_VERSION */
	__u32 recorder_version;
	char  kernel_release[65];
	char  reference_impl_id[32]; /* "linux_tcp_reno_kfunc" */
	__u32 callback_manifest;     /* CCR_RENO_MANIFEST */
	__u32 private_state_schema_id; /* 0 = NONE (ADR-014) */
	__u64 record_size;           /* sizeof(struct ccr_event), parser sanity check */
	__u64 creation_ts_ns;        /* wall-clock-independent: CLOCK_MONOTONIC at open */
};

#endif
