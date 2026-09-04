/* N0.4 diagnostic variant of bpf/reno_wrapper.bpf.c -- byte-identical
 * except every bpf_ktime_get_ns() call is removed (ts_ns left as 0).
 * NOT used for any replay gate; diagnostic-only, per
 * docs/session/OVERNIGHT_EVIDENCE_PIPELINE.md N0.4. See
 * data/recorder_overhead/REPORT_RECORDER_OVERHEAD_SANITY_CHECK.md.
 *
 * Every other line is identical to bpf/reno_wrapper.bpf.c -- diff this
 * file against it to see the single change (grep -n ts_ns).
 */
#include "../bpf_tracing_net.h"
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>
#include "../ccr_event.h"

char _license[] SEC("license") = "GPL";

extern void tcp_reno_cong_avoid(struct sock *sk, __u32 ack, __u32 acked) __ksym;
extern __u32 tcp_reno_ssthresh(struct sock *sk) __ksym;
extern __u32 tcp_reno_undo_cwnd(struct sock *sk) __ksym;

struct ccr_counters {
	__u64 invocations;
	__u64 emitted;
	__u64 drops;
};

struct {
	__uint(type, BPF_MAP_TYPE_ARRAY);
	__uint(max_entries, 1);
	__type(key, __u32);
	__type(value, struct ccr_counters);
} ccr_counters_map SEC(".maps");

struct {
	__uint(type, BPF_MAP_TYPE_RINGBUF);
	__uint(max_entries, 1 << 22);
} ccr_events SEC(".maps");

static __always_inline struct ccr_counters *get_counters(void)
{
	__u32 key = 0;

	return bpf_map_lookup_elem(&ccr_counters_map, &key);
}

static __always_inline __u64 alloc_seq(struct ccr_counters *c)
{
	return __sync_fetch_and_add(&c->invocations, 1);
}

static __always_inline void fill_common(struct ccr_event *e, struct sock *sk,
					 __u64 seq, __u32 callback_id)
{
	e->seq = seq;
	e->sock_cookie = (__u64)(long)sk;
	e->ts_ns = 0; /* N0.4: bpf_ktime_get_ns() intentionally omitted */
	e->callback_id = callback_id;
	e->_pad0 = 0;
	e->in_ack = 0;
	e->in_acked = 0;
	e->result_valid = 0;
	e->result = 0;
}

static __always_inline void snap_pre(struct ccr_event *e, struct sock *sk)
{
	struct tcp_sock *tp = (struct tcp_sock *)sk;

	e->pre_snd_cwnd = BPF_CORE_READ(tp, snd_cwnd);
	e->pre_snd_ssthresh = BPF_CORE_READ(tp, snd_ssthresh);
	e->pre_snd_cwnd_cnt = BPF_CORE_READ(tp, snd_cwnd_cnt);
	e->pre_snd_cwnd_clamp = BPF_CORE_READ(tp, snd_cwnd_clamp);
	e->pre_prior_cwnd = BPF_CORE_READ(tp, prior_cwnd);
	e->pre_max_packets_out = BPF_CORE_READ(tp, max_packets_out);
	e->pre_is_cwnd_limited = BPF_CORE_READ_BITFIELD(tp, is_cwnd_limited);
	e->_pad1[0] = e->_pad1[1] = e->_pad1[2] = 0;
}

static __always_inline void snap_post(struct ccr_event *e, struct sock *sk)
{
	struct tcp_sock *tp = (struct tcp_sock *)sk;

	e->post_snd_cwnd = BPF_CORE_READ(tp, snd_cwnd);
	e->post_snd_cwnd_cnt = BPF_CORE_READ(tp, snd_cwnd_cnt);
}

SEC("struct_ops")
__u32 BPF_PROG(ccr_reno_nk_ssthresh, struct sock *sk)
{
	struct ccr_counters *c = get_counters();
	__u64 seq;
	struct ccr_event *e;
	__u32 ret;

	if (!c)
		return tcp_reno_ssthresh(sk);

	seq = alloc_seq(c);

	e = bpf_ringbuf_reserve(&ccr_events, sizeof(*e), 0);
	if (!e) {
		__sync_fetch_and_add(&c->drops, 1);
		return tcp_reno_ssthresh(sk);
	}

	fill_common(e, sk, seq, CCR_CB_SSTHRESH);
	snap_pre(e, sk);

	ret = tcp_reno_ssthresh(sk);

	e->result_valid = 1;
	e->result = ret;
	snap_post(e, sk);

	bpf_ringbuf_submit(e, 0);
	__sync_fetch_and_add(&c->emitted, 1);
	return ret;
}

SEC("struct_ops")
void BPF_PROG(ccr_reno_nk_cong_avoid, struct sock *sk, __u32 ack, __u32 acked)
{
	struct ccr_counters *c = get_counters();
	__u64 seq;
	struct ccr_event *e;

	if (!c) {
		tcp_reno_cong_avoid(sk, ack, acked);
		return;
	}

	seq = alloc_seq(c);

	e = bpf_ringbuf_reserve(&ccr_events, sizeof(*e), 0);
	if (!e) {
		__sync_fetch_and_add(&c->drops, 1);
		tcp_reno_cong_avoid(sk, ack, acked);
		return;
	}

	fill_common(e, sk, seq, CCR_CB_CONG_AVOID);
	e->in_ack = ack;
	e->in_acked = acked;
	snap_pre(e, sk);

	tcp_reno_cong_avoid(sk, ack, acked);

	snap_post(e, sk);

	bpf_ringbuf_submit(e, 0);
	__sync_fetch_and_add(&c->emitted, 1);
}

SEC("struct_ops")
__u32 BPF_PROG(ccr_reno_nk_undo_cwnd, struct sock *sk)
{
	struct ccr_counters *c = get_counters();
	__u64 seq;
	struct ccr_event *e;
	__u32 ret;

	if (!c)
		return tcp_reno_undo_cwnd(sk);

	seq = alloc_seq(c);

	e = bpf_ringbuf_reserve(&ccr_events, sizeof(*e), 0);
	if (!e) {
		__sync_fetch_and_add(&c->drops, 1);
		return tcp_reno_undo_cwnd(sk);
	}

	fill_common(e, sk, seq, CCR_CB_UNDO_CWND);
	snap_pre(e, sk);

	ret = tcp_reno_undo_cwnd(sk);

	e->result_valid = 1;
	e->result = ret;
	snap_post(e, sk);

	bpf_ringbuf_submit(e, 0);
	__sync_fetch_and_add(&c->emitted, 1);
	return ret;
}

SEC(".struct_ops")
struct tcp_congestion_ops ccr_reno_nk = {
	.ssthresh	= (void *)ccr_reno_nk_ssthresh,
	.cong_avoid	= (void *)ccr_reno_nk_cong_avoid,
	.undo_cwnd	= (void *)ccr_reno_nk_undo_cwnd,
	.name		= "ccr_reno_nk",
};
