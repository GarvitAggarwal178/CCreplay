"""CCReplay trace parser/validator. Pure Python, no kernel dependency.
Binary layout mirrors bpf/ccr_event.h exactly (see struct ccr_trace_header,
struct ccr_event) -- struct format strings below MUST be kept in sync with
that header if it changes (trace_version bump required, per
docs/REPLAY_ABI.md).
"""
import struct
import json
import os
import sys

CCR_TRACE_MAGIC = b"CCRPLAY0"
CCR_TRACE_VERSION = 0

CCR_CB_SSTHRESH = 1
CCR_CB_CONG_AVOID = 2
CCR_CB_UNDO_CWND = 3
CALLBACK_NAMES = {1: "ssthresh", 2: "cong_avoid", 3: "undo_cwnd"}

CCR_MANIFEST_SSTHRESH = 1 << 0
CCR_MANIFEST_CONG_AVOID = 1 << 1
CCR_MANIFEST_UNDO_CWND = 1 << 2
CCR_RENO_MANIFEST = CCR_MANIFEST_SSTHRESH | CCR_MANIFEST_CONG_AVOID | CCR_MANIFEST_UNDO_CWND

# struct ccr_trace_header / struct ccr_event (see bpf/ccr_event.h). Python
# struct has no C-layout inference, so padding is placed by hand -- NOT
# derived by eye, but confirmed byte-for-byte against the real compiled
# struct via offsetof() on this exact toolchain (gcc 15.2.0):
#   header: magic=0 trace_version=8 recorder_version=12 kernel_release=16
#     reference_impl_id=81 callback_manifest=116 private_state_schema_id=120
#     record_size=128 creation_ts_ns=136, sizeof=144
#   event:  seq=0 sock_cookie=8 ts_ns=16 callback_id=24 _pad0=28 in_ack=32
#     in_acked=36 pre_snd_cwnd=40 pre_snd_ssthresh=44 pre_snd_cwnd_cnt=48
#     pre_snd_cwnd_clamp=52 pre_prior_cwnd=56 pre_max_packets_out=60
#     pre_is_cwnd_limited=64 result_valid=68 result=72 post_snd_cwnd=76
#     post_snd_cwnd_cnt=80, sizeof=88
# See data/audit_src/print_offsets.c for the exact program used to obtain
# these (also re-run as part of tests/test_trace_format.py).
HEADER_FMT = "<8sII65s32sxxxIIxxxxQQ"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
assert HEADER_SIZE == 144, HEADER_SIZE

EVENT_FMT = "<QQQIIIIIIIIIIB3xIIII4x"
EVENT_SIZE = struct.calcsize(EVENT_FMT)
assert EVENT_SIZE == 88, EVENT_SIZE

EVENT_FIELDS = [
    "seq", "sock_cookie", "ts_ns", "callback_id", "_pad0",
    "in_ack", "in_acked",
    "pre_snd_cwnd", "pre_snd_ssthresh", "pre_snd_cwnd_cnt", "pre_snd_cwnd_clamp",
    "pre_prior_cwnd", "pre_max_packets_out", "pre_is_cwnd_limited",
    "result_valid", "result",
    "post_snd_cwnd", "post_snd_cwnd_cnt",
]


class TraceHeader:
    __slots__ = ("magic", "trace_version", "recorder_version", "kernel_release",
                 "reference_impl_id", "callback_manifest", "private_state_schema_id",
                 "record_size", "creation_ts_ns")

    def __init__(self, raw):
        vals = struct.unpack(HEADER_FMT, raw)
        self.magic = vals[0]
        self.trace_version = vals[1]
        self.recorder_version = vals[2]
        self.kernel_release = vals[3].split(b"\x00", 1)[0].decode()
        self.reference_impl_id = vals[4].split(b"\x00", 1)[0].decode()
        self.callback_manifest = vals[5]
        self.private_state_schema_id = vals[6]
        self.record_size = vals[7]
        self.creation_ts_ns = vals[8]


class TraceValidationError(Exception):
    pass


def parse_trace(path):
    """Returns (TraceHeader, list[dict]). Raises TraceValidationError on any
    structural problem. Does not consult the sidecar metadata file -- that
    is validated separately by validate_run (below), since integrity is a
    two-source check (trace file self-consistency + independent sidecar).
    """
    size = os.path.getsize(path)
    if size < HEADER_SIZE:
        raise TraceValidationError(f"file too small for header: {size} < {HEADER_SIZE}")

    with open(path, "rb") as f:
        raw_hdr = f.read(HEADER_SIZE)
        hdr = TraceHeader(raw_hdr)

        if hdr.magic != CCR_TRACE_MAGIC:
            raise TraceValidationError(f"bad magic: {hdr.magic!r}")
        if hdr.trace_version != CCR_TRACE_VERSION:
            raise TraceValidationError(
                f"unknown trace_version {hdr.trace_version} (parser supports {CCR_TRACE_VERSION} only)")
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


def validate_sequence(events):
    """Per-socket-cookie monotonic/gapless sequence check (see
    docs/REPLAY_ABI.md v0: seq is global, sock_cookie disambiguates).
    Returns (ok: bool, report: dict).
    """
    by_cookie = {}
    for e in events:
        by_cookie.setdefault(e["sock_cookie"], []).append(e["seq"])

    report = {"distinct_sock_cookies": len(by_cookie), "per_cookie": {}}
    ok = True
    for cookie, seqs in by_cookie.items():
        seqs_sorted = sorted(seqs)
        gaps = []
        for a, b in zip(seqs_sorted, seqs_sorted[1:]):
            if b != a + 1:
                # Gaps here reflect other callback invocations on the SAME
                # socket that were not part of this manifest's global seq
                # space filtering -- since seq is global across all
                # invocations (not per-cookie), a per-cookie subsequence is
                # expected to have gaps whenever another socket's events are
                # interleaved. This function reports raw per-cookie gap
                # count for diagnostics; the authoritative loss check is
                # the global sequence (see validate_global_sequence) plus
                # the invocations==emitted+drops identity (validate_run).
                gaps.append((a, b))
        report["per_cookie"][cookie] = {
            "count": len(seqs), "min_seq": seqs_sorted[0], "max_seq": seqs_sorted[-1],
            "internal_gaps": len(gaps),
        }
    return ok, report


def validate_global_sequence(events):
    """The authoritative gapless check: seq is allocated globally at
    callback entry (ADR-009), so across ALL events in the trace (regardless
    of socket), seq must be exactly the set of integers observed with no
    unexplained gaps relative to the recorded invocations/drops counters
    (checked separately in validate_run against the sidecar).
    """
    seqs = sorted(e["seq"] for e in events)
    gaps = []
    for a, b in zip(seqs, seqs[1:]):
        if b != a + 1:
            gaps.append((a, b))
    return {
        "n": len(seqs),
        "min_seq": seqs[0] if seqs else None,
        "max_seq": seqs[-1] if seqs else None,
        "gaps": gaps,
    }


def select_dominant_connection(events):
    """CCReplay's unit of replay is one connection (docs/SEMANTICS.md: "does
    not replay the complete TCP connection" -- i.e. it replays ONE). A
    recording window can contain events from more than one socket that
    used the recorder's CC name (observed empirically: iperf3 appears to
    apply -C to its control channel as well as its data channel, producing
    one or a handful of stray events on a second, short-lived socket -- see
    ADR-016). This selects the sock_cookie with the most events as "the"
    recorded connection and returns (dominant_cookie, dominant_events,
    other_events).
    """
    counts = {}
    for e in events:
        counts[e["sock_cookie"]] = counts.get(e["sock_cookie"], 0) + 1
    if not counts:
        return None, [], []
    dominant = max(counts, key=lambda k: counts[k])
    dominant_events = [e for e in events if e["sock_cookie"] == dominant]
    other_events = [e for e in events if e["sock_cookie"] != dominant]
    return dominant, dominant_events, other_events


def validate_run(trace_path, meta_path):
    """Full R0 integrity check for one recorded run. Returns dict with a
    top-level "pass": bool and full diagnostic detail. This is the function
    scripts/run_r0.sh and the R0 report should call.
    """
    hdr, events = parse_trace(trace_path)

    with open(meta_path) as f:
        meta = json.load(f)

    global_seq = validate_global_sequence(events)
    _, per_cookie = validate_sequence(events)

    checks = {}
    checks["magic_ok"] = True  # parse_trace already raised if not
    checks["trace_version_known"] = True
    checks["callback_manifest_matches"] = (hdr.callback_manifest == CCR_RENO_MANIFEST)
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
    # Every declared-manifest callback that was invoked at least once
    # (invocations>0 overall) should be representable; we don't require
    # every callback type individually since undo_cwnd may legitimately
    # never fire on a given run (see data/capability_audit.md section E).
    callback_counts = {}
    for e in events:
        callback_counts[e["callback_id"]] = callback_counts.get(e["callback_id"], 0) + 1
    checks["result_present_where_required"] = all(
        e["result_valid"] == 1
        for e in events
        if e["callback_id"] in (CCR_CB_SSTHRESH, CCR_CB_UNDO_CWND)
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
        },
        "meta": meta,
        "n_events": len(events),
        "callback_counts": {CALLBACK_NAMES.get(k, k): v for k, v in callback_counts.items()},
        "global_sequence": global_seq,
        "per_cookie": per_cookie,
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <trace.ccr> <meta.json>", file=sys.stderr)
        sys.exit(2)
    result = validate_run(sys.argv[1], sys.argv[2])
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result["pass"] else 1)
