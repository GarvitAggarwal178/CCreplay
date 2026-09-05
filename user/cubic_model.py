"""Userspace CUBIC replay model.

Ported line-for-line from data/kernel_source_ref/tcp_cubic.c (the real
kernel source for this exact machine's running kernel,
linux-msft-wsl-6.18.33.2 -- see docs/PROVENANCE.md's "External
(non-read-only-repo) source reference" and ADR-017), NOT from
~/cn-spike/bpf_src/bpf_cubic.c. Every function below cites the real source's
line numbers. Module-parameter constants (beta, bic_scale, fast_convergence,
hystart, hystart_detect, hystart_low_window, hystart_ack_delta_us,
initial_ssthresh, tcp_friendliness) were read live from
/sys/module/tcp_cubic/parameters/* on this running kernel and confirmed to
equal the source's compiled-in defaults exactly -- not assumed from the
source file alone. CONFIG_HZ=250 was ground-truthed from /proc/config.gz
(data/cubic_replay_capability_audit.md).

All arithmetic that the C source performs on a `u32`-typed variable is
explicitly masked to 32 bits here (`u32()`); `s32()` reproduces C's signed
32-bit wraparound for the jiffies-delta comparisons. Getting this wrong is
exactly the kind of thing data/cubic_replay_kernel_source_correction.md's
"integer-semantics" concern is about -- masking is applied at every point
the real source assigns to a u32/s32-typed variable, not only where it
looked like it might matter.

Private state is a dict of the 16 semantic struct bictcp fields (ADR-019):
cnt, last_max_cwnd, last_cwnd, last_time, bic_origin_point, bic_K,
delay_min, epoch_start, ack_cnt, tcp_cwnd, sample_cnt, found, round_start,
end_seq, last_ack, curr_rtt. Functions that mutate private state return a
NEW dict (never mutate their argument in place), so Mode A/B replay callers
can compare before/after without aliasing surprises.
"""

MASK32 = 0xFFFFFFFF


def u32(x):
    return x & MASK32


def s32(x):
    x &= MASK32
    return x - 0x100000000 if x >= 0x80000000 else x


def u64(x):
    return x & 0xFFFFFFFFFFFFFFFF


# Live-verified module parameters (see module docstring) -- tcp_cubic.c
# lines 49-58.
FAST_CONVERGENCE = 1
BETA = 717
INITIAL_SSTHRESH = 0
BIC_SCALE = 41
TCP_FRIENDLINESS = 1
HYSTART = 1
HYSTART_ACK_TRAIN = 0x1
HYSTART_DELAY = 0x2
HYSTART_DETECT = HYSTART_ACK_TRAIN | HYSTART_DELAY  # = 3, live-verified
HYSTART_LOW_WINDOW = 16
HYSTART_ACK_DELTA_US = 2000
HYSTART_MIN_SAMPLES = 8
HYSTART_DELAY_MIN = 4000
HYSTART_DELAY_MAX = 16000

BICTCP_BETA_SCALE = 1024
BICTCP_HZ = 10
CONFIG_HZ = 250  # ground-truthed, data/cubic_replay_capability_audit.md
USEC_PER_MSEC = 1000
USEC_PER_SEC = 1000000
TCP_CA_Loss = 4
CA_EVENT_TX_START = 0

# cubictcp_register(), tcp_cubic.c lines 504-541 -- precomputed once, exact
# C integer truncation order preserved (left-to-right / with explicit
# do_div == integer division here).
BETA_SCALE = (8 * (BICTCP_BETA_SCALE + BETA) // 3) // (BICTCP_BETA_SCALE - BETA)
CUBE_RTT_SCALE = BIC_SCALE * 10
CUBE_FACTOR = (1 << (10 + 3 * BICTCP_HZ)) // (BIC_SCALE * 10)

# tcp_cubic.c lines 178-187 -- cbrt(x<<18)-1 table for x in [0..63].
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

NONE_PRIVATE_STATE = None  # only used for events before the first `init`


def fls64(x):
    """tcp_cubic.c's fls64 is a from-scratch bit-search loop; Python's
    int.bit_length() is exactly equivalent (1-based index of the highest
    set bit, 0 for x==0) and is used directly rather than re-implementing
    the manual shift loop."""
    return x.bit_length()


def cubic_root(a):
    """tcp_cubic.c lines 167-209, exact integer semantics (u32 masking at
    every point the source assigns to a u32-typed variable)."""
    b = fls64(a)
    if b < 7:
        return u32((_CBRT_TABLE[a] + 35) >> 6)

    b = ((b * 84) >> 8) - 1
    shift = a >> (b * 3)

    x = u32((u32(_CBRT_TABLE[shift] + 10) << b)) >> 6
    # Newton-Raphson: x = (2*x + a/(x*(x-1))) ; div64_u64 is genuine 64-bit
    # integer division, both operands cast to u64 explicitly in the source.
    x = u32(2 * x + (a // (u64(x) * u64(x - 1))))
    x = u32(x * 341) >> 10
    return x


def bictcp_reset(ca):
    """tcp_cubic.c lines 107-111: memset(ca, 0, offsetof(struct bictcp,
    unused)) zeroes exactly the first 10 u32 fields (cnt..tcp_cwnd);
    `found` is set separately; sample_cnt/round_start/end_seq/last_ack/
    curr_rtt are NOT touched by this function -- a real, easy-to-miss
    behavior confirmed from the real source, not from bpf_cubic.c's
    field-by-field reimplementation (which resets the same 10+found set,
    same effective behavior, but this model is grounded in the real
    memset's actual byte range, not the port's mirrored field list)."""
    ca = dict(ca)
    for f in ("cnt", "last_max_cwnd", "last_cwnd", "last_time",
              "bic_origin_point", "bic_K", "delay_min", "epoch_start",
              "ack_cnt", "tcp_cwnd"):
        ca[f] = 0
    ca["found"] = 0
    return ca


def bictcp_hystart_reset(ca, tcp_mstamp, snd_nxt):
    """tcp_cubic.c lines 118-127. bictcp_clock_us returns tp->tcp_mstamp
    truncated to u32 (the function's declared return type), not the full
    u64 timestamp -- reproduced here via u32()."""
    ca = dict(ca)
    now = u32(tcp_mstamp)
    ca["round_start"] = now
    ca["last_ack"] = now
    ca["end_seq"] = u32(snd_nxt)
    ca["curr_rtt"] = MASK32  # ~0U
    ca["sample_cnt"] = 0
    return ca


def cubictcp_init(ca, tcp_mstamp, snd_nxt, pre_snd_ssthresh):
    """tcp_cubic.c lines 129-140. Returns (ca, post_snd_ssthresh)."""
    ca = bictcp_reset(ca)
    if HYSTART:
        ca = bictcp_hystart_reset(ca, tcp_mstamp, snd_nxt)
    post_snd_ssthresh = pre_snd_ssthresh
    if not HYSTART and INITIAL_SSTHRESH:
        post_snd_ssthresh = INITIAL_SSTHRESH  # dead on this system (HYSTART=1)
    return ca, post_snd_ssthresh


def cubictcp_cwnd_event(ca, event, jiffies_now, lsndtime):
    """tcp_cubic.c lines 142-161."""
    ca = dict(ca)
    if event == CA_EVENT_TX_START:
        now = u32(jiffies_now)
        delta = s32(now - lsndtime)
        if ca["epoch_start"] and delta > 0:
            new_epoch = u32(ca["epoch_start"] + delta)
            # after(a,b) == before(b,a) == (s32)(b-a) < 0
            if s32(now - new_epoch) < 0:
                new_epoch = now
            ca["epoch_start"] = new_epoch
    return ca


def bictcp_update(ca, cwnd, acked, jiffies_now):
    """tcp_cubic.c lines 214-322 (bictcp_update), the core cubic-curve
    computation. `jiffies_now` is the recorded clock_jiffies32_before for
    this event (CLOCK_STABLE is expected to dominate overwhelmingly per
    the clock-window hazard investigation; ambiguous events use the
    before-snapshot by documented convention, see
    data/cubic_replay_capability_audit.md)."""
    ca = dict(ca)
    ca["ack_cnt"] = u32(ca["ack_cnt"] + acked)

    if ca["last_cwnd"] == cwnd and s32(u32(jiffies_now) - ca["last_time"]) <= CONFIG_HZ // 32:
        return ca

    if ca["epoch_start"] and u32(jiffies_now) == ca["last_time"]:
        return _tcp_friendliness(ca, cwnd)

    ca["last_cwnd"] = cwnd
    ca["last_time"] = u32(jiffies_now)

    if ca["epoch_start"] == 0:
        ca["epoch_start"] = u32(jiffies_now)
        ca["ack_cnt"] = acked
        ca["tcp_cwnd"] = cwnd

        if ca["last_max_cwnd"] <= cwnd:
            ca["bic_K"] = 0
            ca["bic_origin_point"] = cwnd
        else:
            ca["bic_K"] = cubic_root(u64(CUBE_FACTOR * (ca["last_max_cwnd"] - cwnd)))
            ca["bic_origin_point"] = ca["last_max_cwnd"]

    t = s32(u32(jiffies_now) - ca["epoch_start"])
    t += _usecs_to_jiffies(ca["delay_min"])
    t = u64(t) << BICTCP_HZ
    t = t // CONFIG_HZ  # do_div(t, HZ)

    if t < ca["bic_K"]:
        offs = ca["bic_K"] - t
    else:
        offs = t - ca["bic_K"]

    delta = u32((CUBE_RTT_SCALE * offs * offs * offs) >> (10 + 3 * BICTCP_HZ))
    if t < ca["bic_K"]:
        bic_target = u32(ca["bic_origin_point"] - delta)
    else:
        bic_target = u32(ca["bic_origin_point"] + delta)

    if bic_target > cwnd:
        ca["cnt"] = cwnd // (bic_target - cwnd)
    else:
        ca["cnt"] = 100 * cwnd

    if ca["last_max_cwnd"] == 0 and ca["cnt"] > 20:
        ca["cnt"] = 20

    return _tcp_friendliness(ca, cwnd)


def _usecs_to_jiffies(usecs):
    """Linux's usecs_to_jiffies: usecs * HZ / 1_000_000, integer, with the
    kernel's own rounding (jiffies_to_usecs/usecs_to_jiffies use a
    scaled-multiply table for arbitrary HZ in reality, but for the
    HZ=250 case actually compiled on this kernel the exact widely-used
    generic formula is `(usecs * HZ + 999999) / 1000000` is NOT what the
    kernel uses for the common-HZ fast path; the generic path used when HZ
    does not evenly divide USEC_PER_SEC is `DIV_ROUND_UP(usecs, USEC_PER_SEC / HZ)`
    for usecs_to_jiffies. USEC_PER_SEC/HZ = 1000000/250 = 4000 exactly (HZ=250
    evenly divides 10^6), so this reduces to the exact, unambiguous
    ceiling-division `(usecs + 3999) // 4000`, with no dependency on which
    of the kernel's several HZ-dependent code paths is compiled in."""
    usec_per_jiffy = USEC_PER_SEC // CONFIG_HZ  # exact: 4000
    return (usecs + usec_per_jiffy - 1) // usec_per_jiffy


def _tcp_friendliness(ca, cwnd):
    """tcp_cubic.c lines 299-321 (the `tcp_friendliness:` label onward).

    Disclosed model deviation (category: none of A/B/C -- a Python-
    practicality substitution, not a correctness fix, flagged per the
    anti-fitting rule's "leave unresolved and report it" spirit rather than
    silently included): the real source's loop is
    `while (ca->ack_cnt > delta) { ca->ack_cnt -= delta; ca->tcp_cwnd++; }`,
    unconditionally -- if delta were ever 0 this would be a genuine
    infinite loop in the compiled kernel too, which cannot have actually
    happened in any trace this model is validated against (a recording
    that hung would never have completed). Reproduced here as the
    mathematically identical closed form for delta>0 (n = ack_cnt // delta,
    matching data/kernel_source_ref/tcp_cubic.c's own predecessor's
    documented equivalence, independently re-derived here rather than
    trusted from bpf_cubic.c's port); delta==0 is left as a no-op rather
    than hung, since it should never be reached on a real completed trace,
    and if it ever is, the resulting comparison mismatch will surface it
    rather than mask it.
    """
    ca = dict(ca)
    if TCP_FRIENDLINESS:
        scale = BETA_SCALE
        delta = u32((cwnd * scale) >> 3)
        if delta:
            n = ca["ack_cnt"] // delta
            if n:
                ca["ack_cnt"] = u32(ca["ack_cnt"] - n * delta)
                ca["tcp_cwnd"] = u32(ca["tcp_cwnd"] + n)

        if ca["tcp_cwnd"] > cwnd:
            delta = u32(ca["tcp_cwnd"] - cwnd)
            max_cnt = cwnd // delta
            if ca["cnt"] > max_cnt:
                ca["cnt"] = max_cnt

    ca["cnt"] = max(ca["cnt"], 2)
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


def cubictcp_cong_avoid(ca, pre, ack, acked, jiffies_now):
    """tcp_cubic.c lines 324-339. Returns (post_snd_cwnd, post_snd_cwnd_cnt, ca).
    Per data/cubic_replay_kernel_source_correction.md: the real kernel's
    cong_avoid does NOT read its `ack` argument at all (unlike the
    bpf_cubic.c port, which used it for a HyStart round-reset check that
    real cong_avoid does not perform) -- `ack` is accepted here only to
    match the callback's real signature/manifest, never used."""
    del ack  # confirmed unread by the real kernel source, kept for signature parity
    cwnd = pre["snd_cwnd"]
    ssthresh = pre["snd_ssthresh"]
    cwnd_cnt = pre["snd_cwnd_cnt"]
    clamp = pre["snd_cwnd_clamp"]
    max_packets_out = pre["max_packets_out"]
    is_lim = pre["is_cwnd_limited"]

    if not tcp_is_cwnd_limited(cwnd, ssthresh, max_packets_out, is_lim):
        return cwnd, cwnd_cnt, ca

    if tcp_in_slow_start(cwnd, ssthresh):
        cwnd, acked = tcp_slow_start(cwnd, ssthresh, clamp, acked)
        if acked == 0:
            return cwnd, cwnd_cnt, ca

    ca = bictcp_update(ca, cwnd, acked, jiffies_now)
    cwnd, cwnd_cnt = tcp_cong_avoid_ai(cwnd, cwnd_cnt, clamp, ca["cnt"], acked)
    return cwnd, cwnd_cnt, ca


def cubictcp_recalc_ssthresh(ca, pre):
    """tcp_cubic.c lines 341-356. Returns (result, ca)."""
    ca = dict(ca)
    cwnd = pre["snd_cwnd"]
    ca["epoch_start"] = 0
    if cwnd < ca["last_max_cwnd"] and FAST_CONVERGENCE:
        ca["last_max_cwnd"] = u32((cwnd * (BICTCP_BETA_SCALE + BETA)) // (2 * BICTCP_BETA_SCALE))
    else:
        ca["last_max_cwnd"] = cwnd
    result = max((cwnd * BETA) // BICTCP_BETA_SCALE, 2)
    return result, ca


def cubictcp_state(ca, new_state, tcp_mstamp, snd_nxt):
    """tcp_cubic.c lines 358-364."""
    if new_state == TCP_CA_Loss:
        ca = bictcp_reset(ca)
        ca = bictcp_hystart_reset(ca, tcp_mstamp, snd_nxt)
    return ca


def hystart_ack_delay(sk_pacing_rate, sk_gso_max_size):
    """tcp_cubic.c lines 375-384."""
    rate = sk_pacing_rate
    if not rate:
        return 0
    return min(USEC_PER_MSEC, (sk_gso_max_size * 4 * USEC_PER_SEC) // rate)


def hystart_update(ca, delay, tp):
    """tcp_cubic.c lines 386-450. `tp` carries the shared-state fields
    hystart_update reads: snd_una, snd_cwnd, tcp_mstamp, sk_pacing_rate,
    sk_pacing_status, sk_gso_max_size. Returns (ca, post_snd_ssthresh)."""
    ca = dict(ca)
    post_snd_ssthresh = None  # None == "not written this call"

    # Real kernel: `if (after(tp->snd_una, ca->end_seq)) bictcp_hystart_reset(sk);`
    # -- keyed on snd_una, NOT cong_avoid's `ack` argument (the port's
    # structure). after(a,b) == (s32)(b-a) < 0.
    if s32(ca["end_seq"] - tp["snd_una"]) < 0:
        ca = bictcp_hystart_reset(ca, tp["tcp_mstamp"], tp["snd_nxt"])

    if tp["snd_cwnd"] < HYSTART_LOW_WINDOW:
        return ca, post_snd_ssthresh

    if HYSTART_DETECT & HYSTART_ACK_TRAIN:
        now = u32(tp["tcp_mstamp"])
        if s32(now - ca["last_ack"]) <= HYSTART_ACK_DELTA_US:
            ca["last_ack"] = now
            threshold = ca["delay_min"] + hystart_ack_delay(tp["sk_pacing_rate"], tp["sk_gso_max_size"])
            if tp["sk_pacing_status"] == 0:  # SK_PACING_NONE
                threshold >>= 1
            if s32(now - ca["round_start"]) > threshold:
                ca["found"] = 1
                post_snd_ssthresh = tp["snd_cwnd"]

    if HYSTART_DETECT & HYSTART_DELAY:
        if ca["curr_rtt"] > delay:
            ca["curr_rtt"] = delay
        if ca["sample_cnt"] < HYSTART_MIN_SAMPLES:
            ca["sample_cnt"] += 1
        else:
            thresh = ca["delay_min"] + min(max(ca["delay_min"] >> 3, HYSTART_DELAY_MIN), HYSTART_DELAY_MAX)
            if ca["curr_rtt"] > thresh:
                ca["found"] = 1
                post_snd_ssthresh = tp["snd_cwnd"]

    return ca, post_snd_ssthresh


def cubictcp_acked(ca, sample_rtt_us, pre, jiffies_now):
    """tcp_cubic.c lines 452-476. `pre` carries snd_una/snd_cwnd/tcp_mstamp/
    snd_nxt/sk_pacing_rate/sk_pacing_status/sk_gso_max_size. Returns
    (ca, post_snd_ssthresh) where post_snd_ssthresh is None if this call
    never wrote tp->snd_ssthresh (the common case -- ADR-020's field is
    then equal to pre_snd_ssthresh, checked by the caller)."""
    ca = dict(ca)
    if sample_rtt_us < 0:
        return ca, None

    if ca["epoch_start"] and s32(u32(jiffies_now) - ca["epoch_start"]) < CONFIG_HZ:
        return ca, None

    delay = sample_rtt_us
    if delay == 0:
        delay = 1

    if ca["delay_min"] == 0 or ca["delay_min"] > delay:
        ca["delay_min"] = delay

    post_snd_ssthresh = None
    if not ca["found"] and tcp_in_slow_start(pre["snd_cwnd"], pre["snd_ssthresh"]) and HYSTART:
        ca, post_snd_ssthresh = hystart_update(ca, delay, pre)

    return ca, post_snd_ssthresh


def cubictcp_undo_cwnd(pre):
    """undo_cwnd is tcp_reno_undo_cwnd directly (tcp_cubic.c line 483) --
    zero CUBIC-specific logic, identical formula to user/reno_model.py's
    model_undo_cwnd."""
    return max(pre["snd_cwnd"], pre["prior_cwnd"])


# --------------------------------------------------------------------------
# Replay-engine integration: event <-> model dict extraction, single
# dispatch point, and the declared exact comparison schema. Mirrors
# user/reno_model.py's pre_from_event/transition/COMPARISON_FIELDS shape.
# --------------------------------------------------------------------------

CCR_CB_SSTHRESH = 1
CCR_CB_CONG_AVOID = 2
CCR_CB_UNDO_CWND = 3
CCR_CB_INIT = 4
CCR_CB_SET_STATE = 5
CCR_CB_CWND_EVENT = 6
CCR_CB_PKTS_ACKED = 7

PRIVATE_FIELDS = (
    "cnt", "last_max_cwnd", "last_cwnd", "last_time", "bic_origin_point", "bic_K",
    "delay_min", "epoch_start", "ack_cnt", "tcp_cwnd", "sample_cnt", "found",
    "round_start", "end_seq", "last_ack", "curr_rtt",
)


def pre_from_event(e):
    """Shared-state PRE dict, keyed to match cubic_model function
    parameter names (docs/REPLAY_ABI.md v1 SharedTcpPreState)."""
    return {
        "snd_cwnd": e["pre_snd_cwnd"],
        "snd_ssthresh": e["pre_snd_ssthresh"],
        "snd_cwnd_cnt": e["pre_snd_cwnd_cnt"],
        "snd_cwnd_clamp": e["pre_snd_cwnd_clamp"],
        "prior_cwnd": e["pre_prior_cwnd"],
        "max_packets_out": e["pre_max_packets_out"],
        "is_cwnd_limited": e["pre_is_cwnd_limited"],
        "snd_nxt": e["pre_snd_nxt"],
        "snd_una": e["pre_snd_una"],
        "lsndtime": e["pre_lsndtime"],
        "tcp_mstamp": e["pre_tcp_mstamp"],
        "sk_pacing_rate": e["pre_sk_pacing_rate"],
        "sk_pacing_status": e["pre_sk_pacing_status"],
        "sk_gso_max_size": e["pre_sk_gso_max_size"],
    }


def private_pre_from_event(e):
    """The event's own RECORDED private PRE state (ADR-019 16 fields) --
    used only by Mode A (R3A), which evaluates every event independently
    from recorded private PRE, never from a carried-over replay value
    (CLAUDE.md Mode A definition)."""
    return {f: e[f"priv_pre_{f}"] for f in PRIVATE_FIELDS}


def transition(event, ca):
    """Single dispatch point used by both R3A (event-local: `ca` is this
    event's OWN recorded private PRE state, via private_pre_from_event) and
    R3B (stateful: `ca` is whatever the model itself carried forward from
    the previous event -- never re-seeded from the recording). Returns
    (computed_dict, next_ca); computed_dict's keys exactly match
    ccr_trace_v1.EVENT_FIELDS's POST/result field names so callers can diff
    directly against the recorded event.

    post_snd_ssthresh is pre_snd_ssthresh for every callback except
    `pkts_acked` when its HyStart branch actually fires (the only path,
    across all seven callbacks, that mutates tp->snd_ssthresh outside the
    `ssthresh` callback's own return value -- ADR-020).
    """
    pre = pre_from_event(event)
    cb = event["callback_id"]

    def _priv_post(ca_):
        return {f"priv_post_{f}": ca_[f] for f in PRIVATE_FIELDS}

    if cb == CCR_CB_INIT:
        next_ca, post_ssthresh = cubictcp_init(ca, pre["tcp_mstamp"], pre["snd_nxt"], pre["snd_ssthresh"])
        out = {
            "result_valid": 0, "result": 0,
            "post_snd_cwnd": pre["snd_cwnd"], "post_snd_cwnd_cnt": pre["snd_cwnd_cnt"],
            "post_snd_ssthresh": post_ssthresh,
        }
        out.update(_priv_post(next_ca))
        return out, next_ca

    if cb == CCR_CB_CONG_AVOID:
        post_cwnd, post_cwnd_cnt, next_ca = cubictcp_cong_avoid(
            ca, pre, event["in_ack"], event["in_acked"], event["clock_jiffies32_before"])
        out = {
            "result_valid": 0, "result": 0,
            "post_snd_cwnd": post_cwnd, "post_snd_cwnd_cnt": post_cwnd_cnt,
            "post_snd_ssthresh": pre["snd_ssthresh"],
        }
        out.update(_priv_post(next_ca))
        return out, next_ca

    if cb == CCR_CB_SSTHRESH:
        result, next_ca = cubictcp_recalc_ssthresh(ca, pre)
        out = {
            "result_valid": 1, "result": result,
            "post_snd_cwnd": pre["snd_cwnd"], "post_snd_cwnd_cnt": pre["snd_cwnd_cnt"],
            "post_snd_ssthresh": pre["snd_ssthresh"],
        }
        out.update(_priv_post(next_ca))
        return out, next_ca

    if cb == CCR_CB_SET_STATE:
        next_ca = cubictcp_state(ca, event["in_new_state"], pre["tcp_mstamp"], pre["snd_nxt"])
        out = {
            "result_valid": 0, "result": 0,
            "post_snd_cwnd": pre["snd_cwnd"], "post_snd_cwnd_cnt": pre["snd_cwnd_cnt"],
            "post_snd_ssthresh": pre["snd_ssthresh"],
        }
        out.update(_priv_post(next_ca))
        return out, next_ca

    if cb == CCR_CB_CWND_EVENT:
        next_ca = cubictcp_cwnd_event(ca, event["in_cwnd_event"], event["clock_jiffies32_before"], pre["lsndtime"])
        out = {
            "result_valid": 0, "result": 0,
            "post_snd_cwnd": pre["snd_cwnd"], "post_snd_cwnd_cnt": pre["snd_cwnd_cnt"],
            "post_snd_ssthresh": pre["snd_ssthresh"],
        }
        out.update(_priv_post(next_ca))
        return out, next_ca

    if cb == CCR_CB_PKTS_ACKED:
        acked_pre = dict(pre)  # hystart_update also needs snd_nxt, already present
        next_ca, written_ssthresh = cubictcp_acked(
            ca, event["in_sample_rtt_us"], acked_pre, event["clock_jiffies32_before"])
        post_ssthresh = pre["snd_ssthresh"] if written_ssthresh is None else written_ssthresh
        out = {
            "result_valid": 0, "result": 0,
            "post_snd_cwnd": pre["snd_cwnd"], "post_snd_cwnd_cnt": pre["snd_cwnd_cnt"],
            "post_snd_ssthresh": post_ssthresh,
        }
        out.update(_priv_post(next_ca))
        return out, next_ca

    if cb == CCR_CB_UNDO_CWND:
        result = cubictcp_undo_cwnd(pre)
        # undo_cwnd is tcp_reno_undo_cwnd -- touches no CUBIC private state
        # at all (ca passes through unchanged); asserted, not assumed, by
        # including the full private comparison schema below.
        out = {
            "result_valid": 1, "result": result,
            "post_snd_cwnd": pre["snd_cwnd"], "post_snd_cwnd_cnt": pre["snd_cwnd_cnt"],
            "post_snd_ssthresh": pre["snd_ssthresh"],
        }
        out.update(_priv_post(ca))
        return out, ca

    raise ValueError(f"unknown callback_id {cb}")


# Declared exact comparison schema. Every callback compares the FULL
# 16-field private POST state, not only the fields that callback is
# expected to touch (Phase-1's COMPARISON_FIELDS under-scoping mistake --
# REPORT_PHASE1_RENO_REPLAY_VALIDATION.md deviation item 9 -- is not
# repeated here): this is how a "callback X touches no private state"
# purity claim (undo_cwnd) or "only these fields change" claim gets
# actually checked against every real recorded event, not merely asserted.
_ALL_PRIV_POST = [f"priv_post_{f}" for f in PRIVATE_FIELDS]
_COMMON_POST = ["post_snd_cwnd", "post_snd_cwnd_cnt", "post_snd_ssthresh"] + _ALL_PRIV_POST

COMPARISON_FIELDS = {
    CCR_CB_INIT: _COMMON_POST,
    CCR_CB_CONG_AVOID: _COMMON_POST,
    CCR_CB_SSTHRESH: ["result"] + _COMMON_POST,
    CCR_CB_SET_STATE: _COMMON_POST,
    CCR_CB_CWND_EVENT: _COMMON_POST,
    CCR_CB_PKTS_ACKED: _COMMON_POST,
    CCR_CB_UNDO_CWND: ["result"] + _COMMON_POST,
}
CALLBACK_NAMES = {
    CCR_CB_SSTHRESH: "ssthresh", CCR_CB_CONG_AVOID: "cong_avoid", CCR_CB_UNDO_CWND: "undo_cwnd",
    CCR_CB_INIT: "init", CCR_CB_SET_STATE: "set_state", CCR_CB_CWND_EVENT: "cwnd_event",
    CCR_CB_PKTS_ACKED: "pkts_acked",
}
