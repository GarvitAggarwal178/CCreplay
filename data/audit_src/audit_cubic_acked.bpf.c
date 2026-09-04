#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include "bpf_tracing_net.h"
char _license[] SEC("license") = "GPL";

extern void cubictcp_acked(struct sock *sk, const struct ack_sample *sample) __ksym;

SEC("struct_ops/audit_cubic_acked")
void BPF_PROG(audit_cubic_acked, struct sock *sk, const struct ack_sample *sample)
{
	cubictcp_acked(sk, sample);
}

SEC(".struct_ops")
struct tcp_congestion_ops audit_cubic_acked_probe = {
	.pkts_acked = (void *)audit_cubic_acked,
	.name       = "ccr_audit_ackd",
};
