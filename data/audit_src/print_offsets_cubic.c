// N1.3 ground-truth layout tool (audit-only, disposable).
//
// Deliberately does NOT include vmlinux.h (it collides with libc's wchar_t
// under a native/userspace target, and pulling in the entire vmlinux.h just
// for one struct is unnecessary). Instead this mirrors struct bictcp
// field-for-field EXACTLY as reported by `bpftool btf dump file
// /sys/kernel/btf/vmlinux format c` against the live running kernel (ground
// truth, not upstream recollection) -- same field order, same declared
// types, no packing attribute (matches upstream tcp_cubic.c, a plain
// struct). The compiler's own ABI alignment then produces the real offsets;
// nothing here is hand-computed. sizeof is cross-checked against BTF's
// independently-reported STRUCT size=60 below.
#include <stdio.h>
#include <stddef.h>

typedef unsigned char  u8;
typedef unsigned short u16;
typedef unsigned int   u32;
typedef unsigned long long u64;

struct bictcp {
	u32 cnt;
	u32 last_max_cwnd;
	u32 last_cwnd;
	u32 last_time;
	u32 bic_origin_point;
	u32 bic_K;
	u32 delay_min;
	u32 epoch_start;
	u32 ack_cnt;
	u32 tcp_cwnd;
	u16 unused;
	u8  sample_cnt;
	u8  found;
	u32 round_start;
	u32 end_seq;
	u32 last_ack;
	u32 curr_rtt;
};

#define P(field) printf("%-20s offset=%-4zu size=%-4zu\n", #field, \
	offsetof(struct bictcp, field), sizeof(((struct bictcp *)0)->field))

int main(void)
{
	printf("sizeof(struct bictcp) = %zu (BTF-reported STRUCT size = 60, cross-check %s)\n",
	       sizeof(struct bictcp), sizeof(struct bictcp) == 60 ? "PASS" : "FAIL");
	printf("icsk_ca_priv capacity = 13 * sizeof(u64) = %zu bytes (from live BTF: "
	       "'u64 icsk_ca_priv[13]')\n", 13 * sizeof(u64));
	P(cnt);
	P(last_max_cwnd);
	P(last_cwnd);
	P(last_time);
	P(bic_origin_point);
	P(bic_K);
	P(delay_min);
	P(epoch_start);
	P(ack_cnt);
	P(tcp_cwnd);
	P(unused);
	P(sample_cnt);
	P(found);
	P(round_start);
	P(end_seq);
	P(last_ack);
	P(curr_rtt);
	return 0;
}
