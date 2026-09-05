/* CCReplay CUBIC wrapper recorder — Replay ABI v1 (ADR-021).
 *
 * struct_ops congestion-control implementation that IS the active
 * controller for the socket (ADR-007, same as the Reno wrapper). Delegates
 * every callback to the target kernel's own cubictcp_* reference functions
 * plus shared tcp_reno_undo_cwnd (Oracle C — ADR-017, verifier-load-
 * confirmed callable for all seven callbacks, data/cubic_replay_capability_audit.md
 * N1.1 and data/cubic_replay_kernel_source_correction.md), recording one
 * EventRecord per callback invocation in a single bpf_ringbuf_reserve
 * (N2.2 — attempted and achieved; no split-record fallback was needed).
 *
 * Manifest: {init, ssthresh, cong_avoid, set_state, cwnd_event, pkts_acked,
 * undo_cwnd} — exactly cubictcp's real struct tcp_congestion_ops table
 * (data/kernel_source_ref/tcp_cubic.c lines 478-488). Unlike Reno, CUBIC has
 * private controller state (struct bictcp in icsk_ca_priv, ADR-019) and two
 * controller-visible clocks (tcp_jiffies32, tp->tcp_mstamp — ADR-018).
 *
 * Sequence/counter discipline is identical to bpf/reno_wrapper.bpf.c
 * (ADR-009/ADR-013): sequence numbers allocated at callback entry, before
 * ring-buffer reservation; the reference controller always runs and always
 * produces a correct live result regardless of recording success; three
 * independent atomic counters (invocations, emitted, drops) read directly
 * from a map at teardown.
 *
 * Provenance: the kfunc-delegation pattern and counter/sequence discipline
 * are reused from bpf/reno_wrapper.bpf.c (new CCReplay code, not from any
 * read-only source repo). The cubictcp_* kfunc signatures and struct bictcp
 * layout are taken from data/kernel_source_ref/tcp_cubic.c (external
 * reference, docs/PROVENANCE.md "External (non-read-only-repo) source
 * reference" section) — not from ~/cn-spike/bpf_src/bpf_cubic.c.
 */
#include "bpf_tracing_net.h"
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>
#include "ccr_event_v1.h"

char _license[] SEC("license") = "GPL";

extern void cubictcp_init(struct sock *sk) __ksym;
extern void cubictcp_cong_avoid(struct sock *sk, __u32 ack, __u32 acked) __ksym;
extern __u32 cubictcp_recalc_ssthresh(struct sock *sk) __ksym;
extern void cubictcp_state(struct sock *sk, __u8 new_state) __ksym;
extern void cubictcp_cwnd_event(struct sock *sk, enum tcp_ca_event event) __ksym;
extern void cubictcp_acked(struct sock *sk, const struct ack_sample *sample) __ksym;
extern __u32 tcp_reno_undo_cwnd(struct sock *sk) __ksym;

struct ccr_counters {
	__u64 invocations;
	__u64 emitted;
	__u64 drops;
	/* Aggregate clock-ambiguity accounting (docs/REPLAY_ABI.md v1
	 * RecorderRunMetadata), read at teardown alongside the other three. */
	__u64 clock_stable;
	__u64 clock_ambiguous;
};

struct {
	__uint(type, BPF_MAP_TYPE_ARRAY);
	__uint(max_entries, 1);
	__type(key, __u32);
	__type(value, struct ccr_counters);
} ccr_counters_map SEC(".maps");

struct {
	__uint(type, BPF_MAP_TYPE_RINGBUF);
	/* 16 MiB: struct ccr_event_v1 is ~488 bytes, ~5.5x wider than v0's 88
	 * bytes, and CUBIC has two dominant callbacks (cong_avoid, pkts_acked)
	 * vs. Reno's one (data/cubic_replay_callback_coverage_plan.md) — sized
	 * up from v0's 4 MiB accordingly rather than reused unchanged.
	 */
	__uint(max_entries, 1 << 24);
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

static __always_inline void fill_common(struct ccr_event_v1 *e, struct sock *sk,
					 __u64 seq, __u32 callback_id)
{
	e->seq = seq;
	e->sock_cookie = (__u64)(long)sk; /* ADR-016 rationale unchanged from v0 */
	e->ts_ns = bpf_ktime_get_ns();
	e->callback_id = callback_id;
	e->_pad0 = 0;

	e->in_ack = 0;
	e->in_acked = 0;
	e->in_new_state = 0;
	e->in_cwnd_event = 0;
	e->in_sample_rtt_us = 0;
	e->in_sample_pkts_acked = 0;
	e->in_sample_in_flight = 0;

	e->result_valid = 0;
	e->result = 0;

	e->clock_jiffies32_before = tcp_jiffies32;
}

static __always_inline void finish_clock(struct ccr_event_v1 *e, struct ccr_counters *c)
{
	e->clock_jiffies32_after = tcp_jiffies32;
	if (e->clock_jiffies32_after == e->clock_jiffies32_before)
		__sync_fetch_and_add(&c->clock_stable, 1);
	else
		__sync_fetch_and_add(&c->clock_ambiguous, 1);
}

static __always_inline void snap_private(struct ccr_event_v1 *e, struct sock *sk, int is_post)
{
	struct bictcp *ca = (struct bictcp *)inet_csk_ca(sk);
	__u8 raw[CCR_ICSK_CA_PRIV_BYTES];

	bpf_probe_read_kernel(raw, sizeof(raw), (void *)ca);

	if (is_post) {
		e->priv_post_cnt = BPF_CORE_READ(ca, cnt);
		e->priv_post_last_max_cwnd = BPF_CORE_READ(ca, last_max_cwnd);
		e->priv_post_last_cwnd = BPF_CORE_READ(ca, last_cwnd);
		e->priv_post_last_time = BPF_CORE_READ(ca, last_time);
		e->priv_post_bic_origin_point = BPF_CORE_READ(ca, bic_origin_point);
		e->priv_post_bic_K = BPF_CORE_READ(ca, bic_K);
		e->priv_post_delay_min = BPF_CORE_READ(ca, delay_min);
		e->priv_post_epoch_start = BPF_CORE_READ(ca, epoch_start);
		e->priv_post_ack_cnt = BPF_CORE_READ(ca, ack_cnt);
		e->priv_post_tcp_cwnd = BPF_CORE_READ(ca, tcp_cwnd);
		e->priv_post_sample_cnt = BPF_CORE_READ(ca, sample_cnt);
		e->priv_post_found = BPF_CORE_READ(ca, found);
		e->_pad3[0] = e->_pad3[1] = 0;
		e->priv_post_round_start = BPF_CORE_READ(ca, round_start);
		e->priv_post_end_seq = BPF_CORE_READ(ca, end_seq);
		e->priv_post_last_ack = BPF_CORE_READ(ca, last_ack);
		e->priv_post_curr_rtt = BPF_CORE_READ(ca, curr_rtt);
		__builtin_memcpy(e->priv_post_raw, raw, sizeof(raw));
	} else {
		e->priv_pre_cnt = BPF_CORE_READ(ca, cnt);
		e->priv_pre_last_max_cwnd = BPF_CORE_READ(ca, last_max_cwnd);
		e->priv_pre_last_cwnd = BPF_CORE_READ(ca, last_cwnd);
		e->priv_pre_last_time = BPF_CORE_READ(ca, last_time);
		e->priv_pre_bic_origin_point = BPF_CORE_READ(ca, bic_origin_point);
		e->priv_pre_bic_K = BPF_CORE_READ(ca, bic_K);
		e->priv_pre_delay_min = BPF_CORE_READ(ca, delay_min);
		e->priv_pre_epoch_start = BPF_CORE_READ(ca, epoch_start);
		e->priv_pre_ack_cnt = BPF_CORE_READ(ca, ack_cnt);
		e->priv_pre_tcp_cwnd = BPF_CORE_READ(ca, tcp_cwnd);
		e->priv_pre_sample_cnt = BPF_CORE_READ(ca, sample_cnt);
		e->priv_pre_found = BPF_CORE_READ(ca, found);
		e->_pad2[0] = e->_pad2[1] = 0;
		e->priv_pre_round_start = BPF_CORE_READ(ca, round_start);
		e->priv_pre_end_seq = BPF_CORE_READ(ca, end_seq);
		e->priv_pre_last_ack = BPF_CORE_READ(ca, last_ack);
		e->priv_pre_curr_rtt = BPF_CORE_READ(ca, curr_rtt);
		__builtin_memcpy(e->priv_pre_raw, raw, sizeof(raw));
	}
}

static __always_inline void snap_shared_pre(struct ccr_event_v1 *e, struct sock *sk)
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
	e->pre_snd_nxt = BPF_CORE_READ(tp, snd_nxt);
	e->pre_snd_una = BPF_CORE_READ(tp, snd_una);
	e->pre_lsndtime = BPF_CORE_READ(tp, lsndtime);
	e->pre_tcp_mstamp = BPF_CORE_READ(tp, tcp_mstamp);
	e->pre_sk_pacing_rate = BPF_CORE_READ(sk, sk_pacing_rate);
	e->pre_sk_pacing_status = BPF_CORE_READ(sk, sk_pacing_status);
	e->pre_sk_gso_max_size = BPF_CORE_READ(sk, sk_gso_max_size);

	snap_private(e, sk, 0);
}

static __always_inline void snap_post(struct ccr_event_v1 *e, struct sock *sk)
{
	struct tcp_sock *tp = (struct tcp_sock *)sk;

	e->post_snd_cwnd = BPF_CORE_READ(tp, snd_cwnd);
	e->post_snd_cwnd_cnt = BPF_CORE_READ(tp, snd_cwnd_cnt);
	e->post_snd_ssthresh = BPF_CORE_READ(tp, snd_ssthresh); /* ADR-020 */

	snap_private(e, sk, 1);
}

SEC("struct_ops")
void BPF_PROG(ccr_cubic_init, struct sock *sk)
{
	struct ccr_counters *c = get_counters();
	__u64 seq;
	struct ccr_event_v1 *e;

	if (!c) {
		cubictcp_init(sk);
		return;
	}
	seq = alloc_seq(c);
	e = bpf_ringbuf_reserve(&ccr_events, sizeof(*e), 0);
	if (!e) {
		__sync_fetch_and_add(&c->drops, 1);
		cubictcp_init(sk);
		return;
	}
	fill_common(e, sk, seq, CCR_CB_INIT);
	snap_shared_pre(e, sk);

	cubictcp_init(sk);

	snap_post(e, sk);
	finish_clock(e, c);
	bpf_ringbuf_submit(e, 0);
	__sync_fetch_and_add(&c->emitted, 1);
}

SEC("struct_ops")
void BPF_PROG(ccr_cubic_cong_avoid, struct sock *sk, __u32 ack, __u32 acked)
{
	struct ccr_counters *c = get_counters();
	__u64 seq;
	struct ccr_event_v1 *e;

	if (!c) {
		cubictcp_cong_avoid(sk, ack, acked);
		return;
	}
	seq = alloc_seq(c);
	e = bpf_ringbuf_reserve(&ccr_events, sizeof(*e), 0);
	if (!e) {
		__sync_fetch_and_add(&c->drops, 1);
		cubictcp_cong_avoid(sk, ack, acked);
		return;
	}
	fill_common(e, sk, seq, CCR_CB_CONG_AVOID);
	e->in_ack = ack;
	e->in_acked = acked;
	snap_shared_pre(e, sk);

	cubictcp_cong_avoid(sk, ack, acked);

	snap_post(e, sk);
	finish_clock(e, c);
	bpf_ringbuf_submit(e, 0);
	__sync_fetch_and_add(&c->emitted, 1);
}

SEC("struct_ops")
__u32 BPF_PROG(ccr_cubic_ssthresh, struct sock *sk)
{
	struct ccr_counters *c = get_counters();
	__u64 seq;
	struct ccr_event_v1 *e;
	__u32 ret;

	if (!c)
		return cubictcp_recalc_ssthresh(sk);

	seq = alloc_seq(c);
	e = bpf_ringbuf_reserve(&ccr_events, sizeof(*e), 0);
	if (!e) {
		__sync_fetch_and_add(&c->drops, 1);
		return cubictcp_recalc_ssthresh(sk);
	}
	fill_common(e, sk, seq, CCR_CB_SSTHRESH);
	snap_shared_pre(e, sk);

	ret = cubictcp_recalc_ssthresh(sk);

	e->result_valid = 1;
	e->result = ret;
	snap_post(e, sk);
	finish_clock(e, c);
	bpf_ringbuf_submit(e, 0);
	__sync_fetch_and_add(&c->emitted, 1);
	return ret;
}

SEC("struct_ops")
void BPF_PROG(ccr_cubic_set_state, struct sock *sk, __u8 new_state)
{
	struct ccr_counters *c = get_counters();
	__u64 seq;
	struct ccr_event_v1 *e;

	if (!c) {
		cubictcp_state(sk, new_state);
		return;
	}
	seq = alloc_seq(c);
	e = bpf_ringbuf_reserve(&ccr_events, sizeof(*e), 0);
	if (!e) {
		__sync_fetch_and_add(&c->drops, 1);
		cubictcp_state(sk, new_state);
		return;
	}
	fill_common(e, sk, seq, CCR_CB_SET_STATE);
	e->in_new_state = new_state;
	snap_shared_pre(e, sk);

	cubictcp_state(sk, new_state);

	snap_post(e, sk);
	finish_clock(e, c);
	bpf_ringbuf_submit(e, 0);
	__sync_fetch_and_add(&c->emitted, 1);
}

SEC("struct_ops")
void BPF_PROG(ccr_cubic_cwnd_event, struct sock *sk, enum tcp_ca_event event)
{
	struct ccr_counters *c = get_counters();
	__u64 seq;
	struct ccr_event_v1 *e;

	if (!c) {
		cubictcp_cwnd_event(sk, event);
		return;
	}
	seq = alloc_seq(c);
	e = bpf_ringbuf_reserve(&ccr_events, sizeof(*e), 0);
	if (!e) {
		__sync_fetch_and_add(&c->drops, 1);
		cubictcp_cwnd_event(sk, event);
		return;
	}
	fill_common(e, sk, seq, CCR_CB_CWND_EVENT);
	e->in_cwnd_event = event;
	snap_shared_pre(e, sk);

	cubictcp_cwnd_event(sk, event);

	snap_post(e, sk);
	finish_clock(e, c);
	bpf_ringbuf_submit(e, 0);
	__sync_fetch_and_add(&c->emitted, 1);
}

SEC("struct_ops")
void BPF_PROG(ccr_cubic_pkts_acked, struct sock *sk, const struct ack_sample *sample)
{
	struct ccr_counters *c = get_counters();
	__u64 seq;
	struct ccr_event_v1 *e;

	if (!c) {
		cubictcp_acked(sk, sample);
		return;
	}
	seq = alloc_seq(c);
	e = bpf_ringbuf_reserve(&ccr_events, sizeof(*e), 0);
	if (!e) {
		__sync_fetch_and_add(&c->drops, 1);
		cubictcp_acked(sk, sample);
		return;
	}
	fill_common(e, sk, seq, CCR_CB_PKTS_ACKED);
	e->in_sample_rtt_us = BPF_CORE_READ(sample, rtt_us);
	e->in_sample_pkts_acked = BPF_CORE_READ(sample, pkts_acked);
	e->in_sample_in_flight = BPF_CORE_READ(sample, in_flight);
	snap_shared_pre(e, sk);

	cubictcp_acked(sk, sample);

	snap_post(e, sk);
	finish_clock(e, c);
	bpf_ringbuf_submit(e, 0);
	__sync_fetch_and_add(&c->emitted, 1);
}

SEC("struct_ops")
__u32 BPF_PROG(ccr_cubic_undo_cwnd, struct sock *sk)
{
	struct ccr_counters *c = get_counters();
	__u64 seq;
	struct ccr_event_v1 *e;
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
	snap_shared_pre(e, sk);

	ret = tcp_reno_undo_cwnd(sk);

	e->result_valid = 1;
	e->result = ret;
	snap_post(e, sk);
	finish_clock(e, c);
	bpf_ringbuf_submit(e, 0);
	__sync_fetch_and_add(&c->emitted, 1);
	return ret;
}

SEC(".struct_ops")
struct tcp_congestion_ops ccr_cubic = {
	.init		= (void *)ccr_cubic_init,
	.ssthresh	= (void *)ccr_cubic_ssthresh,
	.cong_avoid	= (void *)ccr_cubic_cong_avoid,
	.set_state	= (void *)ccr_cubic_set_state,
	.cwnd_event	= (void *)ccr_cubic_cwnd_event,
	.pkts_acked	= (void *)ccr_cubic_pkts_acked,
	.undo_cwnd	= (void *)ccr_cubic_undo_cwnd,
	.name		= "ccr_cubic",
};
