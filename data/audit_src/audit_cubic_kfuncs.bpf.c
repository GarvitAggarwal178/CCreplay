// N1.1 smoke test (audit-only, disposable): is the kernel's own CUBIC math
// (cubictcp_cong_avoid / cubictcp_recalc_ssthresh / cubictcp_init /
// cubictcp_cwnd_event / cubictcp_state) callable as a kfunc from a
// struct_ops congestion-control program on THIS kernel, the same way
// tcp_reno_cong_avoid etc. were confirmed callable for Reno (Phase 1)?
//
// BTF presence (confirmed via `bpftool btf dump`) does not imply
// kfunc-callability -- only the kernel's registered kfunc allowlist does.
// This program never runs; it only needs to load-verify.
#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include "bpf_tracing_net.h"

char _license[] SEC("license") = "GPL";

extern void cubictcp_init(struct sock *sk) __ksym;
extern void cubictcp_cong_avoid(struct sock *sk, __u32 ack, __u32 acked) __ksym;
extern __u32 cubictcp_recalc_ssthresh(struct sock *sk) __ksym;
extern void cubictcp_state(struct sock *sk, __u8 new_state) __ksym;
extern void cubictcp_cwnd_event(struct sock *sk, enum tcp_ca_event event) __ksym;
extern __u32 tcp_reno_undo_cwnd(struct sock *sk) __ksym;

SEC("struct_ops/audit_cubic_init")
void BPF_PROG(audit_cubic_init, struct sock *sk)
{
	cubictcp_init(sk);
}

SEC("struct_ops/audit_cubic_cong_avoid")
void BPF_PROG(audit_cubic_cong_avoid, struct sock *sk, __u32 ack, __u32 acked)
{
	cubictcp_cong_avoid(sk, ack, acked);
}

SEC("struct_ops/audit_cubic_ssthresh")
__u32 BPF_PROG(audit_cubic_ssthresh, struct sock *sk)
{
	return cubictcp_recalc_ssthresh(sk);
}

SEC("struct_ops/audit_cubic_state")
void BPF_PROG(audit_cubic_state, struct sock *sk, __u8 new_state)
{
	cubictcp_state(sk, new_state);
}

SEC("struct_ops/audit_cubic_cwnd_event")
void BPF_PROG(audit_cubic_cwnd_event, struct sock *sk, enum tcp_ca_event event)
{
	cubictcp_cwnd_event(sk, event);
}

SEC("struct_ops/audit_cubic_undo")
__u32 BPF_PROG(audit_cubic_undo, struct sock *sk)
{
	return tcp_reno_undo_cwnd(sk);
}

SEC(".struct_ops")
struct tcp_congestion_ops audit_cubic_kfunc_probe = {
	.init       = (void *)audit_cubic_init,
	.cong_avoid = (void *)audit_cubic_cong_avoid,
	.ssthresh   = (void *)audit_cubic_ssthresh,
	.set_state  = (void *)audit_cubic_state,
	.cwnd_event = (void *)audit_cubic_cwnd_event,
	.undo_cwnd  = (void *)audit_cubic_undo,
	.name       = "ccr_audit_cubic",
};
