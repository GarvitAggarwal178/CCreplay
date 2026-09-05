// Integer-semantics isolation test (pipeline's INTEGER-SEMANTICS TEST
// section): cubic_root/fls64 copied VERBATIM from
// data/kernel_source_ref/tcp_cubic.c lines 167-209 (real kernel source for
// this exact kernel version, not bpf_cubic.c), compiled and run natively,
// dumping (input, output) pairs across a broad deterministic range for
// cross-checking against user/cubic_model.py's Python port in
// data/audit_src/integer_semantics_check.py. This isolates the
// C-source-to-Python-port translation step BEFORE trusting any full-trace
// replay comparison -- exactly the pipeline's stated purpose ("fix
// arithmetic mismatches in isolation before debugging long traces").
#include <stdio.h>
#include <stdint.h>

typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;

static int fls64(u64 x)
{
	int num = 64 - 1;

	if (x == 0)
		return 0;

	if (!(x & (~0ull << (64 - 32)))) {
		num -= 32;
		x <<= 32;
	}
	if (!(x & (~0ull << (64 - 16)))) {
		num -= 16;
		x <<= 16;
	}
	if (!(x & (~0ull << (64 - 8)))) {
		num -= 8;
		x <<= 8;
	}
	if (!(x & (~0ull << (64 - 4)))) {
		num -= 4;
		x <<= 4;
	}
	if (!(x & (~0ull << (64 - 2)))) {
		num -= 2;
		x <<= 2;
	}
	if (!(x & (~0ull << (64 - 1))))
		num -= 1;

	return num + 1;
}

static u64 div64_u64(u64 dividend, u64 divisor)
{
	return dividend / divisor;
}

// tcp_cubic.c lines 167-209, byte-for-byte (only type renames: u8/u32/u64
// as declared above, matching the real kernel typedefs exactly).
static u32 cubic_root(u64 a)
{
	u32 x, b, shift;
	static const u8 v[] = {
		0,   54,   54,   54,  118,  118,  118,  118,
		123,  129,  134,  138,  143,  147,  151,  156,
		157,  161,  164,  168,  170,  173,  176,  179,
		181,  185,  187,  190,  192,  194,  197,  199,
		200,  202,  204,  206,  209,  211,  213,  215,
		217,  219,  221,  222,  224,  225,  227,  229,
		231,  232,  234,  236,  237,  239,  240,  242,
		244,  245,  246,  248,  250,  251,  252,  254,
	};

	b = fls64(a);
	if (b < 7) {
		return ((u32)v[(u32)a] + 35) >> 6;
	}

	b = ((b * 84) >> 8) - 1;
	shift = (u32)(a >> (b * 3));

	x = ((u32)(((u32)v[shift] + 10) << b)) >> 6;

	x = (2 * x + (u32)div64_u64(a, (u64)x * (u64)(x - 1)));
	x = ((x * 341) >> 10);
	return x;
}

int main(void)
{
	// Broad deterministic range: every value 0..10000 (covers the table
	// lookup path a<64 exhaustively, plus the Newton-Raphson path
	// immediately above it), then a log-spaced sweep up to the practical
	// ceiling for cube_factor*(last_max_cwnd-cwnd) with cwnd<1,000,000
	// packets (the real source's own documented precondition,
	// tcp_cubic.c lines 526-529): cube_factor ~= 2.68e9, times a cwnd
	// delta up to 1e6, ceiling ~2.68e15 -- well under 2^62 (~4.6e18), so
	// no u64 overflow in the multiply itself is in-scope here (checked
	// separately, this file only isolates cubic_root/fls64).
	for (u64 a = 0; a <= 10000; a++)
		printf("%llu %u\n", (unsigned long long)a, cubic_root(a));

	u64 milestones[] = {
		10001, 20000, 50000, 100000, 500000, 1000000, 5000000,
		10000000, 50000000, 100000000, 500000000, 1000000000ULL,
		5000000000ULL, 10000000000ULL, 50000000000ULL,
		100000000000ULL, 500000000000ULL, 1000000000000ULL,
		2680000000000000ULL, /* ~ceiling per comment above */
		(1ULL << 40), (1ULL << 50), (1ULL << 62),
	};
	for (size_t i = 0; i < sizeof(milestones)/sizeof(milestones[0]); i++)
		printf("%llu %u\n", (unsigned long long)milestones[i], cubic_root(milestones[i]));

	return 0;
}
