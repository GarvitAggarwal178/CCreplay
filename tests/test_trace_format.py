"""Trace format tests (CLAUDE.md section 17):
- version rejection;
- malformed trace rejection;
- sequence-gap detection;
- drop metadata handling.

Builds small synthetic .ccr files byte-for-byte (using the same struct
formats as user/ccr_trace.py) rather than depending on real R0 traces, so
these tests exercise edge cases R0's own clean traces never hit.
"""
import sys
import os
import struct
import json
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from user.ccr_trace import (
    HEADER_FMT, HEADER_SIZE, EVENT_FMT, EVENT_SIZE,
    CCR_TRACE_MAGIC, CCR_RENO_MANIFEST,
    parse_trace, validate_global_sequence, validate_run, TraceValidationError,
)


def make_header(magic=CCR_TRACE_MAGIC, trace_version=0, recorder_version=1,
                 kernel_release=b"test-kernel", reference_impl_id=b"linux_tcp_reno_kfunc",
                 callback_manifest=CCR_RENO_MANIFEST, private_state_schema_id=0,
                 record_size=EVENT_SIZE, creation_ts_ns=12345):
    return struct.pack(
        HEADER_FMT, magic, trace_version, recorder_version,
        kernel_release.ljust(65, b"\x00"), reference_impl_id.ljust(32, b"\x00"),
        callback_manifest, private_state_schema_id, record_size, creation_ts_ns)


def make_event(seq, sock_cookie=1, ts_ns=0, callback_id=2, in_ack=0, in_acked=1,
               pre_snd_cwnd=10, pre_snd_ssthresh=2147483647, pre_snd_cwnd_cnt=0,
               pre_snd_cwnd_clamp=4294967295, pre_prior_cwnd=0, pre_max_packets_out=10,
               pre_is_cwnd_limited=1, result_valid=0, result=0,
               post_snd_cwnd=11, post_snd_cwnd_cnt=0):
    return struct.pack(
        EVENT_FMT, seq, sock_cookie, ts_ns, callback_id, 0, in_ack, in_acked,
        pre_snd_cwnd, pre_snd_ssthresh, pre_snd_cwnd_cnt, pre_snd_cwnd_clamp,
        pre_prior_cwnd, pre_max_packets_out, pre_is_cwnd_limited,
        result_valid, result, post_snd_cwnd, post_snd_cwnd_cnt)


def write_trace(path, header_bytes, event_list):
    with open(path, "wb") as f:
        f.write(header_bytes)
        for ev in event_list:
            f.write(ev)


class TestVersionRejection(unittest.TestCase):
    def test_unknown_trace_version_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.ccr")
            write_trace(path, make_header(trace_version=99), [make_event(0)])
            with self.assertRaises(TraceValidationError):
                parse_trace(path)

    def test_bad_magic_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.ccr")
            write_trace(path, make_header(magic=b"BADMAGIC"), [make_event(0)])
            with self.assertRaises(TraceValidationError):
                parse_trace(path)

    def test_known_version_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.ccr")
            write_trace(path, make_header(), [make_event(0)])
            hdr, events = parse_trace(path)
            self.assertEqual(hdr.trace_version, 0)
            self.assertEqual(len(events), 1)


class TestMalformedTraceRejection(unittest.TestCase):
    def test_truncated_header_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.ccr")
            with open(path, "wb") as f:
                f.write(make_header()[:HEADER_SIZE - 10])
            with self.assertRaises(TraceValidationError):
                parse_trace(path)

    def test_trailing_partial_record_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.ccr")
            with open(path, "wb") as f:
                f.write(make_header())
                f.write(make_event(0))
                f.write(b"\x00" * (EVENT_SIZE // 2))  # half a trailing record
            with self.assertRaises(TraceValidationError):
                parse_trace(path)

    def test_record_size_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.ccr")
            write_trace(path, make_header(record_size=1234), [make_event(0)])
            with self.assertRaises(TraceValidationError):
                parse_trace(path)

    def test_empty_trace_body_is_not_malformed(self):
        """Zero events is structurally valid (just an unusual run)."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.ccr")
            write_trace(path, make_header(), [])
            hdr, events = parse_trace(path)
            self.assertEqual(events, [])


class TestSequenceGapDetection(unittest.TestCase):
    def test_gapless_sequence_detected_as_ok(self):
        events = [{"seq": s} for s in range(10)]
        report = validate_global_sequence(events)
        self.assertEqual(report["gaps"], [])

    def test_interior_gap_detected(self):
        events = [{"seq": s} for s in [0, 1, 2, 4, 5]]  # missing 3
        report = validate_global_sequence(events)
        self.assertEqual(report["gaps"], [(2, 4)])

    def test_multiple_gaps_all_detected(self):
        events = [{"seq": s} for s in [0, 2, 3, 7, 8]]  # missing 1, 4,5,6
        report = validate_global_sequence(events)
        self.assertEqual(report["gaps"], [(0, 2), (3, 7)])


class TestDropMetadataHandling(unittest.TestCase):
    def _write(self, d, invocations, emitted, drops, n_events, counters_read_ok=True):
        trace_path = os.path.join(d, "t.ccr")
        meta_path = os.path.join(d, "t.meta.json")
        events = [make_event(s) for s in range(n_events)]
        write_trace(trace_path, make_header(), events)
        with open(meta_path, "w") as f:
            json.dump({
                "trace_version": 0, "recorder_version": 1, "kernel_release": "test",
                "invocations": invocations, "emitted": emitted, "drops": drops,
                "counters_read_ok": counters_read_ok,
                "events_written_userspace": n_events,
                "trace_file_bytes": 0, "duration_s_requested": 1,
                "bpf_stats": {"ssthresh": {"run_time_ns": 0, "run_cnt": 0},
                              "cong_avoid": {"run_time_ns": 0, "run_cnt": 0},
                              "undo_cwnd": {"run_time_ns": 0, "run_cnt": 0}},
            }, f)
        return trace_path, meta_path

    def test_zero_drops_clean_run_passes(self):
        with tempfile.TemporaryDirectory() as d:
            trace_path, meta_path = self._write(d, invocations=5, emitted=5, drops=0, n_events=5)
            result = validate_run(trace_path, meta_path)
            self.assertTrue(result["pass"], result["checks"])
            self.assertTrue(result["checks"]["zero_drops"])

    def test_nonzero_drops_fails_zero_drops_check_but_integrity_identity_can_still_hold(self):
        with tempfile.TemporaryDirectory() as d:
            # 5 invocations, only 3 emitted (2 dropped) -- integrity identity
            # invocations == emitted + drops holds, but zero_drops fails and
            # the trace file only contains the 3 that were actually emitted.
            trace_path, meta_path = self._write(d, invocations=5, emitted=3, drops=2, n_events=3)
            result = validate_run(trace_path, meta_path)
            self.assertTrue(result["checks"]["invocations_eq_emitted_plus_drops"])
            self.assertFalse(result["checks"]["zero_drops"])
            self.assertFalse(result["pass"], "a trace with any drops must not PASS R0")

    def test_broken_integrity_identity_detected(self):
        with tempfile.TemporaryDirectory() as d:
            # invocations != emitted + drops -- the tail-truncation case
            # ADR-013 exists to catch (drop counter says 0, but fewer
            # events were actually written than were invoked).
            trace_path, meta_path = self._write(d, invocations=10, emitted=7, drops=0, n_events=7)
            result = validate_run(trace_path, meta_path)
            self.assertFalse(result["checks"]["invocations_eq_emitted_plus_drops"])
            self.assertFalse(result["pass"])

    def test_counters_read_failure_detected(self):
        with tempfile.TemporaryDirectory() as d:
            trace_path, meta_path = self._write(
                d, invocations=5, emitted=5, drops=0, n_events=5, counters_read_ok=False)
            result = validate_run(trace_path, meta_path)
            self.assertFalse(result["checks"]["counters_read_ok"])
            self.assertFalse(result["pass"])


if __name__ == "__main__":
    unittest.main()
