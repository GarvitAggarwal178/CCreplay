"""Controller model tests (CLAUDE.md section 17):
- deterministic repeated replay;
- callback-specific known transition tests.

Known-transition cases are drawn from real events actually observed in
data/audit_src/fields_out.csv / fields_undo_out.csv (see
data/capability_audit.md sections E/F), not invented -- each test's
docstring names which real event it reproduces.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from user.reno_model import (
    tcp_is_cwnd_limited, tcp_slow_start, tcp_cong_avoid_ai,
    model_cong_avoid, model_ssthresh, model_undo_cwnd, transition,
    NONE_PRIVATE_STATE, CCR_CB_SSTHRESH, CCR_CB_CONG_AVOID, CCR_CB_UNDO_CWND,
)


class TestDeterminism(unittest.TestCase):
    def test_cong_avoid_deterministic(self):
        pre = {"snd_cwnd": 10, "snd_ssthresh": 2147483647, "snd_cwnd_cnt": 0,
               "snd_cwnd_clamp": 4294967295, "max_packets_out": 10, "is_cwnd_limited": 1,
               "prior_cwnd": 0}
        results = [model_cong_avoid(pre, 683934925, 1, NONE_PRIVATE_STATE) for _ in range(20)]
        self.assertEqual(len(set(results)), 1, "same input must produce same output every call")

    def test_transition_deterministic_over_event_dict(self):
        e = {
            "callback_id": CCR_CB_CONG_AVOID, "in_ack": 1, "in_acked": 1,
            "pre_snd_cwnd": 10, "pre_snd_ssthresh": 2147483647, "pre_snd_cwnd_cnt": 0,
            "pre_snd_cwnd_clamp": 4294967295, "pre_prior_cwnd": 0,
            "pre_max_packets_out": 10, "pre_is_cwnd_limited": 1,
        }
        r1, s1 = transition(e, NONE_PRIVATE_STATE)
        r2, s2 = transition(e, NONE_PRIVATE_STATE)
        self.assertEqual(r1, r2)
        self.assertEqual(s1, s2)


class TestKnownCongAvoidTransitions(unittest.TestCase):
    """Real events from data/audit_src/fields_out.csv."""

    def test_gated_no_growth_ack_683933477(self):
        """Real event: cwnd=10 ssthresh=MAX max_packets_out=1 is_cwnd_limited=0
        -> not cwnd-limited -> cong_avoid is a complete no-op."""
        pre = {"snd_cwnd": 10, "snd_ssthresh": 2147483647, "snd_cwnd_cnt": 0,
               "snd_cwnd_clamp": 4294967295, "max_packets_out": 1, "is_cwnd_limited": 0,
               "prior_cwnd": 0}
        cwnd, cwnd_cnt, _ = model_cong_avoid(pre, 683933477, 1, NONE_PRIVATE_STATE)
        self.assertEqual((cwnd, cwnd_cnt), (10, 0))

    def test_slow_start_growth_ack_683934925(self):
        """Real event: cwnd=10 ssthresh=MAX max_packets_out=10 is_cwnd_limited=1
        -> cwnd-limited, in slow start -> cwnd grows by acked=1."""
        pre = {"snd_cwnd": 10, "snd_ssthresh": 2147483647, "snd_cwnd_cnt": 0,
               "snd_cwnd_clamp": 4294967295, "max_packets_out": 10, "is_cwnd_limited": 1,
               "prior_cwnd": 0}
        cwnd, cwnd_cnt, _ = model_cong_avoid(pre, 683934925, 1, NONE_PRIVATE_STATE)
        self.assertEqual((cwnd, cwnd_cnt), (11, 0))

    def test_congestion_avoidance_ai_phase(self):
        """Once past slow start (cwnd >= ssthresh), growth is +1/RTT via the
        AI counter, not +1 per ACK -- cwnd must NOT grow on every call."""
        pre = {"snd_cwnd": 50, "snd_ssthresh": 25, "snd_cwnd_cnt": 0,
               "snd_cwnd_clamp": 4294967295, "max_packets_out": 50, "is_cwnd_limited": 1,
               "prior_cwnd": 0}
        cwnd, cwnd_cnt, _ = model_cong_avoid(pre, 1, 1, NONE_PRIVATE_STATE)
        self.assertEqual(cwnd, 50, "one ACK must not grow cwnd during AI phase")
        self.assertEqual(cwnd_cnt, 1)

        # Feed 49 more acks (cwnd_cnt reaches w=50) -> cwnd increments once.
        pre2 = dict(pre)
        pre2["snd_cwnd_cnt"] = 49
        cwnd2, cwnd_cnt2, _ = model_cong_avoid(pre2, 1, 1, NONE_PRIVATE_STATE)
        self.assertEqual(cwnd2, 51)
        self.assertEqual(cwnd_cnt2, 0)


class TestKnownSsthreshTransitions(unittest.TestCase):
    def test_formula_matches_real_events(self):
        """max(cwnd>>1, 2), confirmed exactly on 5/5 real events
        (data/capability_audit.md section E)."""
        for cwnd, expected in [(10, 5), (373, 186), (2, 2), (3, 2)]:
            ret, _ = model_ssthresh({"snd_cwnd": cwnd}, NONE_PRIVATE_STATE)
            self.assertEqual(ret, expected)


class TestKnownUndoCwndTransitions(unittest.TestCase):
    def test_formula_matches_real_events(self):
        """max(snd_cwnd, prior_cwnd), confirmed exactly on 8/8 real events
        from the auxiliary reorder capture (data/capability_audit.md
        section E): (pre_cwnd, prior_cwnd) -> expected ret."""
        cases = [(11, 20, 20), (14, 22, 22), (25, 27, 27), (17, 28, 28),
                 (18, 28, 28), (108, 110, 110), (105, 110, 110), (102, 110, 110)]
        for cwnd, prior, expected in cases:
            ret, _ = model_undo_cwnd({"snd_cwnd": cwnd, "prior_cwnd": prior}, NONE_PRIVATE_STATE)
            self.assertEqual(ret, expected)


class TestPrivateStateThreading(unittest.TestCase):
    """Reno has no private state (ADR-014): confirm the sentinel is threaded
    through unchanged rather than silently dropped or reinitialized."""

    def test_private_state_unchanged_across_all_callback_types(self):
        base = {"pre_snd_cwnd": 10, "pre_snd_ssthresh": 20, "pre_snd_cwnd_cnt": 0,
                "pre_snd_cwnd_clamp": 4294967295, "pre_prior_cwnd": 5,
                "pre_max_packets_out": 10, "pre_is_cwnd_limited": 1,
                "in_ack": 1, "in_acked": 1}
        for cb in (CCR_CB_SSTHRESH, CCR_CB_CONG_AVOID, CCR_CB_UNDO_CWND):
            e = dict(base, callback_id=cb)
            _, next_state = transition(e, NONE_PRIVATE_STATE)
            self.assertIsNone(next_state)


if __name__ == "__main__":
    unittest.main()
