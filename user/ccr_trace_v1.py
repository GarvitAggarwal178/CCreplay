"""CCReplay trace parser/validator for Replay ABI v1 (CUBIC). Pure Python, no
kernel dependency. Binary layout mirrors bpf/ccr_event_v1.h exactly (struct
ccr_event_v1) -- struct format strings below MUST be kept in sync with that
header if it changes (trace_version bump required, per docs/REPLAY_ABI.md).

This module is entirely separate from user/ccr_trace.py (v0/Reno) per
ADR-021 -- v0's parser, format strings, and tests are not modified or
imported here except for the genuinely version-independent helpers
(validate_global_sequence, validate_sequence, select_dominant_connection),
which operate only on generic "seq"/"sock_cookie" dict keys and carry no
v0-specific assumption.
"""
import struct
import json
import os
import sys

from ccr_trace import (
    CCR_TRACE_MAGIC,
    HEADER_FMT, HEADER_SIZE, TraceHeader, TraceValidationError,
    validate_sequence, validate_global_sequence, select_dominant_connection,
)

CCR_TRACE_VERSION_1 = 1

CCR_CB_SSTHRESH = 1
CCR_CB_CONG_AVOID = 2
CCR_CB_UNDO_CWND = 3
CCR_CB_INIT = 4
CCR_CB_SET_STATE = 5
CCR_CB_CWND_EVENT = 6
CCR_CB_PKTS_ACKED = 7
CALLBACK_NAMES = {
    1: "ssthresh", 2: "cong_avoid", 3: "undo_cwnd",
    4: "init", 5: "set_state", 6: "cwnd_event", 7: "pkts_acked",
}

CCR_MANIFEST_SSTHRESH = 1 << 0
CCR_MANIFEST_CONG_AVOID = 1 << 1
CCR_MANIFEST_UNDO_CWND = 1 << 2
CCR_MANIFEST_INIT = 1 << 3
CCR_MANIFEST_SET_STATE = 1 << 4
CCR_MANIFEST_CWND_EVENT = 1 << 5
CCR_MANIFEST_PKTS_ACKED = 1 << 6
CCR_CUBIC_MANIFEST = (
    CCR_MANIFEST_SSTHRESH | CCR_MANIFEST_CONG_AVOID | CCR_MANIFEST_UNDO_CWND |
    CCR_MANIFEST_INIT | CCR_MANIFEST_SET_STATE | CCR_MANIFEST_CWND_EVENT |
    CCR_MANIFEST_PKTS_ACKED
)

CCR_PRIVATE_SCHEMA_CUBIC_V1 = 1

# struct ccr_event_v1 (see bpf/ccr_event_v1.h). Offsets confirmed byte-for-
# byte against the real compiled struct via offsetof()
# (data/audit_src/print_offsets_v1.c), not derived by eye:
#   seq=0 sock_cookie=8 ts_ns=16 callback_id=24 _pad0=28
#   clock_jiffies32_before=32 clock_jiffies32_after=36 pre_tcp_mstamp=40
#   in_ack=48 in_acked=52 in_new_state=56 in_cwnd_event=60
#   in_sample_rtt_us=64 in_sample_pkts_acked=72 in_sample_in_flight=76
#   pre_snd_cwnd=80 pre_snd_ssthresh=84 pre_snd_cwnd_cnt=88 pre_snd_cwnd_clamp=92
#   pre_prior_cwnd=96 pre_max_packets_out=100 pre_is_cwnd_limited=104
#   pre_snd_nxt=108 pre_snd_una=112 pre_lsndtime=116
#   pre_sk_pacing_rate=120 pre_sk_pacing_status=128 pre_sk_gso_max_size=132
#   priv_pre_cnt=136 .. priv_pre_tcp_cwnd=172 (10 x u32)
#   priv_pre_sample_cnt=176 priv_pre_found=177
#   priv_pre_round_start=180 priv_pre_end_seq=184 priv_pre_last_ack=188 priv_pre_curr_rtt=192
#   priv_pre_raw=196 (104 bytes)
#   result_valid=300 result=304
#   post_snd_cwnd=308 post_snd_cwnd_cnt=312 post_snd_ssthresh=316
#   priv_post_cnt=320 .. priv_post_tcp_cwnd=356 (10 x u32)
#   priv_post_sample_cnt=360 priv_post_found=361
#   priv_post_round_start=364 .. priv_post_curr_rtt=376
#   priv_post_raw=380 (104 bytes), sizeof=488
EVENT_FMT = (
    "<QQQII"        # seq, sock_cookie, ts_ns, callback_id, _pad0
    "IIQ"           # clock_jiffies32_before, clock_jiffies32_after, pre_tcp_mstamp
    "IIII"          # in_ack, in_acked, in_new_state, in_cwnd_event
    "qii"           # in_sample_rtt_us (signed), in_sample_pkts_acked, in_sample_in_flight
    "IIIIII"        # pre_snd_cwnd .. pre_max_packets_out
    "B3x"           # pre_is_cwnd_limited + pad
    "III"           # pre_snd_nxt, pre_snd_una, pre_lsndtime
    "Q"             # pre_sk_pacing_rate
    "II"            # pre_sk_pacing_status, pre_sk_gso_max_size
    "IIIIIIIIII"    # priv_pre_cnt .. priv_pre_tcp_cwnd (10)
    "BB2x"          # priv_pre_sample_cnt, priv_pre_found + pad
    "IIII"          # priv_pre_round_start .. priv_pre_curr_rtt
    "104s"          # priv_pre_raw
    "II"            # result_valid, result
    "III"           # post_snd_cwnd, post_snd_cwnd_cnt, post_snd_ssthresh
    "IIIIIIIIII"    # priv_post_cnt .. priv_post_tcp_cwnd (10)
    "BB2x"          # priv_post_sample_cnt, priv_post_found + pad
    "IIII"          # priv_post_round_start .. priv_post_curr_rtt
    "104s"          # priv_post_raw
    "4x"            # trailing struct alignment padding
)
EVENT_SIZE = struct.calcsize(EVENT_FMT)
assert EVENT_SIZE == 488, EVENT_SIZE

EVENT_FIELDS = [
    "seq", "sock_cookie", "ts_ns", "callback_id", "_pad0",
    "clock_jiffies32_before", "clock_jiffies32_after", "pre_tcp_mstamp",
    "in_ack", "in_acked", "in_new_state", "in_cwnd_event",
    "in_sample_rtt_us", "in_sample_pkts_acked", "in_sample_in_flight",
    "pre_snd_cwnd", "pre_snd_ssthresh", "pre_snd_cwnd_cnt", "pre_snd_cwnd_clamp",
    "pre_prior_cwnd", "pre_max_packets_out",
    "pre_is_cwnd_limited",
    "pre_snd_nxt", "pre_snd_una", "pre_lsndtime",
    "pre_sk_pacing_rate",
    "pre_sk_pacing_status", "pre_sk_gso_max_size",
    "priv_pre_cnt", "priv_pre_last_max_cwnd", "priv_pre_last_cwnd", "priv_pre_last_time",
    "priv_pre_bic_origin_point", "priv_pre_bic_K", "priv_pre_delay_min", "priv_pre_epoch_start",
    "priv_pre_ack_cnt", "priv_pre_tcp_cwnd",
    "priv_pre_sample_cnt", "priv_pre_found",
    "priv_pre_round_start", "priv_pre_end_seq", "priv_pre_last_ack", "priv_pre_curr_rtt",
    "priv_pre_raw",
    "result_valid", "result",
    "post_snd_cwnd", "post_snd_cwnd_cnt", "post_snd_ssthresh",
    "priv_post_cnt", "priv_post_last_max_cwnd", "priv_post_last_cwnd", "priv_post_last_time",
    "priv_post_bic_origin_point", "priv_post_bic_K", "priv_post_delay_min", "priv_post_epoch_start",
    "priv_post_ack_cnt", "priv_post_tcp_cwnd",
    "priv_post_sample_cnt", "priv_post_found",
    "priv_post_round_start", "priv_post_end_seq", "priv_post_last_ack", "priv_post_curr_rtt",
    "priv_post_raw",
]
assert len(EVENT_FIELDS) == len(struct.unpack(EVENT_FMT, b"\x00" * EVENT_SIZE)), (
    len(EVENT_FIELDS), len(struct.unpack(EVENT_FMT, b"\x00" * EVENT_SIZE)))

# The 16 semantic CUBIC private-state fields (ADR-019); `unused` (the real
# struct's dead field at offset 40) has no corresponding entry here or
# anywhere in EVENT_FIELDS -- it was never recorded in the first place, not
# merely excluded at comparison time.
PRIVATE_FIELD_SUFFIXES = [
    "cnt", "last_max_cwnd", "last_cwnd", "last_time", "bic_origin_point", "bic_K",
    "delay_min", "epoch_start", "ack_cnt", "tcp_cwnd", "sample_cnt", "found",
    "round_start", "end_seq", "last_ack", "curr_rtt",
]


def clock_classification(event):
    """CLOCK_STABLE if tcp_jiffies32 did not change during the kfunc call,
    CLOCK_AMBIGUOUS otherwise (ADR-018). Computed at parse time from the two
    recorded snapshots, never trusted as a stored field.
    """
    return "CLOCK_STABLE" if event["clock_jiffies32_before"] == event["clock_jiffies32_after"] else "CLOCK_AMBIGUOUS"


def parse_trace_v1(path):
    """Returns (TraceHeader, list[dict]). Raises TraceValidationError on any
    structural problem. Mirrors user/ccr_trace.py's parse_trace exactly,
    substituting the v1 record format; the header format is unchanged
    (ADR-021) and reuses TraceHeader/HEADER_FMT/HEADER_SIZE directly.
    """
    size = os.path.getsize(path)
    if size < HEADER_SIZE:
        raise TraceValidationError(f"file too small for header: {size} < {HEADER_SIZE}")

    with open(path, "rb") as f:
        raw_hdr = f.read(HEADER_SIZE)
        hdr = TraceHeader(raw_hdr)

        if hdr.magic != CCR_TRACE_MAGIC:
            raise TraceValidationError(f"bad magic: {hdr.magic!r}")
        if hdr.trace_version != CCR_TRACE_VERSION_1:
            raise TraceValidationError(
                f"unknown trace_version {hdr.trace_version} (this parser supports {CCR_TRACE_VERSION_1} only)")
        if hdr.record_size != EVENT_SIZE:
            raise TraceValidationError(
                f"record_size mismatch: header says {hdr.record_size}, parser expects {EVENT_SIZE}")

        body = size - HEADER_SIZE
        if body % EVENT_SIZE != 0:
            raise TraceValidationError(
                f"trailing partial record: body={body} not a multiple of record_size={EVENT_SIZE}")

        n = body // EVENT_SIZE
        events = []
        for i in range(n):
            raw = f.read(EVENT_SIZE)
            if len(raw) != EVENT_SIZE:
                raise TraceValidationError(f"short read at record {i}")
            vals = struct.unpack(EVENT_FMT, raw)
            events.append(dict(zip(EVENT_FIELDS, vals)))

    return hdr, events


def validate_run_v1(trace_path, meta_path):
    """Full R3 (N2.3) integrity check for one recorded CUBIC run. Mirrors
    user/ccr_trace.py's validate_run, adapted for the 7-callback manifest and
    clock-ambiguity accounting; does not modify or call into v0's
    validate_run.
    """
    hdr, events = parse_trace_v1(trace_path)

    with open(meta_path) as f:
        meta = json.load(f)

    global_seq = validate_global_sequence(events)
    _, per_cookie = validate_sequence(events)

    checks = {}
    checks["magic_ok"] = True
    checks["trace_version_known"] = True
    checks["callback_manifest_matches"] = (hdr.callback_manifest == CCR_CUBIC_MANIFEST)
    checks["private_state_schema_matches"] = (hdr.private_state_schema_id == CCR_PRIVATE_SCHEMA_CUBIC_V1)
    checks["counters_read_ok"] = meta.get("counters_read_ok") is True
    checks["invocations_eq_emitted_plus_drops"] = (
        meta["invocations"] == meta["emitted"] + meta["drops"])
    checks["zero_drops"] = meta["drops"] == 0
    checks["emitted_eq_events_in_file"] = meta["emitted"] == len(events)
    checks["events_written_userspace_eq_events_in_file"] = (
        meta["events_written_userspace"] == len(events))
    checks["global_sequence_gapless"] = len(global_seq["gaps"]) == 0
    checks["global_sequence_spans_invocations"] = (
        len(events) > 0 and
        global_seq["min_seq"] == 0 and
        global_seq["max_seq"] == meta["invocations"] - 1
    ) if meta["invocations"] > 0 else True

    callback_counts = {}
    for e in events:
        callback_counts[e["callback_id"]] = callback_counts.get(e["callback_id"], 0) + 1
    checks["result_present_where_required"] = all(
        e["result_valid"] == 1
        for e in events
        if e["callback_id"] in (CCR_CB_SSTHRESH, CCR_CB_UNDO_CWND)
    )

    clock_stable = sum(1 for e in events if clock_classification(e) == "CLOCK_STABLE")
    clock_ambiguous = len(events) - clock_stable
    checks["clock_ambiguous_count_matches_sidecar"] = (
        clock_stable == meta.get("clock_stable") and
        clock_ambiguous == meta.get("clock_ambiguous")
    )

    dominant_cookie, dominant_events, other_events = select_dominant_connection(events)
    checks["single_dominant_connection"] = (
        len(events) == 0 or len(dominant_events) / len(events) >= 0.99
    )

    overall_pass = all(checks.values())

    return {
        "pass": overall_pass,
        "checks": checks,
        "dominant_connection": {
            "sock_cookie": str(dominant_cookie) if dominant_cookie is not None else None,
            "n_events": len(dominant_events),
            "n_other_events": len(other_events),
            "other_events_sample": other_events[:5],
        },
        "header": {
            "trace_version": hdr.trace_version,
            "recorder_version": hdr.recorder_version,
            "kernel_release": hdr.kernel_release,
            "reference_impl_id": hdr.reference_impl_id,
            "callback_manifest": hdr.callback_manifest,
            "private_state_schema_id": hdr.private_state_schema_id,
        },
        "meta": meta,
        "n_events": len(events),
        "callback_counts": {CALLBACK_NAMES.get(k, k): v for k, v in callback_counts.items()},
        "clock_stable": clock_stable,
        "clock_ambiguous": clock_ambiguous,
        "global_sequence": global_seq,
        "per_cookie": per_cookie,
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <trace.ccr> <meta.json>", file=sys.stderr)
        sys.exit(2)
    result = validate_run_v1(sys.argv[1], sys.argv[2])
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result["pass"] else 1)
