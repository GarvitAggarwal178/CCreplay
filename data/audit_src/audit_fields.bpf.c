/* Capability audit E: empirically discover which tcp_sock fields the real
 * kernel tcp_reno_* reference functions actually mutate, rather than
 * assuming the Replay ABI doc's example field list is complete. Captures a
 * wide PRE/POST superset around each real kfunc call and emits it; a
 * userspace pass over the resulting event stream diffs PRE vs POST per
 * field across many real invocations to find exactly which fields the
 * kfunc wrote. See data/capability_audit.md section E.
 */
#include "bpf_tracing_net.h"
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>

char _license[] SEC("license") = "GPL";

extern void tcp_reno_cong_avoid(struct sock *sk, __u32 ack, __u32 acked) __ksym;
extern __u32 tcp_reno_ssthresh(struct sock *sk) __ksym;
extern __u32 tcp_reno_undo_cwnd(struct sock *sk) __ksym;

struct fields_snap {
	__u32 snd_cwnd;
	__u32 snd_ssthresh;
	__u32 snd_cwnd_cnt;
	__u32 snd_cwnd_clamp;
	__u32 snd_cwnd_used;
	__u32 snd_cwnd_stamp;
	__u32 prior_cwnd;
	__u32 prior_ssthresh;
	__u32 packets_out;
	__u32 max_packets_out;
	__u8  is_cwnd_limited;
};

struct fields_event {
	__u64 ts_ns;
	__u32 callback; /* 0=cong_avoid 1=ssthresh 2=undo_cwnd */
	__u32 ack;
	__u32 acked;
	__u32 ret; /* return value for ssthresh/undo_cwnd */
	struct fields_snap pre;
	struct fields_snap post;
};

struct {
	__uint(type, BPF_MAP_TYPE_RINGBUF);
	__uint(max_entries, 1 << 22);
} fields_events SEC(".maps");

static __always_inline void snap(struct sock *sk, struct fields_snap *s)
{
	struct tcp_sock *tp = (struct tcp_sock *)sk;

	s->snd_cwnd = BPF_CORE_READ(tp, snd_cwnd);
	s->snd_ssthresh = BPF_CORE_READ(tp, snd_ssthresh);
	s->snd_cwnd_cnt = BPF_CORE_READ(tp, snd_cwnd_cnt);
	s->snd_cwnd_clamp = BPF_CORE_READ(tp, snd_cwnd_clamp);
	s->snd_cwnd_used = BPF_CORE_READ(tp, snd_cwnd_used);
	s->snd_cwnd_stamp = BPF_CORE_READ(tp, snd_cwnd_stamp);
	s->prior_cwnd = BPF_CORE_READ(tp, prior_cwnd);
	s->prior_ssthresh = BPF_CORE_READ(tp, prior_ssthresh);
	s->packets_out = BPF_CORE_READ(tp, packets_out);
	s->max_packets_out = BPF_CORE_READ(tp, max_packets_out);
	s->is_cwnd_limited = BPF_CORE_READ_BITFIELD(tp, is_cwnd_limited);
}

SEC("struct_ops")
void BPF_PROG(audit_fields_init, struct sock *sk)
{
}

SEC("struct_ops")
void BPF_PROG(audit_fields_cong_avoid, struct sock *sk, __u32 ack, __u32 acked)
{
	struct fields_event *e;

	e = bpf_ringbuf_reserve(&fields_events, sizeof(*e), 0);
	if (!e) {
		tcp_reno_cong_avoid(sk, ack, acked);
		return;
	}
	e->ts_ns = bpf_ktime_get_ns();
	e->callback = 0;
	e->ack = ack;
	e->acked = acked;
	e->ret = 0;
	snap(sk, &e->pre);
	tcp_reno_cong_avoid(sk, ack, acked);
	snap(sk, &e->post);
	bpf_ringbuf_submit(e, 0);
}

SEC("struct_ops")
__u32 BPF_PROG(audit_fields_ssthresh, struct sock *sk)
{
	struct fields_event *e;
	__u32 ret;

	e = bpf_ringbuf_reserve(&fields_events, sizeof(*e), 0);
	if (!e)
		return tcp_reno_ssthresh(sk);
	e->ts_ns = bpf_ktime_get_ns();
	e->callback = 1;
	e->ack = 0;
	e->acked = 0;
	snap(sk, &e->pre);
	ret = tcp_reno_ssthresh(sk);
	e->ret = ret;
	snap(sk, &e->post);
	bpf_ringbuf_submit(e, 0);
	return ret;
}

SEC("struct_ops")
__u32 BPF_PROG(audit_fields_undo_cwnd, struct sock *sk)
{
	struct fields_event *e;
	__u32 ret;

	e = bpf_ringbuf_reserve(&fields_events, sizeof(*e), 0);
	if (!e)
		return tcp_reno_undo_cwnd(sk);
	e->ts_ns = bpf_ktime_get_ns();
	e->callback = 2;
	e->ack = 0;
	e->acked = 0;
	snap(sk, &e->pre);
	ret = tcp_reno_undo_cwnd(sk);
	e->ret = ret;
	snap(sk, &e->post);
	bpf_ringbuf_submit(e, 0);
	return ret;
}

SEC(".struct_ops")
struct tcp_congestion_ops audit_fields = {
	.init		= (void *)audit_fields_init,
	.ssthresh	= (void *)audit_fields_ssthresh,
	.cong_avoid	= (void *)audit_fields_cong_avoid,
	.undo_cwnd	= (void *)audit_fields_undo_cwnd,
	.name		= "audit_fields",
};
