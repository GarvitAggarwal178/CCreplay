/* Capability audit A: independent compile+verify+register smoke test for
 * the three Reno reference kfuncs, from CCReplay's own wrapper shape (not
 * copied cn-spike object code -- written fresh against this kernel's BTF
 * to avoid taking the prior gate's result on faith). See
 * data/capability_audit.md section A.
 */
#include "bpf_tracing_net.h"
#include <bpf/bpf_tracing.h>

char _license[] SEC("license") = "GPL";

extern void tcp_reno_cong_avoid(struct sock *sk, __u32 ack, __u32 acked) __ksym;
extern __u32 tcp_reno_ssthresh(struct sock *sk) __ksym;
extern __u32 tcp_reno_undo_cwnd(struct sock *sk) __ksym;

SEC("struct_ops")
void BPF_PROG(audit_reno_init, struct sock *sk)
{
}

SEC("struct_ops")
void BPF_PROG(audit_reno_cong_avoid, struct sock *sk, __u32 ack, __u32 acked)
{
	tcp_reno_cong_avoid(sk, ack, acked);
}

SEC("struct_ops")
__u32 BPF_PROG(audit_reno_ssthresh, struct sock *sk)
{
	return tcp_reno_ssthresh(sk);
}

SEC("struct_ops")
__u32 BPF_PROG(audit_reno_undo_cwnd, struct sock *sk)
{
	return tcp_reno_undo_cwnd(sk);
}

SEC(".struct_ops")
struct tcp_congestion_ops audit_reno = {
	.init		= (void *)audit_reno_init,
	.ssthresh	= (void *)audit_reno_ssthresh,
	.cong_avoid	= (void *)audit_reno_cong_avoid,
	.undo_cwnd	= (void *)audit_reno_undo_cwnd,
	.name		= "audit_reno",
};
