"""Userspace CoVegas replay model.

Ported line-for-line from the SAME algorithm logic copied into
bpf/covegas_wrapper.bpf.c (ADR-022), which is itself copied near-verbatim
from the read-only reference (~/cn-spike/covegas/src/covegas.bpf.c, repo
HEAD bab7ab7, file itself last touched at b5bc0be "v4" -- see
docs/PROVENANCE.md). Per ADR-022, there is no independent kernel reference
for CoVegas -- the live reference IS this same algorithm, run as the actual
active congestion controller. This model exists to prove CCReplay can
faithfully reproduce that implementation's transitions (self-replay), per
D4's disclosed oracle-strength statement.

Private state is a dict with 17 dedicated fields plus BOTH union arms
(delay_*, cubic_*) always present as separate keys -- this is a safe
simplification of the real struct's memory-aliasing union (verified from
source: every DELAY<->COMPETE transition explicitly reinitializes every
field of the newly-live arm -- cubic_reset() or the keep_epoch branch always
sets all 7 cubic fields; revert_to_delay() always sets all 6 delay fields --
so no transition ever relies on stale/leftover bytes from the other arm,
making independent tracking behaviorally equivalent to the real aliased
memory for every reachable code path).

Per ADR-023, the comparison schema is mode-dependent: PRE-arm fields are
compared only if PRE mode selects that arm; POST-arm fields only if POST
mode selects that arm, independently.
"""

MASK32 = 0xFFFFFFFF


def u32(x):
    return x & MASK32


def s32(x):
    x &= MASK32
    return x - 0x100000000 if x >= 0x80000000 else x


def u64(x):
    return x & 0xFFFFFFFFFFFFFFFF


MODE_DELAY = 0
MODE_COMPETE = 1

T_US = 10000
K_WINDOWS = 4
W_RTTS = 4
MINRTT_PERIOD_MS = 10000
MINRTT_SKIP_MS = 30000
ALPHA = 2
BETA = 4
DETECTOR_ENABLED = 1
RATE_SETTLE_MS = 1000
RATE_JUMP_NUM = 3
RATE_JUMP_DEN = 2
EPOCH_KEEP_MS = 5000
HOLD_MS = 500

BICTCP_BETA_SCALE = 1024
BICTCP_HZ = 10
CONFIG_HZ = 250  # ground-truthed, data/cubic_replay_capability_audit.md; same kernel

FAST_CONVERGENCE = 1
BETA_CUBIC = 717
BIC_SCALE = 41
TCP_FRIENDLINESS = 1

CUBE_RTT_SCALE = BIC_SCALE * 10
BETA_SCALE = (8 * (BICTCP_BETA_SCALE + BETA_CUBIC) // 3) // (BICTCP_BETA_SCALE - BETA_CUBIC)
CUBE_FACTOR = (1 << (10 + 3 * BICTCP_HZ)) // (BIC_SCALE * 10)
USEC_PER_SEC = 1000000
USEC_PER_JIFFY = USEC_PER_SEC // CONFIG_HZ

_CBRT_TABLE = [
    0, 54, 54, 54, 118, 118, 118, 118,
    123, 129, 134, 138, 143, 147, 151, 156,
    157, 161, 164, 168, 170, 173, 176, 179,
    181, 185, 187, 190, 192, 194, 197, 199,
    200, 202, 204, 206, 209, 211, 213, 215,
    217, 219, 221, 222, 224, 225, 227, 229,
    231, 232, 234, 236, 237, 239, 240, 242,
    244, 245, 246, 248, 250, 251, 252, 254,
]

DEDICATED_FIELDS = (
    "min_rtt_us", "recent_min_us", "detect_count", "last_max_cwnd", "epoch_start",
    "cwnd_before_minrtt_probe", "minrtt_probe_min_us", "last_queue_est_pkts",
    "dlv_rate_bps", "dlv_rate_compete", "dlv_rate_max",
    "last_compete_exit_jiffies", "compete_enter_jiffies",
    "last_minrtt_probe_ns", "probe_action_start_ns", "mode", "minrtt_probing",
)
DELAY_ARM_FIELDS = (
    "delay_window_start_ack", "delay_cwnd_at_window_start", "delay_rtts_in_window",
    "delay_saved_bic_origin_point", "delay_saved_bic_K", "delay_detect_hold_until",
)
CUBIC_ARM_FIELDS = (
    "cubic_cnt", "cubic_last_cwnd", "cubic_last_time", "cubic_bic_origin_point",
    "cubic_bic_K", "cubic_ack_cnt", "cubic_tcp_cwnd",
)
ALL_PRIVATE_FIELDS = DEDICATED_FIELDS + DELAY_ARM_FIELDS + CUBIC_ARM_FIELDS

INITIAL_PRIVATE_STATE = {f: 0 for f in ALL_PRIVATE_FIELDS}
INITIAL_PRIVATE_STATE["recent_min_us"] = MASK32
INITIAL_PRIVATE_STATE["minrtt_probe_min_us"] = MASK32
NONE_PRIVATE_STATE = None


def fls64(x):
    return x.bit_length()


def cubic_root(a):
    if a < 64:
        return u32((_CBRT_TABLE[a] + 35) >> 6)
    b = fls64(a)
    b = ((b * 84) >> 8) - 1
    shift = a >> (b * 3)
    if shift >= 64:
        return 0
    x = u32((u32(_CBRT_TABLE[shift] + 10) << b)) >> 6
    x = u32(2 * x + (a // (u64(x) * u64(x - 1))))
    x = u32(x * 341) >> 10
    return x


def compute_queue_est(tp_snd_cwnd, srtt_us, min_rtt_us):
    srtt = srtt_us >> 3
    if not min_rtt_us or srtt <= min_rtt_us:
        return 0
    return (tp_snd_cwnd * (srtt - min_rtt_us)) // srtt


def cubic_reset(ca):
    ca = dict(ca)
    for f in CUBIC_ARM_FIELDS:
        ca[f] = 0
    ca["last_max_cwnd"] = 0
    ca["epoch_start"] = 0
    return ca


def bictcp_update(ca, cwnd, acked, jiffies_now):
    ca = dict(ca)
    ca["cubic_ack_cnt"] = u32(ca["cubic_ack_cnt"] + acked)

    if ca["cubic_last_cwnd"] == cwnd and s32(u32(jiffies_now) - ca["cubic_last_time"]) <= CONFIG_HZ // 32:
        return ca

    if ca["epoch_start"] and u32(jiffies_now) == ca["cubic_last_time"]:
        return _tcp_friendliness(ca, cwnd)

    ca["cubic_last_cwnd"] = cwnd
    ca["cubic_last_time"] = u32(jiffies_now)

    if ca["epoch_start"] == 0:
        ca["epoch_start"] = u32(jiffies_now)
        ca["cubic_ack_cnt"] = acked
        ca["cubic_tcp_cwnd"] = cwnd
        if ca["last_max_cwnd"] <= cwnd:
            ca["cubic_bic_K"] = 0
            ca["cubic_bic_origin_point"] = cwnd
        else:
            ca["cubic_bic_K"] = cubic_root(u64(CUBE_FACTOR * (ca["last_max_cwnd"] - cwnd)))
            ca["cubic_bic_origin_point"] = ca["last_max_cwnd"]

    # min_rtt_us plays the role bpf_cubic.c's ca->delay_min plays --
    # covegas passes its own continuously-validated min_rtt_us floor here
    # ("uses covegas's own continuously-validated min_rtt_us floor in place
    # of a separate cubic delay_min sample tracker", read-only source's own
    # comment). Time math is the bpf_cubic.c PORT style (multiply by
    # USEC_PER_JIFFY first), not the real kernel tcp_cubic.c style --
    # confirmed verbatim from covegas_wrapper.bpf.c's own copied source
    # (adapted from bpf_cubic.c per its top-of-file comment, not from
    # data/kernel_source_ref/tcp_cubic.c).
    t = s32(u32(jiffies_now) - ca["epoch_start"]) * USEC_PER_JIFFY
    t += ca["min_rtt_us"]
    t = u64(t) << BICTCP_HZ
    t = t // USEC_PER_SEC

    if t < ca["cubic_bic_K"]:
        offs = ca["cubic_bic_K"] - t
    else:
        offs = t - ca["cubic_bic_K"]

    delta = u32((CUBE_RTT_SCALE * offs * offs * offs) >> (10 + 3 * BICTCP_HZ))
    if t < ca["cubic_bic_K"]:
        bic_target = u32(ca["cubic_bic_origin_point"] - delta)
    else:
        bic_target = u32(ca["cubic_bic_origin_point"] + delta)

    if bic_target > cwnd:
        ca["cubic_cnt"] = cwnd // (bic_target - cwnd)
    else:
        ca["cubic_cnt"] = 100 * cwnd

    if ca["last_max_cwnd"] == 0 and ca["cubic_cnt"] > 20:
        ca["cubic_cnt"] = 20

    return _tcp_friendliness(ca, cwnd)


def _tcp_friendliness(ca, cwnd):
    ca = dict(ca)
    if TCP_FRIENDLINESS:
        scale = BETA_SCALE
        delta = u32((cwnd * scale) >> 3)
        if delta and ca["cubic_ack_cnt"] > delta:
            n = (ca["cubic_ack_cnt"] - 1) // delta  # ceil(a/b)-1 == (a-1)//b identity, cubic_model.py precedent
            ca["cubic_ack_cnt"] = u32(ca["cubic_ack_cnt"] - n * delta)
            ca["cubic_tcp_cwnd"] = u32(ca["cubic_tcp_cwnd"] + n)
        if ca["cubic_tcp_cwnd"] > cwnd:
            delta = u32(ca["cubic_tcp_cwnd"] - cwnd)
            max_cnt = cwnd // delta
            if ca["cubic_cnt"] > max_cnt:
                ca["cubic_cnt"] = max_cnt
    ca["cubic_cnt"] = max(ca["cubic_cnt"], 2)
    return ca


def tcp_in_slow_start(cwnd, ssthresh):
    return cwnd < ssthresh


def tcp_is_cwnd_limited(cwnd, ssthresh, max_packets_out, is_cwnd_limited_bit):
    if tcp_in_slow_start(cwnd, ssthresh):
        return cwnd < 2 * max_packets_out
    return bool(is_cwnd_limited_bit)


def tcp_slow_start(cwnd, ssthresh, clamp, acked):
    new_cwnd = min(cwnd + acked, ssthresh)
    acked -= (new_cwnd - cwnd)
    new_cwnd = min(new_cwnd, clamp)
    return new_cwnd, acked


def tcp_cong_avoid_ai(cwnd, cwnd_cnt, clamp, w, acked):
    if cwnd_cnt >= w:
        cwnd_cnt = 0
        cwnd += 1
    cwnd_cnt += acked
    if cwnd_cnt >= w:
        delta = cwnd_cnt // w
        cwnd_cnt -= delta * w
        cwnd += delta
    cwnd = min(cwnd, clamp)
    return cwnd, cwnd_cnt


def cubic_growth(ca, pre, acked, jiffies_now):
    """Returns (post_snd_cwnd, post_snd_cwnd_cnt, ca)."""
    cwnd = pre["snd_cwnd"]
    cwnd_cnt = pre["snd_cwnd_cnt"]
    clamp = pre["snd_cwnd_clamp"]
    ssthresh = pre["snd_ssthresh"]

    if tcp_in_slow_start(cwnd, ssthresh):
        cwnd, _ = tcp_slow_start(cwnd, ssthresh, clamp, acked)
        return cwnd, cwnd_cnt, ca

    ca = bictcp_update(ca, cwnd, acked, jiffies_now)
    cwnd, cwnd_cnt = tcp_cong_avoid_ai(cwnd, cwnd_cnt, clamp, ca["cubic_cnt"], acked)
    return cwnd, cwnd_cnt, ca


def update_dlv_rate(ca, pre):
    ca = dict(ca)
    interval_us = pre["rate_interval_us"]
    delivered = pre["rate_delivered"]
    mss = pre["mss_cache"]
    app_limited = pre["rate_app_limited"]

    if app_limited or interval_us == 0 or not mss:
        return ca

    rate_Bps = (delivered * mss * USEC_PER_SEC) // interval_us
    if rate_Bps > MASK32:
        rate_Bps = MASK32

    if ca["dlv_rate_bps"] == 0:
        ca["dlv_rate_bps"] = u32(rate_Bps)
    else:
        ca["dlv_rate_bps"] = u32(ca["dlv_rate_bps"] - (ca["dlv_rate_bps"] >> 3) + (u32(rate_Bps) >> 3))

    if ca["dlv_rate_bps"] > ca["dlv_rate_max"]:
        ca["dlv_rate_max"] = ca["dlv_rate_bps"]

    return ca


def handle_minrtt_probe(ca, pre, ktime_now, jiffies_now):
    """Returns (probe_ran: bool, ca, post_snd_cwnd_override_or_None)."""
    ca = dict(ca)
    if ca["minrtt_probing"]:
        dur_ns = 200 * 1000000
        one_rtt_ns = (pre["srtt_us"] >> 3) * 1000
        if one_rtt_ns > dur_ns:
            dur_ns = one_rtt_ns

        if u64(ktime_now) - ca["probe_action_start_ns"] >= dur_ns:
            if ca["minrtt_probe_min_us"] != MASK32:
                new_floor = ca["minrtt_probe_min_us"]
                if ca["recent_min_us"] != MASK32 and ca["recent_min_us"] < new_floor:
                    new_floor = ca["recent_min_us"]
                ca["min_rtt_us"] = new_floor
            cwnd_override = ca["cwnd_before_minrtt_probe"]

            if ca["mode"] == MODE_COMPETE and ca["epoch_start"]:
                delta_jiffies = u32(((u64(ktime_now) - ca["probe_action_start_ns"]) * CONFIG_HZ) // 1000000000)
                ca["epoch_start"] = u32(ca["epoch_start"] + delta_jiffies)

            ca["minrtt_probing"] = 0
            ca["last_minrtt_probe_ns"] = u64(ktime_now)
            return True, ca, cwnd_override
        return True, ca, None

    period_ns = (MINRTT_SKIP_MS * 1000000) if (ca["mode"] == MODE_COMPETE and ca["dlv_rate_compete"] != 0) \
        else (MINRTT_PERIOD_MS * 1000000)

    if u64(ktime_now) - ca["last_minrtt_probe_ns"] >= period_ns:
        ca["cwnd_before_minrtt_probe"] = pre["snd_cwnd"]
        ca["minrtt_probe_min_us"] = MASK32
        ca["minrtt_probing"] = 1
        ca["probe_action_start_ns"] = u64(ktime_now)
        ca["dlv_rate_max"] = ca["dlv_rate_max"] - (ca["dlv_rate_max"] >> 4)
        return True, ca, 4  # cwnd forced to 4

    return False, ca, None


def revert_to_delay(ca, pre, jiffies_now):
    """Returns (post_snd_cwnd, ca)."""
    ca = dict(ca)
    save_origin = ca["cubic_bic_origin_point"]
    save_K = ca["cubic_bic_K"]
    mss = pre["mss_cache"]
    bdp_bytes = (ca["dlv_rate_bps"] * ca["min_rtt_us"]) // 1000000
    bdp_pkts = (bdp_bytes // mss) if mss else 0
    target = bdp_pkts + BETA

    snd_cwnd = pre["snd_cwnd"]
    if snd_cwnd > target:
        snd_cwnd = max(target, 4)

    ca["mode"] = MODE_DELAY
    ca["detect_count"] = 0
    ca["last_compete_exit_jiffies"] = u32(jiffies_now)
    ca["delay_window_start_ack"] = pre["snd_nxt"]
    ca["delay_cwnd_at_window_start"] = snd_cwnd
    ca["delay_rtts_in_window"] = 0
    ca["delay_saved_bic_origin_point"] = save_origin
    ca["delay_saved_bic_K"] = save_K
    ca["delay_detect_hold_until"] = u32(u32(jiffies_now) + (HOLD_MS * CONFIG_HZ) // 1000)
    ca["recent_min_us"] = MASK32
    return snd_cwnd, ca


def handle_compete_mode(ca, pre, acked, jiffies_now):
    """Returns (post_snd_cwnd, post_snd_cwnd_cnt, ca)."""
    ca = dict(ca)
    cwnd = pre["snd_cwnd"]
    cwnd_cnt = pre["snd_cwnd_cnt"]

    if ca["dlv_rate_compete"] == 0:
        elapsed_jiffies = u32(u32(jiffies_now) - ca["compete_enter_jiffies"])
        if elapsed_jiffies >= (RATE_SETTLE_MS * CONFIG_HZ) // 1000 and ca["dlv_rate_bps"]:
            if ca["dlv_rate_bps"] < (ca["dlv_rate_max"] * 3) // 4:
                ca["dlv_rate_compete"] = ca["dlv_rate_bps"]
            else:
                cwnd, ca = revert_to_delay(ca, pre, jiffies_now)
                return cwnd, cwnd_cnt, ca
    elif ca["dlv_rate_bps"] > (RATE_JUMP_NUM * ca["dlv_rate_compete"]) // RATE_JUMP_DEN:
        cwnd, ca = revert_to_delay(ca, pre, jiffies_now)
        return cwnd, cwnd_cnt, ca

    cwnd2, cwnd_cnt2, ca = cubic_growth(ca, pre, acked, jiffies_now)
    return cwnd2, cwnd_cnt2, ca


def handle_delay_mode(ca, pre, ack, acked, jiffies_now):
    """Returns (post_snd_cwnd, post_snd_cwnd_cnt, post_snd_ssthresh, ca)."""
    ca = dict(ca)
    cwnd = pre["snd_cwnd"]
    cwnd_cnt = pre["snd_cwnd_cnt"]
    ssthresh = pre["snd_ssthresh"]

    queue_est = compute_queue_est(cwnd, pre["srtt_us"], ca["min_rtt_us"])
    ca["last_queue_est_pkts"] = queue_est

    if tcp_in_slow_start(cwnd, ssthresh):
        if queue_est < ALPHA:
            cwnd, _ = tcp_slow_start(cwnd, ssthresh, pre["snd_cwnd_clamp"], acked)
        else:
            ssthresh = cwnd

    if not (s32(ca["delay_window_start_ack"] - ack) < 0):  # after(ack, window_start_ack)
        return cwnd, cwnd_cnt, ssthresh, ca

    ca["delay_rtts_in_window"] += 1
    ca["delay_window_start_ack"] = pre["snd_nxt"]

    if ca["delay_rtts_in_window"] < W_RTTS:
        return cwnd, cwnd_cnt, ssthresh, ca

    if not tcp_in_slow_start(cwnd, ssthresh):
        fresh_queue_est = compute_queue_est(cwnd, pre["srtt_us"], ca["min_rtt_us"])
        if fresh_queue_est < ALPHA:
            cwnd += 1
        elif fresh_queue_est > BETA:
            cwnd -= 1
        if cwnd < 4:
            cwnd = 4

    if (DETECTOR_ENABLED and ca["min_rtt_us"] and ca["recent_min_us"] != MASK32 and
            not (s32(u32(jiffies_now) - ca["delay_detect_hold_until"]) < 0)):  # !before(jiffies_now, detect_hold_until)
        elevated = ca["recent_min_us"] > ca["min_rtt_us"] and (ca["recent_min_us"] - ca["min_rtt_us"]) > T_US
        yielding = cwnd <= ca["delay_cwnd_at_window_start"]

        if elevated and yielding:
            ca["detect_count"] += 1
            if ca["detect_count"] >= K_WINDOWS:
                gap_jiffies = u32(u32(jiffies_now) - ca["last_compete_exit_jiffies"])
                keep_epoch = ca["epoch_start"] != 0 and gap_jiffies < (EPOCH_KEEP_MS * CONFIG_HZ) // 1000
                saved_origin = ca["delay_saved_bic_origin_point"]
                saved_K = ca["delay_saved_bic_K"]

                ca["mode"] = MODE_COMPETE
                ca["dlv_rate_compete"] = 0
                ca["compete_enter_jiffies"] = u32(jiffies_now)

                if keep_epoch:
                    ca["epoch_start"] = u32(ca["epoch_start"] + gap_jiffies)
                    ca["cubic_cnt"] = 0
                    ca["cubic_last_cwnd"] = 0
                    ca["cubic_last_time"] = 0
                    ca["cubic_ack_cnt"] = 0
                    ca["cubic_tcp_cwnd"] = 0
                    ca["cubic_bic_origin_point"] = saved_origin
                    ca["cubic_bic_K"] = saved_K
                else:
                    ca = cubic_reset(ca)
                return cwnd, cwnd_cnt, ssthresh, ca
        else:
            ca["detect_count"] = 0
    else:
        ca["detect_count"] = 0

    ca["delay_rtts_in_window"] = 0
    ca["recent_min_us"] = MASK32
    ca["delay_cwnd_at_window_start"] = cwnd
    return cwnd, cwnd_cnt, ssthresh, ca


# --------------------------------------------------------------------------
# Replay-engine integration
# --------------------------------------------------------------------------

CCR_CB_SSTHRESH = 1
CCR_CB_CONG_AVOID = 2
CCR_CB_UNDO_CWND = 3
CCR_CB_INIT = 4
CCR_CB_PKTS_ACKED = 7

CALLBACK_NAMES = {1: "ssthresh", 2: "cong_avoid", 3: "undo_cwnd", 4: "init", 7: "pkts_acked"}


def pre_from_event(e):
    return {
        "snd_cwnd": e["pre_snd_cwnd"],
        "snd_ssthresh": e["pre_snd_ssthresh"],
        "snd_cwnd_cnt": e["pre_snd_cwnd_cnt"],
        "snd_cwnd_clamp": e["pre_snd_cwnd_clamp"],
        "prior_cwnd": e["pre_prior_cwnd"],
        "max_packets_out": e["pre_max_packets_out"],
        "is_cwnd_limited": e["pre_is_cwnd_limited"],
        "snd_nxt": e["pre_snd_nxt"],
        "mss_cache": e["pre_mss_cache"],
        "rate_delivered": e["pre_rate_delivered"],
        "rate_interval_us": e["pre_rate_interval_us"],
        "rate_app_limited": e["pre_rate_app_limited"],
        "srtt_us": e["pre_srtt_us"],
    }


def private_pre_from_event(e):
    return {f: e[f"priv_pre_{f}"] for f in ALL_PRIVATE_FIELDS}


def cubic_undo_cwnd(pre):
    return max(pre["snd_cwnd"], pre["prior_cwnd"])


def transition(event, ca):
    """Single dispatch point (same shape as reno_model.py/cubic_model.py's
    transition()). Returns (computed_dict, next_ca)."""
    pre = pre_from_event(event)
    cb = event["callback_id"]
    jiffies_now = event["clock_jiffies32_before"]
    ktime_now = event["clock_ktime_ns_before"]

    def _priv_post(ca_):
        return {f"priv_post_{f}": ca_[f] for f in ALL_PRIVATE_FIELDS}

    if cb == CCR_CB_INIT:
        next_ca = dict(INITIAL_PRIVATE_STATE)
        next_ca["delay_window_start_ack"] = pre["snd_nxt"]
        next_ca["delay_cwnd_at_window_start"] = pre["snd_cwnd"]
        # covegas_init sets ca->last_minrtt_probe_ns = now (the SAME
        # bpf_ktime_get_ns() read the recorder shares with
        # clock_ktime_ns_before, per the fill_common fix -- see
        # bpf/covegas_wrapper.bpf.c's comment on that function).
        next_ca["last_minrtt_probe_ns"] = u64(ktime_now)
        out = {
            "result_valid": 0, "result": 0,
            "post_snd_cwnd": pre["snd_cwnd"], "post_snd_cwnd_cnt": pre["snd_cwnd_cnt"],
            "post_snd_ssthresh": pre["snd_ssthresh"],
        }
        out.update(_priv_post(next_ca))
        return out, next_ca

    if cb == CCR_CB_CONG_AVOID:
        if not tcp_is_cwnd_limited(pre["snd_cwnd"], pre["snd_ssthresh"], pre["max_packets_out"], pre["is_cwnd_limited"]):
            out = {
                "result_valid": 0, "result": 0,
                "post_snd_cwnd": pre["snd_cwnd"], "post_snd_cwnd_cnt": pre["snd_cwnd_cnt"],
                "post_snd_ssthresh": pre["snd_ssthresh"],
            }
            out.update(_priv_post(ca))
            return out, ca

        probe_ran, next_ca, cwnd_override = handle_minrtt_probe(ca, pre, ktime_now, jiffies_now)
        post_ssthresh = pre["snd_ssthresh"]
        if probe_ran:
            post_cwnd = pre["snd_cwnd"] if cwnd_override is None else cwnd_override
            post_cwnd_cnt = pre["snd_cwnd_cnt"]
        elif next_ca["mode"] == MODE_COMPETE:
            post_cwnd, post_cwnd_cnt, next_ca = handle_compete_mode(next_ca, pre, event["in_acked"], jiffies_now)
        else:
            post_cwnd, post_cwnd_cnt, post_ssthresh, next_ca = handle_delay_mode(
                next_ca, pre, event["in_ack"], event["in_acked"], jiffies_now)

        out = {
            "result_valid": 0, "result": 0,
            "post_snd_cwnd": post_cwnd, "post_snd_cwnd_cnt": post_cwnd_cnt,
            "post_snd_ssthresh": post_ssthresh,
        }
        out.update(_priv_post(next_ca))
        return out, next_ca

    if cb == CCR_CB_SSTHRESH:
        ca2 = dict(ca)
        ca2["epoch_start"] = 0
        cwnd = pre["snd_cwnd"]
        if cwnd < ca2["last_max_cwnd"] and FAST_CONVERGENCE:
            ca2["last_max_cwnd"] = u32((cwnd * (BICTCP_BETA_SCALE + BETA_CUBIC)) // (2 * BICTCP_BETA_SCALE))
        else:
            ca2["last_max_cwnd"] = cwnd
        result = max((cwnd * BETA_CUBIC) // BICTCP_BETA_SCALE, 2)
        out = {
            "result_valid": 1, "result": result,
            "post_snd_cwnd": pre["snd_cwnd"], "post_snd_cwnd_cnt": pre["snd_cwnd_cnt"],
            "post_snd_ssthresh": pre["snd_ssthresh"],
        }
        out.update(_priv_post(ca2))
        return out, ca2

    if cb == CCR_CB_UNDO_CWND:
        result = cubic_undo_cwnd(pre)
        out = {
            "result_valid": 1, "result": result,
            "post_snd_cwnd": pre["snd_cwnd"], "post_snd_cwnd_cnt": pre["snd_cwnd_cnt"],
            "post_snd_ssthresh": pre["snd_ssthresh"],
        }
        out.update(_priv_post(ca))
        return out, ca

    if cb == CCR_CB_PKTS_ACKED:
        rtt_us = event["in_sample_rtt_us"]
        if rtt_us < 0:
            out = {
                "result_valid": 0, "result": 0,
                "post_snd_cwnd": pre["snd_cwnd"], "post_snd_cwnd_cnt": pre["snd_cwnd_cnt"],
                "post_snd_ssthresh": pre["snd_ssthresh"],
            }
            out.update(_priv_post(ca))
            return out, ca

        ca2 = dict(ca)
        rtt = u32(rtt_us)
        if rtt == 0:
            rtt = 1
        if ca2["min_rtt_us"] == 0 or rtt < ca2["min_rtt_us"]:
            ca2["min_rtt_us"] = rtt
        if rtt < ca2["recent_min_us"]:
            ca2["recent_min_us"] = rtt
        if ca2["minrtt_probing"] and rtt < ca2["minrtt_probe_min_us"]:
            ca2["minrtt_probe_min_us"] = rtt
        ca2 = update_dlv_rate(ca2, pre)

        out = {
            "result_valid": 0, "result": 0,
            "post_snd_cwnd": pre["snd_cwnd"], "post_snd_cwnd_cnt": pre["snd_cwnd_cnt"],
            "post_snd_ssthresh": pre["snd_ssthresh"],
        }
        out.update(_priv_post(ca2))
        return out, ca2

    raise ValueError(f"unknown callback_id {cb}")


def comparison_fields(callback_id, pre_mode, post_mode):
    """ADR-023: mode-dependent comparison schema. PRE-arm fields gated by
    pre_mode, POST-arm fields gated by post_mode, independently."""
    common = ["post_snd_cwnd", "post_snd_cwnd_cnt", "post_snd_ssthresh"] + \
        [f"priv_post_{f}" for f in DEDICATED_FIELDS]
    if post_mode == MODE_DELAY:
        common += [f"priv_post_{f}" for f in DELAY_ARM_FIELDS]
    else:
        common += [f"priv_post_{f}" for f in CUBIC_ARM_FIELDS]

    if callback_id in (CCR_CB_SSTHRESH, CCR_CB_UNDO_CWND):
        common = ["result"] + common
    return common


CALLBACK_NAMES_ALIAS = CALLBACK_NAMES  # for symmetry with cubic_model.py's naming
