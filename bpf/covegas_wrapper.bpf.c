/* CCReplay CoVegas wrapper recorder — Replay ABI v2 (ADR-022..024).
 *
 * Unlike bpf/reno_wrapper.bpf.c and bpf/cubic_wrapper.bpf.c, this recorder
 * does NOT delegate to a kernel-native kfunc -- no such entity exists for
 * CoVegas (ADR-022). The internal algorithm helpers below
 * (compute_queue_est/cubic_reset/bictcp_update/cubic_growth/update_dlv_rate/
 * handle_minrtt_probe/revert_to_delay/handle_compete_mode/handle_delay_mode)
 * are copied near-verbatim from the read-only reference
 * (~/cn-spike/covegas/src/covegas.bpf.c, repo HEAD bab7ab7, file itself last
 * touched at b5bc0be "v4" -- docs/PROVENANCE.md), unchanged in logic. Only
 * the five SEC("struct_ops") entry points are new: they add recording
 * instrumentation (PRE/POST snapshots, two independent clock brackets,
 * sequence/drop counters, ring-buffer emission) around calls to the
 * unchanged helpers, following the same fill_common/snap_pre/snap_post
 * pattern as reno_wrapper.bpf.c/cubic_wrapper.bpf.c. This recorder *is* the
 * live reference (ADR-022) -- there is no separate kernel oracle to compare
 * against.
 *
 * Manifest: {init, ssthresh, cong_avoid, undo_cwnd, pkts_acked} -- exactly
 * covegas's real struct tcp_congestion_ops table. Private state: 17
 * dedicated fields + a mode-dependent union (ADR-023, D3 audit).
 */
#include "bpf_tracing_net.h"
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>
#include "ccr_event_v2.h"

char _license[] SEC("license") = "GPL";

#define min(a, b) ((a) < (b) ? (a) : (b))
#define max(a, b) ((a) > (b) ? (a) : (b))

static bool ccr_before(__u32 seq1, __u32 seq2)
{
	return (__s32)(seq1 - seq2) < 0;
}
#define ccr_after(seq2, seq1) ccr_before(seq1, seq2)

extern __u32 tcp_slow_start(struct tcp_sock *tp, __u32 acked) __ksym;
extern void tcp_cong_avoid_ai(struct tcp_sock *tp, __u32 w, __u32 acked) __ksym;
extern __u32 tcp_reno_undo_cwnd(struct sock *sk) __ksym;

#define MODE_DELAY   0
#define MODE_COMPETE 1

#define T_US_DEFAULT 10000
#define K_WINDOWS_DEFAULT 4
#define W_RTTS_DEFAULT 4
#define MINRTT_PERIOD_MS_DEFAULT 10000
#define MINRTT_SKIP_MS_DEFAULT 30000
#define ALPHA_DEFAULT 2
#define BETA_DEFAULT 4
#define DETECTOR_ENABLED_DEFAULT 1
#define RATE_SETTLE_MS_DEFAULT 1000
#define RATE_JUMP_NUM_DEFAULT 3
#define RATE_JUMP_DEN_DEFAULT 2
#define EPOCH_KEEP_MS_DEFAULT 5000
#define HOLD_MS_DEFAULT 500

const volatile __u32 T_us = T_US_DEFAULT;
const volatile __u32 K_WINDOWS = K_WINDOWS_DEFAULT;
const volatile __u32 W_RTTS = W_RTTS_DEFAULT;
const volatile __u32 MINRTT_PERIOD_MS = MINRTT_PERIOD_MS_DEFAULT;
const volatile __u32 MINRTT_SKIP_MS = MINRTT_SKIP_MS_DEFAULT;
const volatile __u32 ALPHA = ALPHA_DEFAULT;
const volatile __u32 BETA = BETA_DEFAULT;
const volatile __u32 DETECTOR_ENABLED = DETECTOR_ENABLED_DEFAULT;
const volatile __u32 RATE_SETTLE_MS = RATE_SETTLE_MS_DEFAULT;
const volatile __u32 RATE_JUMP_NUM = RATE_JUMP_NUM_DEFAULT;
const volatile __u32 RATE_JUMP_DEN = RATE_JUMP_DEN_DEFAULT;
const volatile __u32 EPOCH_KEEP_MS = EPOCH_KEEP_MS_DEFAULT;
const volatile __u32 HOLD_MS = HOLD_MS_DEFAULT;

#define BICTCP_BETA_SCALE 1024
#define BICTCP_HZ 10

static const int fast_convergence = 1;
static const int beta = 717;
static const int bic_scale = 41;
static const int tcp_friendliness = 1;

static const __u32 cube_rtt_scale = (bic_scale * 10);
static const __u32 beta_scale = 8 * (BICTCP_BETA_SCALE + beta) / 3 / (BICTCP_BETA_SCALE - beta);
static const __u64 cube_factor = (__u64)(1ull << (10 + 3 * BICTCP_HZ)) / (bic_scale * 10);

extern unsigned long CONFIG_HZ __kconfig;
#define HZ CONFIG_HZ
#define USEC_PER_SEC 1000000UL
#define USEC_PER_JIFFY (USEC_PER_SEC / HZ)

static __u64 ccr_div64_u64(__u64 dividend, __u64 divisor)
{
	return dividend / divisor;
}

#define BITS_PER_U64 (sizeof(__u64) * 8)
static int ccr_fls64(__u64 x)
{
	int num = BITS_PER_U64 - 1;

	if (x == 0)
		return 0;
	if (!(x & (~0ull << (BITS_PER_U64 - 32)))) { num -= 32; x <<= 32; }
	if (!(x & (~0ull << (BITS_PER_U64 - 16)))) { num -= 16; x <<= 16; }
	if (!(x & (~0ull << (BITS_PER_U64 - 8))))  { num -= 8;  x <<= 8;  }
	if (!(x & (~0ull << (BITS_PER_U64 - 4))))  { num -= 4;  x <<= 4;  }
	if (!(x & (~0ull << (BITS_PER_U64 - 2))))  { num -= 2;  x <<= 2;  }
	if (!(x & (~0ull << (BITS_PER_U64 - 1))))  { num -= 1; }
	return num + 1;
}

static const __u8 cv_v[] = {
	0,   54,   54,   54,  118,  118,  118,  118,
	123,  129,  134,  138,  143,  147,  151,  156,
	157,  161,  164,  168,  170,  173,  176,  179,
	181,  185,  187,  190,  192,  194,  197,  199,
	200,  202,  204,  206,  209,  211,  213,  215,
	217,  219,  221,  222,  224,  225,  227,  229,
	231,  232,  234,  236,  237,  239,  240,  242,
	244,  245,  246,  248,  250,  251,  252,  254,
};

static __u32 ccr_cubic_root(__u64 a)
{
	__u32 x, b, shift;

	if (a < 64)
		return ((__u32)cv_v[(__u32)a] + 35) >> 6;

	b = ccr_fls64(a);
	b = ((b * 84) >> 8) - 1;
	shift = (a >> (b * 3));

	if (shift >= 64)
		return 0;

	x = ((__u32)(((__u32)cv_v[shift] + 10) << b)) >> 6;
	x = (2 * x + (__u32)ccr_div64_u64(a, (__u64)x * (__u64)(x - 1)));
	x = ((x * 341) >> 10);
	return x;
}

/* ---- per-connection state: byte-for-byte identical field list/order to
 * the read-only reference's struct covegas (D3 audit). ---- */
struct covegas {
	__u32 min_rtt_us;
	__u32 recent_min_us;
	__u32 detect_count;

	__u32 last_max_cwnd;
	__u32 epoch_start;

	__u32 cwnd_before_minrtt_probe;
	__u32 minrtt_probe_min_us;
	__u32 last_queue_est_pkts;

	__u32 dlv_rate_bps;
	__u32 dlv_rate_compete;
	__u32 dlv_rate_max;

	__u32 last_compete_exit_jiffies;
	__u32 compete_enter_jiffies;

	__u64 last_minrtt_probe_ns;
	__u64 probe_action_start_ns;

	union {
		struct {
			__u32 window_start_ack;
			__u32 cwnd_at_window_start;
			__u32 rtts_in_window;
			__u32 saved_bic_origin_point;
			__u32 saved_bic_K;
			__u32 detect_hold_until;
		} delay;
		struct {
			__u32 cnt;
			__u32 last_cwnd;
			__u32 last_time;
			__u32 bic_origin_point;
			__u32 bic_K;
			__u32 ack_cnt;
			__u32 tcp_cwnd;
		} cubic;
	} u;

	__u8 mode;
	__u8 minrtt_probing;
};

struct ccr_counters {
	__u64 invocations;
	__u64 emitted;
	__u64 drops;
	__u64 clock_jiffies_stable;
	__u64 clock_jiffies_ambiguous;
	__u64 clock_ktime_stable;
	__u64 clock_ktime_ambiguous;
};

struct {
	__uint(type, BPF_MAP_TYPE_ARRAY);
	__uint(max_entries, 1);
	__type(key, __u32);
	__type(value, struct ccr_counters);
} ccr_counters_map SEC(".maps");

struct {
	__uint(type, BPF_MAP_TYPE_RINGBUF);
	__uint(max_entries, 1 << 24);
} ccr_events SEC(".maps");

/* ==== algorithm helpers, logic unchanged from the read-only reference ==== */

static __u32 compute_queue_est(struct tcp_sock *tp, struct covegas *ca)
{
	__u32 srtt = tp->srtt_us >> 3;

	if (!ca->min_rtt_us || srtt <= ca->min_rtt_us)
		return 0;
	return (tp->snd_cwnd * (srtt - ca->min_rtt_us)) / srtt;
}

static void cubic_reset(struct covegas *ca)
{
	ca->u.cubic.cnt = 0;
	ca->u.cubic.last_cwnd = 0;
	ca->u.cubic.last_time = 0;
	ca->u.cubic.bic_origin_point = 0;
	ca->u.cubic.bic_K = 0;
	ca->u.cubic.ack_cnt = 0;
	ca->u.cubic.tcp_cwnd = 0;
	ca->last_max_cwnd = 0;
	ca->epoch_start = 0;
}

static void bictcp_update(struct covegas *ca, __u32 cwnd, __u32 acked)
{
	__u32 delta, bic_target, max_cnt;
	__u64 offs, t;

	ca->u.cubic.ack_cnt += acked;

	if (ca->u.cubic.last_cwnd == cwnd &&
	    (__s32)(tcp_jiffies32 - ca->u.cubic.last_time) <= HZ / 32)
		return;

	if (ca->epoch_start && tcp_jiffies32 == ca->u.cubic.last_time)
		goto tcp_friendliness;

	ca->u.cubic.last_cwnd = cwnd;
	ca->u.cubic.last_time = tcp_jiffies32;

	if (ca->epoch_start == 0) {
		ca->epoch_start = tcp_jiffies32;
		ca->u.cubic.ack_cnt = acked;
		ca->u.cubic.tcp_cwnd = cwnd;

		if (ca->last_max_cwnd <= cwnd) {
			ca->u.cubic.bic_K = 0;
			ca->u.cubic.bic_origin_point = cwnd;
		} else {
			ca->u.cubic.bic_K = ccr_cubic_root(cube_factor * (ca->last_max_cwnd - cwnd));
			ca->u.cubic.bic_origin_point = ca->last_max_cwnd;
		}
	}

	t = (__s32)(tcp_jiffies32 - ca->epoch_start) * USEC_PER_JIFFY;
	t += ca->min_rtt_us;
	t <<= BICTCP_HZ;
	t /= USEC_PER_SEC;

	if (t < ca->u.cubic.bic_K)
		offs = ca->u.cubic.bic_K - t;
	else
		offs = t - ca->u.cubic.bic_K;

	delta = (cube_rtt_scale * offs * offs * offs) >> (10 + 3 * BICTCP_HZ);
	if (t < ca->u.cubic.bic_K)
		bic_target = ca->u.cubic.bic_origin_point - delta;
	else
		bic_target = ca->u.cubic.bic_origin_point + delta;

	if (bic_target > cwnd)
		ca->u.cubic.cnt = cwnd / (bic_target - cwnd);
	else
		ca->u.cubic.cnt = 100 * cwnd;

	if (ca->last_max_cwnd == 0 && ca->u.cubic.cnt > 20)
		ca->u.cubic.cnt = 20;

tcp_friendliness:
	if (tcp_friendliness) {
		__u32 scale = beta_scale;
		__u32 n;

		delta = (cwnd * scale) >> 3;
		if (ca->u.cubic.ack_cnt > delta && delta) {
			n = ca->u.cubic.ack_cnt / delta;
			ca->u.cubic.ack_cnt -= n * delta;
			ca->u.cubic.tcp_cwnd += n;
		}

		if (ca->u.cubic.tcp_cwnd > cwnd) {
			delta = ca->u.cubic.tcp_cwnd - cwnd;
			max_cnt = cwnd / delta;
			if (ca->u.cubic.cnt > max_cnt)
				ca->u.cubic.cnt = max_cnt;
		}
	}

	ca->u.cubic.cnt = max(ca->u.cubic.cnt, 2U);
}

static void cubic_growth(struct tcp_sock *tp, struct covegas *ca, __u32 acked)
{
	if (tcp_in_slow_start(tp)) {
		tcp_slow_start(tp, acked);
		return;
	}
	bictcp_update(ca, tp->snd_cwnd, acked);
	tcp_cong_avoid_ai(tp, ca->u.cubic.cnt, acked);
}

static void update_dlv_rate(struct tcp_sock *tp, struct covegas *ca)
{
	__u32 interval_us = BPF_CORE_READ(tp, rate_interval_us);
	__u32 delivered = BPF_CORE_READ(tp, rate_delivered);
	__u32 mss = BPF_CORE_READ(tp, mss_cache);
	__u8 app_limited = BPF_CORE_READ_BITFIELD(tp, rate_app_limited);
	__u64 rate_Bps;

	if (app_limited || interval_us == 0 || !mss)
		return;

	rate_Bps = ((__u64)delivered * (__u64)mss * USEC_PER_SEC) / interval_us;
	if (rate_Bps > 0xFFFFFFFFULL)
		rate_Bps = 0xFFFFFFFFULL;

	if (ca->dlv_rate_bps == 0)
		ca->dlv_rate_bps = (__u32)rate_Bps;
	else
		ca->dlv_rate_bps = ca->dlv_rate_bps - (ca->dlv_rate_bps >> 3) + ((__u32)rate_Bps >> 3);

	if (ca->dlv_rate_bps > ca->dlv_rate_max)
		ca->dlv_rate_max = ca->dlv_rate_bps;
}

static int handle_minrtt_probe(struct tcp_sock *tp, struct covegas *ca, __u64 now)
{
	if (ca->minrtt_probing) {
		__u64 dur_ns = 200ULL * 1000000ULL;
		__u64 one_rtt_ns = (__u64)(tp->srtt_us >> 3) * 1000ULL;

		if (one_rtt_ns > dur_ns)
			dur_ns = one_rtt_ns;

		if (now - ca->probe_action_start_ns >= dur_ns) {
			if (ca->minrtt_probe_min_us != ~0U) {
				__u32 new_floor = ca->minrtt_probe_min_us;

				if (ca->recent_min_us != ~0U && ca->recent_min_us < new_floor)
					new_floor = ca->recent_min_us;
				ca->min_rtt_us = new_floor;
			}
			tp->snd_cwnd = ca->cwnd_before_minrtt_probe;

			if (ca->mode == MODE_COMPETE && ca->epoch_start) {
				__u32 delta_jiffies = (__u32)(((now - ca->probe_action_start_ns) * HZ)
							       / 1000000000ULL);

				ca->epoch_start += delta_jiffies;
			}

			ca->minrtt_probing = 0;
			ca->last_minrtt_probe_ns = now;
		}
		return 1;
	}

	{
		__u64 period_ns = (ca->mode == MODE_COMPETE && ca->dlv_rate_compete != 0)
			? (__u64)MINRTT_SKIP_MS * 1000000ULL
			: (__u64)MINRTT_PERIOD_MS * 1000000ULL;

		if (now - ca->last_minrtt_probe_ns >= period_ns) {
			ca->cwnd_before_minrtt_probe = tp->snd_cwnd;
			ca->minrtt_probe_min_us = ~0U;
			tp->snd_cwnd = 4;
			ca->minrtt_probing = 1;
			ca->probe_action_start_ns = now;
			ca->dlv_rate_max = ca->dlv_rate_max - (ca->dlv_rate_max >> 4);
			return 1;
		}
	}

	return 0;
}

static void revert_to_delay(struct tcp_sock *tp, struct covegas *ca)
{
	__u32 save_origin = ca->u.cubic.bic_origin_point;
	__u32 save_K = ca->u.cubic.bic_K;
	__u32 mss = BPF_CORE_READ(tp, mss_cache);
	__u64 bdp_bytes = ((__u64)ca->dlv_rate_bps * ca->min_rtt_us) / 1000000ULL;
	__u32 bdp_pkts = mss ? (__u32)(bdp_bytes / mss) : 0;
	__u32 target = bdp_pkts + BETA;

	if (tp->snd_cwnd > target)
		tp->snd_cwnd = max(target, 4U);

	ca->mode = MODE_DELAY;
	ca->detect_count = 0;
	ca->last_compete_exit_jiffies = tcp_jiffies32;
	ca->u.delay.window_start_ack = tp->snd_nxt;
	ca->u.delay.cwnd_at_window_start = tp->snd_cwnd;
	ca->u.delay.rtts_in_window = 0;
	ca->u.delay.saved_bic_origin_point = save_origin;
	ca->u.delay.saved_bic_K = save_K;
	ca->u.delay.detect_hold_until = tcp_jiffies32 + (HOLD_MS * HZ) / 1000;
	ca->recent_min_us = ~0U;
}

static void handle_compete_mode(struct tcp_sock *tp, struct covegas *ca, __u32 acked)
{
	if (ca->dlv_rate_compete == 0) {
		__u32 elapsed_jiffies = tcp_jiffies32 - ca->compete_enter_jiffies;

		if (elapsed_jiffies >= (RATE_SETTLE_MS * HZ) / 1000 && ca->dlv_rate_bps) {
			if (ca->dlv_rate_bps < (ca->dlv_rate_max * 3) / 4) {
				ca->dlv_rate_compete = ca->dlv_rate_bps;
			} else {
				revert_to_delay(tp, ca);
				return;
			}
		}
	} else if (ca->dlv_rate_bps > (RATE_JUMP_NUM * ca->dlv_rate_compete) / RATE_JUMP_DEN) {
		revert_to_delay(tp, ca);
		return;
	}

	cubic_growth(tp, ca, acked);
}

static void handle_delay_mode(struct tcp_sock *tp, struct covegas *ca, __u32 ack, __u32 acked)
{
	__u32 queue_est = compute_queue_est(tp, ca);

	ca->last_queue_est_pkts = queue_est;

	if (tcp_in_slow_start(tp)) {
		if (queue_est < ALPHA)
			tcp_slow_start(tp, acked);
		else
			tp->snd_ssthresh = tp->snd_cwnd;
	}

	if (!ccr_after(ack, ca->u.delay.window_start_ack))
		return;

	ca->u.delay.rtts_in_window++;
	ca->u.delay.window_start_ack = tp->snd_nxt;

	if (ca->u.delay.rtts_in_window < W_RTTS)
		return;

	if (!tcp_in_slow_start(tp)) {
		__u32 fresh_queue_est = compute_queue_est(tp, ca);

		if (fresh_queue_est < ALPHA)
			tp->snd_cwnd += 1;
		else if (fresh_queue_est > BETA)
			tp->snd_cwnd -= 1;
		if (tp->snd_cwnd < 4)
			tp->snd_cwnd = 4;
	}

	if (DETECTOR_ENABLED && ca->min_rtt_us && ca->recent_min_us != ~0U &&
	    !ccr_before(tcp_jiffies32, ca->u.delay.detect_hold_until)) {
		__u32 elevated = ca->recent_min_us > ca->min_rtt_us &&
				  (ca->recent_min_us - ca->min_rtt_us) > T_us;
		__u32 yielding = tp->snd_cwnd <= ca->u.delay.cwnd_at_window_start;

		if (elevated && yielding) {
			ca->detect_count++;
			if (ca->detect_count >= K_WINDOWS) {
				__u32 gap_jiffies = tcp_jiffies32 - ca->last_compete_exit_jiffies;
				int keep_epoch = ca->epoch_start != 0 &&
						 gap_jiffies < (EPOCH_KEEP_MS * HZ) / 1000;
				__u32 saved_origin = ca->u.delay.saved_bic_origin_point;
				__u32 saved_K = ca->u.delay.saved_bic_K;

				ca->mode = MODE_COMPETE;
				ca->dlv_rate_compete = 0;
				ca->compete_enter_jiffies = tcp_jiffies32;

				if (keep_epoch) {
					ca->epoch_start += gap_jiffies;
					ca->u.cubic.cnt = 0;
					ca->u.cubic.last_cwnd = 0;
					ca->u.cubic.last_time = 0;
					ca->u.cubic.ack_cnt = 0;
					ca->u.cubic.tcp_cwnd = 0;
					ca->u.cubic.bic_origin_point = saved_origin;
					ca->u.cubic.bic_K = saved_K;
				} else {
					cubic_reset(ca);
				}
				return;
			}
		} else {
			ca->detect_count = 0;
		}
	} else {
		ca->detect_count = 0;
	}

	ca->u.delay.rtts_in_window = 0;
	ca->recent_min_us = ~0U;
	ca->u.delay.cwnd_at_window_start = tp->snd_cwnd;
}

/* ==== recorder plumbing (new CCReplay code) ==== */

static __always_inline struct ccr_counters *get_counters(void)
{
	__u32 key = 0;

	return bpf_map_lookup_elem(&ccr_counters_map, &key);
}

static __always_inline __u64 alloc_seq(struct ccr_counters *c)
{
	return __sync_fetch_and_add(&c->invocations, 1);
}

/* now_ktime must be the SAME bpf_ktime_get_ns() value the calling entry
 * point will also feed to the algorithm logic as "now" (handle_minrtt_probe/
 * covegas_init) -- a single shared read, not a second independent one.
 * (Found via E2 self-replay against the loopback smoke trace: an earlier
 * version called bpf_ktime_get_ns() separately in fill_common and again for
 * the algorithm's own `now`, and since ktime has effectively no observable
 * "stable" window at all -- confirmed empirically, clock_ktime_ambiguous
 * was 100% of events in that smoke test -- those two independent reads
 * were, unsurprisingly, never equal, producing a one-event PRE mismatch on
 * covegas_init's `last_minrtt_probe_ns`. Fixed by sharing one read.) */
static __always_inline void fill_common(struct ccr_event_v2 *e, struct sock *sk,
					 __u64 seq, __u32 callback_id, __u64 now_ktime)
{
	e->seq = seq;
	e->sock_cookie = (__u64)(long)sk;
	e->ts_ns = now_ktime;
	e->callback_id = callback_id;
	e->_pad0 = 0;
	e->in_ack = 0;
	e->in_acked = 0;
	e->in_sample_rtt_us = 0;
	e->in_sample_pkts_acked = 0;
	e->in_sample_in_flight = 0;
	e->result_valid = 0;
	e->result = 0;
	e->clock_jiffies32_before = tcp_jiffies32;
	e->clock_ktime_ns_before = now_ktime;
}

static __always_inline void finish_clock(struct ccr_event_v2 *e, struct ccr_counters *c)
{
	e->clock_jiffies32_after = tcp_jiffies32;
	e->clock_ktime_ns_after = bpf_ktime_get_ns();
	if (e->clock_jiffies32_after == e->clock_jiffies32_before)
		__sync_fetch_and_add(&c->clock_jiffies_stable, 1);
	else
		__sync_fetch_and_add(&c->clock_jiffies_ambiguous, 1);
	if (e->clock_ktime_ns_after == e->clock_ktime_ns_before)
		__sync_fetch_and_add(&c->clock_ktime_stable, 1);
	else
		__sync_fetch_and_add(&c->clock_ktime_ambiguous, 1);
}

static __always_inline void snap_private(struct ccr_event_v2 *e, struct covegas *ca, int is_post)
{
	__u8 raw[CCR_ICSK_CA_PRIV_BYTES_V2];

	bpf_probe_read_kernel(raw, sizeof(raw), (void *)ca);

	if (is_post) {
		e->priv_post_min_rtt_us = ca->min_rtt_us;
		e->priv_post_recent_min_us = ca->recent_min_us;
		e->priv_post_detect_count = ca->detect_count;
		e->priv_post_last_max_cwnd = ca->last_max_cwnd;
		e->priv_post_epoch_start = ca->epoch_start;
		e->priv_post_cwnd_before_minrtt_probe = ca->cwnd_before_minrtt_probe;
		e->priv_post_minrtt_probe_min_us = ca->minrtt_probe_min_us;
		e->priv_post_last_queue_est_pkts = ca->last_queue_est_pkts;
		e->priv_post_dlv_rate_bps = ca->dlv_rate_bps;
		e->priv_post_dlv_rate_compete = ca->dlv_rate_compete;
		e->priv_post_dlv_rate_max = ca->dlv_rate_max;
		e->priv_post_last_compete_exit_jiffies = ca->last_compete_exit_jiffies;
		e->priv_post_compete_enter_jiffies = ca->compete_enter_jiffies;
		e->priv_post_last_minrtt_probe_ns = ca->last_minrtt_probe_ns;
		e->priv_post_probe_action_start_ns = ca->probe_action_start_ns;
		e->priv_post_mode = ca->mode;
		e->priv_post_minrtt_probing = ca->minrtt_probing;
		e->priv_post_delay_window_start_ack = ca->u.delay.window_start_ack;
		e->priv_post_delay_cwnd_at_window_start = ca->u.delay.cwnd_at_window_start;
		e->priv_post_delay_rtts_in_window = ca->u.delay.rtts_in_window;
		e->priv_post_delay_saved_bic_origin_point = ca->u.delay.saved_bic_origin_point;
		e->priv_post_delay_saved_bic_K = ca->u.delay.saved_bic_K;
		e->priv_post_delay_detect_hold_until = ca->u.delay.detect_hold_until;
		e->priv_post_cubic_cnt = ca->u.cubic.cnt;
		e->priv_post_cubic_last_cwnd = ca->u.cubic.last_cwnd;
		e->priv_post_cubic_last_time = ca->u.cubic.last_time;
		e->priv_post_cubic_bic_origin_point = ca->u.cubic.bic_origin_point;
		e->priv_post_cubic_bic_K = ca->u.cubic.bic_K;
		e->priv_post_cubic_ack_cnt = ca->u.cubic.ack_cnt;
		e->priv_post_cubic_tcp_cwnd = ca->u.cubic.tcp_cwnd;
		__builtin_memcpy(e->priv_post_raw, raw, sizeof(raw));
	} else {
		e->priv_pre_min_rtt_us = ca->min_rtt_us;
		e->priv_pre_recent_min_us = ca->recent_min_us;
		e->priv_pre_detect_count = ca->detect_count;
		e->priv_pre_last_max_cwnd = ca->last_max_cwnd;
		e->priv_pre_epoch_start = ca->epoch_start;
		e->priv_pre_cwnd_before_minrtt_probe = ca->cwnd_before_minrtt_probe;
		e->priv_pre_minrtt_probe_min_us = ca->minrtt_probe_min_us;
		e->priv_pre_last_queue_est_pkts = ca->last_queue_est_pkts;
		e->priv_pre_dlv_rate_bps = ca->dlv_rate_bps;
		e->priv_pre_dlv_rate_compete = ca->dlv_rate_compete;
		e->priv_pre_dlv_rate_max = ca->dlv_rate_max;
		e->priv_pre_last_compete_exit_jiffies = ca->last_compete_exit_jiffies;
		e->priv_pre_compete_enter_jiffies = ca->compete_enter_jiffies;
		e->priv_pre_last_minrtt_probe_ns = ca->last_minrtt_probe_ns;
		e->priv_pre_probe_action_start_ns = ca->probe_action_start_ns;
		e->priv_pre_mode = ca->mode;
		e->priv_pre_minrtt_probing = ca->minrtt_probing;
		e->priv_pre_delay_window_start_ack = ca->u.delay.window_start_ack;
		e->priv_pre_delay_cwnd_at_window_start = ca->u.delay.cwnd_at_window_start;
		e->priv_pre_delay_rtts_in_window = ca->u.delay.rtts_in_window;
		e->priv_pre_delay_saved_bic_origin_point = ca->u.delay.saved_bic_origin_point;
		e->priv_pre_delay_saved_bic_K = ca->u.delay.saved_bic_K;
		e->priv_pre_delay_detect_hold_until = ca->u.delay.detect_hold_until;
		e->priv_pre_cubic_cnt = ca->u.cubic.cnt;
		e->priv_pre_cubic_last_cwnd = ca->u.cubic.last_cwnd;
		e->priv_pre_cubic_last_time = ca->u.cubic.last_time;
		e->priv_pre_cubic_bic_origin_point = ca->u.cubic.bic_origin_point;
		e->priv_pre_cubic_bic_K = ca->u.cubic.bic_K;
		e->priv_pre_cubic_ack_cnt = ca->u.cubic.ack_cnt;
		e->priv_pre_cubic_tcp_cwnd = ca->u.cubic.tcp_cwnd;
		__builtin_memcpy(e->priv_pre_raw, raw, sizeof(raw));
	}
}

static __always_inline void snap_shared_pre(struct ccr_event_v2 *e, struct sock *sk)
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
	e->pre_mss_cache = BPF_CORE_READ(tp, mss_cache);
	e->pre_rate_delivered = BPF_CORE_READ(tp, rate_delivered);
	e->pre_rate_interval_us = BPF_CORE_READ(tp, rate_interval_us);
	e->pre_rate_app_limited = BPF_CORE_READ_BITFIELD(tp, rate_app_limited);
	e->_pad2[0] = e->_pad2[1] = e->_pad2[2] = 0;
	e->pre_srtt_us = BPF_CORE_READ(tp, srtt_us);
}

static __always_inline void snap_post(struct ccr_event_v2 *e, struct sock *sk)
{
	struct tcp_sock *tp = (struct tcp_sock *)sk;

	e->post_snd_cwnd = BPF_CORE_READ(tp, snd_cwnd);
	e->post_snd_cwnd_cnt = BPF_CORE_READ(tp, snd_cwnd_cnt);
	e->post_snd_ssthresh = BPF_CORE_READ(tp, snd_ssthresh);
}

SEC("struct_ops")
void BPF_PROG(ccr_covegas_init, struct sock *sk)
{
	struct tcp_sock *tp = tcp_sk(sk);
	struct covegas *ca = (struct covegas *)inet_csk_ca(sk);
	struct ccr_counters *c = get_counters();
	__u64 seq, now = bpf_ktime_get_ns(); /* single shared read -- see fill_common's comment */
	struct ccr_event_v2 *e = NULL;

	if (c) {
		seq = alloc_seq(c);
		e = bpf_ringbuf_reserve(&ccr_events, sizeof(*e), 0);
		if (!e) {
			__sync_fetch_and_add(&c->drops, 1);
		} else {
			fill_common(e, sk, seq, CCR_CB_INIT, now);
			snap_shared_pre(e, sk);
			snap_private(e, ca, 0);
		}
	}

	ca->min_rtt_us = 0;
	ca->recent_min_us = ~0U;
	ca->detect_count = 0;
	ca->last_max_cwnd = 0;
	ca->epoch_start = 0;
	ca->cwnd_before_minrtt_probe = 0;
	ca->minrtt_probe_min_us = ~0U;
	ca->last_queue_est_pkts = 0;
	ca->dlv_rate_bps = 0;
	ca->dlv_rate_compete = 0;
	ca->dlv_rate_max = 0;
	ca->last_compete_exit_jiffies = 0;
	ca->compete_enter_jiffies = 0;
	ca->last_minrtt_probe_ns = now;
	ca->probe_action_start_ns = 0;
	ca->u.delay.window_start_ack = tp->snd_nxt;
	ca->u.delay.cwnd_at_window_start = tp->snd_cwnd;
	ca->u.delay.rtts_in_window = 0;
	ca->u.delay.saved_bic_origin_point = 0;
	ca->u.delay.saved_bic_K = 0;
	ca->u.delay.detect_hold_until = 0;
	ca->mode = MODE_DELAY;
	ca->minrtt_probing = 0;

	if (e) {
		snap_post(e, sk);
		snap_private(e, ca, 1);
		finish_clock(e, c);
		bpf_ringbuf_submit(e, 0);
		__sync_fetch_and_add(&c->emitted, 1);
	}
}

SEC("struct_ops")
void BPF_PROG(ccr_covegas_cong_avoid, struct sock *sk, __u32 ack, __u32 acked)
{
	struct tcp_sock *tp = tcp_sk(sk);
	struct covegas *ca = (struct covegas *)inet_csk_ca(sk);
	struct ccr_counters *c = get_counters();
	__u64 seq, now = bpf_ktime_get_ns(); /* single shared read -- see fill_common's comment */
	struct ccr_event_v2 *e = NULL;

	if (!tcp_is_cwnd_limited(sk))
		return;

	if (c) {
		seq = alloc_seq(c);
		e = bpf_ringbuf_reserve(&ccr_events, sizeof(*e), 0);
		if (!e) {
			__sync_fetch_and_add(&c->drops, 1);
		} else {
			fill_common(e, sk, seq, CCR_CB_CONG_AVOID, now);
			e->in_ack = ack;
			e->in_acked = acked;
			snap_shared_pre(e, sk);
			snap_private(e, ca, 0);
		}
	}

	if (!handle_minrtt_probe(tp, ca, now)) {
		if (ca->mode == MODE_COMPETE)
			handle_compete_mode(tp, ca, acked);
		else
			handle_delay_mode(tp, ca, ack, acked);
	}

	if (e) {
		snap_post(e, sk);
		snap_private(e, ca, 1);
		finish_clock(e, c);
		bpf_ringbuf_submit(e, 0);
		__sync_fetch_and_add(&c->emitted, 1);
	}
}

SEC("struct_ops")
__u32 BPF_PROG(ccr_covegas_ssthresh, struct sock *sk)
{
	struct tcp_sock *tp = tcp_sk(sk);
	struct covegas *ca = (struct covegas *)inet_csk_ca(sk);
	struct ccr_counters *c = get_counters();
	__u64 seq;
	struct ccr_event_v2 *e;
	__u32 ret;

	if (!c) {
		goto do_ssthresh;
	}
	seq = alloc_seq(c);
	e = bpf_ringbuf_reserve(&ccr_events, sizeof(*e), 0);
	if (!e) {
		__sync_fetch_and_add(&c->drops, 1);
		goto do_ssthresh;
	}
	fill_common(e, sk, seq, CCR_CB_SSTHRESH, bpf_ktime_get_ns());
	snap_shared_pre(e, sk);
	snap_private(e, ca, 0);

	ca->epoch_start = 0;
	if (tp->snd_cwnd < ca->last_max_cwnd && fast_convergence)
		ca->last_max_cwnd = (tp->snd_cwnd * (BICTCP_BETA_SCALE + beta)) / (2 * BICTCP_BETA_SCALE);
	else
		ca->last_max_cwnd = tp->snd_cwnd;
	ret = max((tp->snd_cwnd * beta) / BICTCP_BETA_SCALE, 2U);

	e->result_valid = 1;
	e->result = ret;
	snap_post(e, sk);
	snap_private(e, ca, 1);
	finish_clock(e, c);
	bpf_ringbuf_submit(e, 0);
	__sync_fetch_and_add(&c->emitted, 1);
	return ret;

do_ssthresh:
	ca->epoch_start = 0;
	if (tp->snd_cwnd < ca->last_max_cwnd && fast_convergence)
		ca->last_max_cwnd = (tp->snd_cwnd * (BICTCP_BETA_SCALE + beta)) / (2 * BICTCP_BETA_SCALE);
	else
		ca->last_max_cwnd = tp->snd_cwnd;
	return max((tp->snd_cwnd * beta) / BICTCP_BETA_SCALE, 2U);
}

SEC("struct_ops")
__u32 BPF_PROG(ccr_covegas_undo_cwnd, struct sock *sk)
{
	struct covegas *ca = (struct covegas *)inet_csk_ca(sk);
	struct ccr_counters *c = get_counters();
	__u64 seq;
	struct ccr_event_v2 *e;
	__u32 ret;

	if (!c)
		return tcp_reno_undo_cwnd(sk);

	seq = alloc_seq(c);
	e = bpf_ringbuf_reserve(&ccr_events, sizeof(*e), 0);
	if (!e) {
		__sync_fetch_and_add(&c->drops, 1);
		return tcp_reno_undo_cwnd(sk);
	}
	fill_common(e, sk, seq, CCR_CB_UNDO_CWND, bpf_ktime_get_ns());
	snap_shared_pre(e, sk);
	snap_private(e, ca, 0);

	ret = tcp_reno_undo_cwnd(sk);

	e->result_valid = 1;
	e->result = ret;
	snap_post(e, sk);
	snap_private(e, ca, 1);
	finish_clock(e, c);
	bpf_ringbuf_submit(e, 0);
	__sync_fetch_and_add(&c->emitted, 1);
	return ret;
}

SEC("struct_ops")
void BPF_PROG(ccr_covegas_pkts_acked, struct sock *sk, const struct ack_sample *sample)
{
	struct tcp_sock *tp = tcp_sk(sk);
	struct covegas *ca = (struct covegas *)inet_csk_ca(sk);
	struct ccr_counters *c = get_counters();
	__u64 seq;
	struct ccr_event_v2 *e;
	__u32 rtt;

	if (sample->rtt_us < 0)
		return;

	if (!c) {
		goto do_acked;
	}
	seq = alloc_seq(c);
	e = bpf_ringbuf_reserve(&ccr_events, sizeof(*e), 0);
	if (!e) {
		__sync_fetch_and_add(&c->drops, 1);
		goto do_acked;
	}
	fill_common(e, sk, seq, CCR_CB_PKTS_ACKED, bpf_ktime_get_ns());
	e->in_sample_rtt_us = BPF_CORE_READ(sample, rtt_us);
	e->in_sample_pkts_acked = BPF_CORE_READ(sample, pkts_acked);
	e->in_sample_in_flight = BPF_CORE_READ(sample, in_flight);
	snap_shared_pre(e, sk);
	snap_private(e, ca, 0);

	rtt = (__u32)sample->rtt_us;
	if (rtt == 0)
		rtt = 1;
	if (ca->min_rtt_us == 0 || rtt < ca->min_rtt_us)
		ca->min_rtt_us = rtt;
	if (rtt < ca->recent_min_us)
		ca->recent_min_us = rtt;
	if (ca->minrtt_probing && rtt < ca->minrtt_probe_min_us)
		ca->minrtt_probe_min_us = rtt;
	update_dlv_rate(tp, ca);

	snap_post(e, sk);
	snap_private(e, ca, 1);
	finish_clock(e, c);
	bpf_ringbuf_submit(e, 0);
	__sync_fetch_and_add(&c->emitted, 1);
	return;

do_acked:
	rtt = (__u32)sample->rtt_us;
	if (rtt == 0)
		rtt = 1;
	if (ca->min_rtt_us == 0 || rtt < ca->min_rtt_us)
		ca->min_rtt_us = rtt;
	if (rtt < ca->recent_min_us)
		ca->recent_min_us = rtt;
	if (ca->minrtt_probing && rtt < ca->minrtt_probe_min_us)
		ca->minrtt_probe_min_us = rtt;
	update_dlv_rate(tp, ca);
}

SEC(".struct_ops")
struct tcp_congestion_ops ccr_covegas = {
	.init		= (void *)ccr_covegas_init,
	.ssthresh	= (void *)ccr_covegas_ssthresh,
	.cong_avoid	= (void *)ccr_covegas_cong_avoid,
	.undo_cwnd	= (void *)ccr_covegas_undo_cwnd,
	.pkts_acked	= (void *)ccr_covegas_pkts_acked,
	.name		= "ccr_covegas",
};
