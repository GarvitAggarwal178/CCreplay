"""CCReplay trace parser/validator for Replay ABI v2 (CoVegas). Pure Python.
Binary layout mirrors bpf/ccr_event_v2.h exactly (struct ccr_event_v2).
Independent of user/ccr_trace.py (v0) and user/ccr_trace_v1.py (v1) except
for the genuinely version-independent helpers reused from ccr_trace.py.
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

CCR_TRACE_VERSION_2 = 2

CCR_CB_SSTHRESH = 1
CCR_CB_CONG_AVOID = 2
CCR_CB_UNDO_CWND = 3
CCR_CB_INIT = 4
CCR_CB_PKTS_ACKED = 7
CALLBACK_NAMES = {
    1: "ssthresh", 2: "cong_avoid", 3: "undo_cwnd", 4: "init", 7: "pkts_acked",
}

CCR_MANIFEST_SSTHRESH = 1 << 0
CCR_MANIFEST_CONG_AVOID = 1 << 1
CCR_MANIFEST_UNDO_CWND = 1 << 2
CCR_MANIFEST_INIT_V2 = 1 << 3
CCR_MANIFEST_PKTS_ACKED_V2 = 1 << 6
CCR_COVEGAS_MANIFEST = (
    CCR_MANIFEST_SSTHRESH | CCR_MANIFEST_CONG_AVOID | CCR_MANIFEST_UNDO_CWND |
    CCR_MANIFEST_INIT_V2 | CCR_MANIFEST_PKTS_ACKED_V2
)
CCR_PRIVATE_SCHEMA_COVEGAS_V2 = 2

MODE_DELAY = 0
MODE_COMPETE = 1

# struct ccr_event_v2 (bpf/ccr_event_v2.h). Offsets confirmed byte-for-byte
# via offsetof() (data/audit_src/print_offsets_v2.c), not derived by eye.
# sizeof == 624.
EVENT_FMT = (
    "<QQQI"        # seq, sock_cookie, ts_ns, callback_id
    "I"             # _pad0
    "II"            # clock_jiffies32_before/after
    "QQ"            # clock_ktime_ns_before/after
    "II"            # in_ack, in_acked
    "qii"           # in_sample_rtt_us (signed), in_sample_pkts_acked, in_sample_in_flight
    "IIIIII"        # pre_snd_cwnd .. pre_max_packets_out
    "B3x"           # pre_is_cwnd_limited + pad
    "III"           # pre_snd_nxt, pre_mss_cache, pre_rate_delivered
    "I"             # pre_rate_interval_us
    "B3x"           # pre_rate_app_limited + pad
    "I"             # pre_srtt_us
    "IIIIIIIIIIIII" # priv_pre_min_rtt_us .. priv_pre_compete_enter_jiffies (13 x u32)
    "QQ"            # priv_pre_last_minrtt_probe_ns, probe_action_start_ns
    "BB6x"          # priv_pre_mode, priv_pre_minrtt_probing + pad
    "IIIIII"        # priv_pre_delay_* (6)
    "IIIIIII"       # priv_pre_cubic_* (7)
    "104s"          # priv_pre_raw
    "II"            # result_valid, result
    "III"           # post_snd_cwnd, post_snd_cwnd_cnt, post_snd_ssthresh
    "IIIIIIIIIIIII" # priv_post_min_rtt_us .. priv_post_compete_enter_jiffies (13 x u32)
    "4x"            # implicit compiler padding before the u64 pair below
    "QQ"            # priv_post_last_minrtt_probe_ns, probe_action_start_ns
    "BB6x"          # priv_post_mode, priv_post_minrtt_probing + pad
    "IIIIII"        # priv_post_delay_* (6)
    "IIIIIII"       # priv_post_cubic_* (7)
    "104s"          # priv_post_raw
    "4x"            # trailing struct alignment padding
)
EVENT_SIZE = struct.calcsize(EVENT_FMT)
assert EVENT_SIZE == 624, EVENT_SIZE

EVENT_FIELDS = [
    "seq", "sock_cookie", "ts_ns", "callback_id", "_pad0",
    "clock_jiffies32_before", "clock_jiffies32_after",
    "clock_ktime_ns_before", "clock_ktime_ns_after",
    "in_ack", "in_acked",
    "in_sample_rtt_us", "in_sample_pkts_acked", "in_sample_in_flight",
    "pre_snd_cwnd", "pre_snd_ssthresh", "pre_snd_cwnd_cnt", "pre_snd_cwnd_clamp",
    "pre_prior_cwnd", "pre_max_packets_out",
    "pre_is_cwnd_limited",
    "pre_snd_nxt", "pre_mss_cache", "pre_rate_delivered",
    "pre_rate_interval_us",
    "pre_rate_app_limited",
    "pre_srtt_us",
    "priv_pre_min_rtt_us", "priv_pre_recent_min_us", "priv_pre_detect_count",
    "priv_pre_last_max_cwnd", "priv_pre_epoch_start", "priv_pre_cwnd_before_minrtt_probe",
    "priv_pre_minrtt_probe_min_us", "priv_pre_last_queue_est_pkts", "priv_pre_dlv_rate_bps",
    "priv_pre_dlv_rate_compete", "priv_pre_dlv_rate_max",
    "priv_pre_last_compete_exit_jiffies", "priv_pre_compete_enter_jiffies",
    "priv_pre_last_minrtt_probe_ns", "priv_pre_probe_action_start_ns",
    "priv_pre_mode", "priv_pre_minrtt_probing",
    "priv_pre_delay_window_start_ack", "priv_pre_delay_cwnd_at_window_start",
    "priv_pre_delay_rtts_in_window", "priv_pre_delay_saved_bic_origin_point",
    "priv_pre_delay_saved_bic_K", "priv_pre_delay_detect_hold_until",
    "priv_pre_cubic_cnt", "priv_pre_cubic_last_cwnd", "priv_pre_cubic_last_time",
    "priv_pre_cubic_bic_origin_point", "priv_pre_cubic_bic_K", "priv_pre_cubic_ack_cnt",
    "priv_pre_cubic_tcp_cwnd",
    "priv_pre_raw",
    "result_valid", "result",
    "post_snd_cwnd", "post_snd_cwnd_cnt", "post_snd_ssthresh",
    "priv_post_min_rtt_us", "priv_post_recent_min_us", "priv_post_detect_count",
    "priv_post_last_max_cwnd", "priv_post_epoch_start", "priv_post_cwnd_before_minrtt_probe",
    "priv_post_minrtt_probe_min_us", "priv_post_last_queue_est_pkts", "priv_post_dlv_rate_bps",
    "priv_post_dlv_rate_compete", "priv_post_dlv_rate_max",
    "priv_post_last_compete_exit_jiffies", "priv_post_compete_enter_jiffies",
    "priv_post_last_minrtt_probe_ns", "priv_post_probe_action_start_ns",
    "priv_post_mode", "priv_post_minrtt_probing",
    "priv_post_delay_window_start_ack", "priv_post_delay_cwnd_at_window_start",
    "priv_post_delay_rtts_in_window", "priv_post_delay_saved_bic_origin_point",
    "priv_post_delay_saved_bic_K", "priv_post_delay_detect_hold_until",
    "priv_post_cubic_cnt", "priv_post_cubic_last_cwnd", "priv_post_cubic_last_time",
    "priv_post_cubic_bic_origin_point", "priv_post_cubic_bic_K", "priv_post_cubic_ack_cnt",
    "priv_post_cubic_tcp_cwnd",
    "priv_post_raw",
]
assert len(EVENT_FIELDS) == len(struct.unpack(EVENT_FMT, b"\x00" * EVENT_SIZE)), (
    len(EVENT_FIELDS), len(struct.unpack(EVENT_FMT, b"\x00" * EVENT_SIZE)))

DEDICATED_PRIVATE_FIELDS = (
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


def jiffies_clock_classification(event):
    return "CLOCK_STABLE" if event["clock_jiffies32_before"] == event["clock_jiffies32_after"] else "CLOCK_AMBIGUOUS"


def ktime_clock_classification(event):
    return "CLOCK_STABLE" if event["clock_ktime_ns_before"] == event["clock_ktime_ns_after"] else "CLOCK_AMBIGUOUS"


def parse_trace_v2(path):
    size = os.path.getsize(path)
    if size < HEADER_SIZE:
        raise TraceValidationError(f"file too small for header: {size} < {HEADER_SIZE}")

    with open(path, "rb") as f:
        raw_hdr = f.read(HEADER_SIZE)
        hdr = TraceHeader(raw_hdr)

        if hdr.magic != CCR_TRACE_MAGIC:
            raise TraceValidationError(f"bad magic: {hdr.magic!r}")
        if hdr.trace_version != CCR_TRACE_VERSION_2:
            raise TraceValidationError(
                f"unknown trace_version {hdr.trace_version} (this parser supports {CCR_TRACE_VERSION_2} only)")
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


def validate_run_v2(trace_path, meta_path):
    hdr, events = parse_trace_v2(trace_path)

    with open(meta_path) as f:
        meta = json.load(f)

    global_seq = validate_global_sequence(events)
    _, per_cookie = validate_sequence(events)

    checks = {}
    checks["magic_ok"] = True
    checks["trace_version_known"] = True
    checks["callback_manifest_matches"] = (hdr.callback_manifest == CCR_COVEGAS_MANIFEST)
    checks["private_state_schema_matches"] = (hdr.private_state_schema_id == CCR_PRIVATE_SCHEMA_COVEGAS_V2)
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

    jiffies_stable = sum(1 for e in events if jiffies_clock_classification(e) == "CLOCK_STABLE")
    jiffies_ambiguous = len(events) - jiffies_stable
    ktime_stable = sum(1 for e in events if ktime_clock_classification(e) == "CLOCK_STABLE")
    ktime_ambiguous = len(events) - ktime_stable
    checks["clock_counts_match_sidecar"] = (
        jiffies_stable == meta.get("clock_jiffies_stable") and
        jiffies_ambiguous == meta.get("clock_jiffies_ambiguous") and
        ktime_stable == meta.get("clock_ktime_stable") and
        ktime_ambiguous == meta.get("clock_ktime_ambiguous")
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
        "jiffies_stable": jiffies_stable, "jiffies_ambiguous": jiffies_ambiguous,
        "ktime_stable": ktime_stable, "ktime_ambiguous": ktime_ambiguous,
        "global_sequence": global_seq,
        "per_cookie": per_cookie,
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <trace.ccr> <meta.json>", file=sys.stderr)
        sys.exit(2)
    result = validate_run_v2(sys.argv[1], sys.argv[2])
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result["pass"] else 1)
