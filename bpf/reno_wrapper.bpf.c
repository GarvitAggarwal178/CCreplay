/* CCReplay Reno wrapper recorder.
 *
 * struct_ops congestion-control implementation that IS the active
 * controller for the socket (ADR-007: no independent observer coexists
 * with native CCA ownership). Delegates every callback to the target
 * kernel's own tcp_reno_* reference functions (Oracle C, independent of
 * the userspace replay implementation -- capability audit section A),
 * recording one EventRecord per callback invocation: PRE state + inputs +
 * explicit callback result + declared controller-owned POST state, in a
 * single bpf_ringbuf_reserve (Replay ABI v0 Reno instantiation, see
 * docs/REPLAY_ABI.md).
 *
 * Manifest: {ssthresh, cong_avoid, undo_cwnd} -- exactly what upstream
 * tcp_reno_ops implements. No .init: Reno has no controller-private state
 * (ADR-014).
 *
 * Sequence numbers are allocated at callback entry, before ring-buffer
 * reservation is attempted (ADR-009): the reference controller always
 * runs and always produces a correct live result, whether or not the
 * event is successfully recorded. Three independent atomic counters
 * (invocations, emitted, drops) are read directly from a map at teardown,
 * before this struct_ops object is unregistered (ADR-013) -- the
 * authoritative loss signal, not a ring-buffer trailer.
 *
 * Provenance: the tcp_reno_* __ksym delegation pattern is adapted from
 * ~/cn-spike/bpf_src/spike_min.bpf.c / spike_probe.bpf.c / spike_ctrl.bpf.c
 * (commit 022c2e2) -- see docs/PROVENANCE.md. The EventRecord layout,
 * sequence/drop-counter logic, and per-callback recorder instrumentation
 * below are new CCReplay code, not present in any source file.
 */
#include "bpf_tracing_net.h"
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>
#include "ccr_event.h"

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
	__uint(max_entries, 1 << 22); /* 4 MiB; sized against R0 measurement */
} ccr_events SEC(".maps");

static __always_inline struct ccr_counters *get_counters(void)
{
	__u32 key = 0;

	return bpf_map_lookup_elem(&ccr_counters_map, &key);
}

/* Returns the allocated sequence number. Always succeeds (an atomic
 * increment cannot fail); the returned value is consumed regardless of
 * whether the subsequent ring-buffer reservation succeeds (ADR-009).
 */
static __always_inline __u64 alloc_seq(struct ccr_counters *c)
{
	return __sync_fetch_and_add(&c->invocations, 1);
}

static __always_inline void fill_common(struct ccr_event *e, struct sock *sk,
					 __u64 seq, __u32 callback_id)
{
	e->seq = seq;
	/* bpf_get_socket_cookie() is not usable from this program type on
	 * this kernel (verifier: "program of this type cannot use helper
	 * bpf_get_socket_cookie") -- confirmed by direct load attempt, not
	 * assumed. The raw sk pointer value is used instead purely as a
	 * within-trace socket-identity discriminator (see docs/REPLAY_ABI.md
	 * v0 Reno instantiation); it is not a stable cross-boot identifier
	 * and is never compared across separate recording sessions.
	 */
	e->sock_cookie = (__u64)(long)sk;
	e->ts_ns = bpf_ktime_get_ns();
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
__u32 BPF_PROG(ccr_reno_ssthresh, struct sock *sk)
{
	struct ccr_counters *c = get_counters();
	__u64 seq;
	struct ccr_event *e;
	__u32 ret;

	if (!c) {
		/* Counter map must always exist; if lookup somehow fails,
		 * still run the reference controller correctly -- recorder
		 * failure must never change controller semantics.
		 */
		return tcp_reno_ssthresh(sk);
	}

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
void BPF_PROG(ccr_reno_cong_avoid, struct sock *sk, __u32 ack, __u32 acked)
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
__u32 BPF_PROG(ccr_reno_undo_cwnd, struct sock *sk)
{
	struct ccr_counters *c = get_counters();
	__u64 seq;
	struct ccr_event *e;
	__u32 ret;

	if (!c) {
		return tcp_reno_undo_cwnd(sk);
	}

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
struct tcp_congestion_ops ccr_reno = {
	.ssthresh	= (void *)ccr_reno_ssthresh,
	.cong_avoid	= (void *)ccr_reno_cong_avoid,
	.undo_cwnd	= (void *)ccr_reno_undo_cwnd,
	.name		= "ccr_reno",
};
