/* Capability audit B: BPF_MAP_TYPE_SK_STORAGE usability from struct_ops
 * TCP CC context on this kernel. Allocates per-socket storage in .init,
 * increments a counter in .cong_avoid on every invocation, reads it back
 * in .ssthresh, and explicitly deletes it in .release. A ringbuf emits the
 * counter value seen at each .cong_avoid call so userspace can confirm the
 * value persists and increments across calls for the same socket (proof
 * it is genuinely per-socket state, not a fluke zero-initialized read).
 * See data/capability_audit.md section B.
 */
#include "bpf_tracing_net.h"
#include <bpf/bpf_tracing.h>

char _license[] SEC("license") = "GPL";

extern void tcp_reno_cong_avoid(struct sock *sk, __u32 ack, __u32 acked) __ksym;
extern __u32 tcp_reno_ssthresh(struct sock *sk) __ksym;
extern __u32 tcp_reno_undo_cwnd(struct sock *sk) __ksym;

struct audit_priv {
	__u32 counter;
};

struct {
	__uint(type, BPF_MAP_TYPE_SK_STORAGE);
	__uint(map_flags, BPF_F_NO_PREALLOC);
	__type(key, int);
	__type(value, struct audit_priv);
} sk_priv SEC(".maps");

struct audit_event {
	__u64 ts_ns;
	__u32 counter;
};

struct {
	__uint(type, BPF_MAP_TYPE_RINGBUF);
	__uint(max_entries, 1 << 16);
} audit_events SEC(".maps");

SEC("struct_ops")
void BPF_PROG(audit_sks_init, struct sock *sk)
{
	struct audit_priv *p;

	p = bpf_sk_storage_get(&sk_priv, sk, NULL, BPF_LOCAL_STORAGE_GET_F_CREATE);
	if (p)
		p->counter = 0;
}

SEC("struct_ops")
void BPF_PROG(audit_sks_cong_avoid, struct sock *sk, __u32 ack, __u32 acked)
{
	struct audit_priv *p;
	struct audit_event *e;

	p = bpf_sk_storage_get(&sk_priv, sk, NULL, 0);
	if (p) {
		p->counter++;
		e = bpf_ringbuf_reserve(&audit_events, sizeof(*e), 0);
		if (e) {
			e->ts_ns = bpf_ktime_get_ns();
			e->counter = p->counter;
			bpf_ringbuf_submit(e, 0);
		}
	}

	tcp_reno_cong_avoid(sk, ack, acked);
}

SEC("struct_ops")
__u32 BPF_PROG(audit_sks_ssthresh, struct sock *sk)
{
	return tcp_reno_ssthresh(sk);
}

SEC("struct_ops")
__u32 BPF_PROG(audit_sks_undo_cwnd, struct sock *sk)
{
	return tcp_reno_undo_cwnd(sk);
}

SEC("struct_ops")
void BPF_PROG(audit_sks_release, struct sock *sk)
{
	bpf_sk_storage_delete(&sk_priv, sk);
}

SEC(".struct_ops")
struct tcp_congestion_ops audit_sks = {
	.init		= (void *)audit_sks_init,
	.ssthresh	= (void *)audit_sks_ssthresh,
	.cong_avoid	= (void *)audit_sks_cong_avoid,
	.undo_cwnd	= (void *)audit_sks_undo_cwnd,
	.release	= (void *)audit_sks_release,
	.name		= "audit_sks",
};
