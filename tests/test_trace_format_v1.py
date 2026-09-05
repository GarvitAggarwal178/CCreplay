"""Trace format tests for Replay ABI v1 (CUBIC) -- mirrors
tests/test_trace_format.py's coverage (version rejection, malformed trace
rejection, sequence-gap detection, drop metadata handling) for the wider
v1 event record, plus a v1-specific clock-classification test (ADR-018).

Builds small synthetic .ccr files byte-for-byte using the same struct
format as user/ccr_trace_v1.py, independent of any real recorded trace.
Does not modify or duplicate tests/test_trace_format.py's v0 coverage.
"""
import sys
import os
import struct
import json
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "user"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from user.ccr_trace import HEADER_FMT, HEADER_SIZE, CCR_TRACE_MAGIC
from user.ccr_trace_v1 import (
    EVENT_FMT, EVENT_SIZE, EVENT_FIELDS, CCR_CUBIC_MANIFEST,
    CCR_PRIVATE_SCHEMA_CUBIC_V1, CCR_CB_CONG_AVOID, CCR_CB_SSTHRESH,
    parse_trace_v1, validate_run_v1, clock_classification, TraceValidationError,
)

# Every field defaults to 0 except a few given sane non-degenerate values,
# matching how a real init/cong_avoid event would look (pre_snd_ssthresh at
# TCP_INFINITE_SSTHRESH, pre_snd_cwnd_clamp at UINT_MAX -- the same real
# values observed in the loopback smoke trace this parser was validated
# against).
_DEFAULTS = {f: 0 for f in EVENT_FIELDS}
_DEFAULTS.update({
    "sock_cookie": 1,
    "callback_id": CCR_CB_CONG_AVOID,
    "pre_snd_cwnd": 10,
    "pre_snd_ssthresh": 2147483647,
    "pre_snd_cwnd_clamp": 4294967295,
    "pre_max_packets_out": 10,
    "pre_is_cwnd_limited": 1,
    "post_snd_cwnd": 11,
    "priv_pre_raw": b"\x00" * 104,
    "priv_post_raw": b"\x00" * 104,
})


def make_header(magic=CCR_TRACE_MAGIC, trace_version=1, recorder_version=1,
                 kernel_release=b"test-kernel", reference_impl_id=b"linux_tcp_cubic_kfunc",
                 callback_manifest=CCR_CUBIC_MANIFEST,
                 private_state_schema_id=CCR_PRIVATE_SCHEMA_CUBIC_V1,
                 record_size=EVENT_SIZE, creation_ts_ns=12345):
    return struct.pack(
        HEADER_FMT, magic, trace_version, recorder_version,
        kernel_release.ljust(65, b"\x00"), reference_impl_id.ljust(32, b"\x00"),
        callback_manifest, private_state_schema_id, record_size, creation_ts_ns)


def make_event_v1(seq, **overrides):
    vals = dict(_DEFAULTS)
    vals["seq"] = seq
    vals.update(overrides)
    return struct.pack(EVENT_FMT, *(vals[f] for f in EVENT_FIELDS))


def write_trace(path, header_bytes, event_list):
    with open(path, "wb") as f:
        f.write(header_bytes)
        for ev in event_list:
            f.write(ev)


class TestV1VersionRejection(unittest.TestCase):
    def test_v0_trace_version_rejected_by_v1_parser(self):
        with tempfile.NamedTemporaryFile(suffix=".ccr", delete=False) as tf:
            write_trace(tf.name, make_header(trace_version=0), [make_event_v1(0)])
        with self.assertRaises(TraceValidationError):
            parse_trace_v1(tf.name)
        os.unlink(tf.name)

    def test_known_v1_version_accepted(self):
        with tempfile.NamedTemporaryFile(suffix=".ccr", delete=False) as tf:
            write_trace(tf.name, make_header(), [make_event_v1(0)])
        hdr, events = parse_trace_v1(tf.name)
        self.assertEqual(hdr.trace_version, 1)
        self.assertEqual(len(events), 1)
        os.unlink(tf.name)

    def test_bad_magic_rejected(self):
        with tempfile.NamedTemporaryFile(suffix=".ccr", delete=False) as tf:
            write_trace(tf.name, make_header(magic=b"NOTCCRPL"), [make_event_v1(0)])
        with self.assertRaises(TraceValidationError):
            parse_trace_v1(tf.name)
        os.unlink(tf.name)


class TestV1MalformedTraceRejection(unittest.TestCase):
    def test_truncated_header_rejected(self):
        with tempfile.NamedTemporaryFile(suffix=".ccr", delete=False) as tf:
            tf.write(make_header()[:100])
        with self.assertRaises(TraceValidationError):
            parse_trace_v1(tf.name)
        os.unlink(tf.name)

    def test_trailing_partial_record_rejected(self):
        with tempfile.NamedTemporaryFile(suffix=".ccr", delete=False) as tf:
            tf.write(make_header())
            tf.write(make_event_v1(0))
            tf.write(b"\x00" * 10)  # partial trailing record
        with self.assertRaises(TraceValidationError):
            parse_trace_v1(tf.name)
        os.unlink(tf.name)

    def test_record_size_mismatch_rejected(self):
        with tempfile.NamedTemporaryFile(suffix=".ccr", delete=False) as tf:
            write_trace(tf.name, make_header(record_size=EVENT_SIZE + 8), [make_event_v1(0)])
        with self.assertRaises(TraceValidationError):
            parse_trace_v1(tf.name)
        os.unlink(tf.name)

    def test_empty_trace_body_is_not_malformed(self):
        with tempfile.NamedTemporaryFile(suffix=".ccr", delete=False) as tf:
            write_trace(tf.name, make_header(), [])
        hdr, events = parse_trace_v1(tf.name)
        self.assertEqual(events, [])
        os.unlink(tf.name)


class TestV1SequenceGapDetection(unittest.TestCase):
    def test_gapless_sequence_detected_as_ok(self):
        with tempfile.NamedTemporaryFile(suffix=".ccr", delete=False) as tf:
            write_trace(tf.name, make_header(), [make_event_v1(i) for i in range(5)])
        _, events = parse_trace_v1(tf.name)
        from user.ccr_trace import validate_global_sequence
        report = validate_global_sequence(events)
        self.assertEqual(report["gaps"], [])
        os.unlink(tf.name)

    def test_interior_gap_detected(self):
        with tempfile.NamedTemporaryFile(suffix=".ccr", delete=False) as tf:
            write_trace(tf.name, make_header(),
                        [make_event_v1(0), make_event_v1(1), make_event_v1(3)])
        _, events = parse_trace_v1(tf.name)
        from user.ccr_trace import validate_global_sequence
        report = validate_global_sequence(events)
        self.assertEqual(report["gaps"], [(1, 3)])
        os.unlink(tf.name)


class TestV1ClockClassification(unittest.TestCase):
    def test_stable_when_jiffies_unchanged(self):
        ev = dict(_DEFAULTS)
        ev["clock_jiffies32_before"] = 100
        ev["clock_jiffies32_after"] = 100
        self.assertEqual(clock_classification(ev), "CLOCK_STABLE")

    def test_ambiguous_when_jiffies_changed(self):
        ev = dict(_DEFAULTS)
        ev["clock_jiffies32_before"] = 100
        ev["clock_jiffies32_after"] = 101
        self.assertEqual(clock_classification(ev), "CLOCK_AMBIGUOUS")


class TestV1DropMetadataHandling(unittest.TestCase):
    def _write_run(self, tmpdir, events, meta_overrides=None):
        trace_path = os.path.join(tmpdir, "t.ccr")
        meta_path = os.path.join(tmpdir, "t.meta.json")
        write_trace(trace_path, make_header(), events)
        meta = {
            "invocations": len(events), "emitted": len(events), "drops": 0,
            "clock_stable": len(events), "clock_ambiguous": 0,
            "counters_read_ok": True, "events_written_userspace": len(events),
        }
        if meta_overrides:
            meta.update(meta_overrides)
        with open(meta_path, "w") as f:
            json.dump(meta, f)
        return trace_path, meta_path

    def test_zero_drops_clean_run_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            events = [make_event_v1(i) for i in range(5)]
            trace_path, meta_path = self._write_run(tmpdir, events)
            result = validate_run_v1(trace_path, meta_path)
            self.assertTrue(result["pass"], result["checks"])

    def test_nonzero_drops_fails_zero_drops_check(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            events = [make_event_v1(i) for i in range(5)]
            trace_path, meta_path = self._write_run(
                tmpdir, events,
                {"invocations": 6, "emitted": 5, "drops": 1})
            result = validate_run_v1(trace_path, meta_path)
            self.assertFalse(result["checks"]["zero_drops"])
            self.assertTrue(result["checks"]["invocations_eq_emitted_plus_drops"])

    def test_clock_ambiguous_mismatch_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            events = [make_event_v1(i) for i in range(5)]
            trace_path, meta_path = self._write_run(
                tmpdir, events, {"clock_stable": 3, "clock_ambiguous": 2})
            result = validate_run_v1(trace_path, meta_path)
            self.assertFalse(result["checks"]["clock_ambiguous_count_matches_sidecar"])


if __name__ == "__main__":
    unittest.main()
