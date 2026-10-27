"""Permanent regression coverage for the Replay-ABI-v2 differential-debugger
path (user/ccreplay_diff.py + user/ccreplay_checkpoint.py).

That path was implemented during the same integrated session that produced
the CoVegas historical differential result (see
docs/session/LATEST_REVIEW_HANDOFF.md "POST-SUCCESS CONSISTENCY CLOSURE").
These tests move its protection out of session experiment scripts and into
the standing suite.

  3.1  version dispatch  -- a v2 trace reaches the v2 parser/model path
  3.2  mode-dependent comparison schema  -- comparison_fields(cb, pre, post)
       is used (not a flat Reno/CUBIC field set)
  3.3  v2 hard negative  -- fixed/v4 vs fixed/v4 -> NO DIVERGENCE
  3.4  v2 reconstructed-v3 positive  -- fixed/v4 vs reconstructed-v3 on the
       committed historical trace -> first divergence at the precommitted
       Predicate-D callback, with priv_post_mode + priv_post_dlv_rate_compete
       among the differing fields; also exercises pre_mode != post_mode
       (different union-arm selection)

3.3/3.4 load real committed traces (raw/covegas_replay/primary/rep1.ccr,
raw/covegas_campaign/rep4.ccr); ~1-2 s each. This is debugger regression
coverage, not new historical evidence.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "user"))

ROOT = os.path.join(os.path.dirname(__file__), "..")

from user.ccreplay_diff import _detect_version_and_parse, diff_trace
import user.covegas_model as v4
import user.covegas_model_v3_latch as v3
import user.ccr_trace_v2 as t2

REP1 = os.path.join(ROOT, "raw/covegas_replay/primary/rep1.ccr")
REP4 = os.path.join(ROOT, "raw/covegas_campaign/rep4.ccr")


class TestV2VersionDispatch(unittest.TestCase):
    def test_v2_trace_dispatches_to_v2_parser_and_names(self):
        hdr, events, select_dominant, callback_names = _detect_version_and_parse(REP1)
        self.assertEqual(hdr.trace_version, 2)
        self.assertGreater(len(events), 0)
        # v2 CALLBACK_NAMES include init(4) and pkts_acked(7); v0/v1 do not have 7.
        self.assertEqual(callback_names, t2.CALLBACK_NAMES)
        self.assertIn(7, callback_names)
        self.assertEqual(select_dominant, t2.select_dominant_connection)


class TestV2ModeDependentSchema(unittest.TestCase):
    def test_diff_uses_comparison_fields_not_flat_dict(self):
        # covegas_model MUST NOT expose a flat COMPARISON_FIELDS dict, or the
        # diff engine's v2 branch would never be taken.
        self.assertFalse(hasattr(v4, "COMPARISON_FIELDS"))
        self.assertTrue(callable(getattr(v4, "comparison_fields")))

        calls = []
        orig = v4.comparison_fields

        def spy(cb, pre_mode, post_mode):
            calls.append((cb, pre_mode, post_mode))
            return orig(cb, pre_mode, post_mode)

        v4.comparison_fields = spy
        try:
            diff_trace(REP1, "x", v4, v4)
        finally:
            v4.comparison_fields = orig

        self.assertGreater(len(calls), 0)
        for cb, pm, qm in calls:
            self.assertIsInstance(cb, int)
            self.assertIn(pm, (t2.MODE_DELAY, t2.MODE_COMPETE, None))
            self.assertIn(qm, (t2.MODE_DELAY, t2.MODE_COMPETE, None))
        # DELAY-arm vs COMPETE-arm field lists must actually differ.
        delay_fields = set(orig(t2.CCR_CB_CONG_AVOID, t2.MODE_DELAY, t2.MODE_DELAY))
        compete_fields = set(orig(t2.CCR_CB_CONG_AVOID, t2.MODE_COMPETE, t2.MODE_COMPETE))
        self.assertNotEqual(delay_fields, compete_fields)
        self.assertTrue(any(f.startswith("priv_post_delay_") for f in delay_fields))
        self.assertTrue(any(f.startswith("priv_post_cubic_") for f in compete_fields))


class TestV2HardNegative(unittest.TestCase):
    def test_fixed_v4_vs_fixed_v4_no_divergence(self):
        r = diff_trace(REP1, "x", v4, v4)
        self.assertEqual(r["result"], "NO DIVERGENCE")
        self.assertIsNone(r["divergence"])
        self.assertEqual(r["matched_event_count_before_divergence"], r["n_events_dominant"])


class TestV2ReconstructedV3Positive(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(REP4), "historical trace raw/covegas_campaign/rep4.ccr not present")
    def test_fixed_v4_vs_recon_v3_diverges_at_predicate_d(self):
        r = diff_trace(REP4, "x", v4, v3)
        self.assertEqual(r["result"], "DIVERGENCE")
        d = r["divergence"]
        self.assertEqual(d["first_divergent_event"]["seq"], 10421)
        self.assertEqual(d["callback"], "cong_avoid")
        self.assertEqual(r["matched_event_count_before_divergence"], 10420)
        priv = d["private_state_diff"]
        self.assertIn("priv_post_mode", priv)
        self.assertIn("priv_post_dlv_rate_compete", priv)
        self.assertEqual(priv["priv_post_mode"]["reference"], t2.MODE_DELAY)
        self.assertEqual(priv["priv_post_mode"]["candidate"], t2.MODE_COMPETE)
        self.assertEqual(priv["priv_post_dlv_rate_compete"]["reference"], 0)
        self.assertEqual(priv["priv_post_dlv_rate_compete"]["candidate"], 1192908)

    @unittest.skipUnless(os.path.exists(REP4), "historical trace not present")
    def test_pre_mode_differs_from_post_mode_at_divergence(self):
        # At the Predicate-D event the reference (v4) enters as COMPETE and
        # leaves as DELAY -> the diff must gate PRE-arm vs POST-arm fields on
        # different modes.
        calls = []
        orig = v4.comparison_fields

        def spy(cb, pre_mode, post_mode):
            calls.append((cb, pre_mode, post_mode))
            return orig(cb, pre_mode, post_mode)

        v4.comparison_fields = spy
        try:
            diff_trace(REP4, "x", v4, v3)
        finally:
            v4.comparison_fields = orig
        self.assertTrue(any(pm is not None and qm is not None and pm != qm for _, pm, qm in calls))


class TestV2CheckpointReproducer(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(REP4), "historical trace not present")
    def test_covegas_v2_checkpoint_suffix_reproduces_divergence(self):
        from user.ccreplay_checkpoint import (run_with_checkpoints,
                                              nearest_checkpoint_at_or_before,
                                              replay_suffix_from_checkpoint)
        ckpts, first_div, dom, _ = run_with_checkpoints(REP4, v4, v3, 2000)
        self.assertIsNotNone(first_div)
        self.assertEqual(first_div["seq"], 10421)
        self.assertEqual(first_div["callback"], "cong_avoid")
        D = first_div["event_index"]
        ck = nearest_checkpoint_at_or_before(ckpts, D)
        self.assertLessEqual(ck["next_event_index"], D)
        sd = replay_suffix_from_checkpoint(ck, dom, v4, v3, D)
        self.assertIsNotNone(sd)
        self.assertEqual(sd["event_index"], D)
        self.assertEqual(sd["seq"], first_div["seq"])
        self.assertEqual(sd["diff_fields"], first_div["diff_fields"])
        from user.ccreplay_checkpoint import same_divergence
        self.assertTrue(same_divergence(first_div, sd))

    def test_cubic_n6_checkpoint_regression_unchanged(self):
        import user.cubic_model as cubic
        import user.cubic_model_bug_ssthresh as bug
        from user.ccreplay_checkpoint import (run_with_checkpoints,
                                              nearest_checkpoint_at_or_before,
                                              replay_suffix_from_checkpoint)
        trace = os.path.join(ROOT, "raw/cubic_replay/primary/rep1.ccr")
        ckpts, first_div, dom, _ = run_with_checkpoints(trace, cubic, bug, 500)
        self.assertEqual(first_div["event_index"], 1704)
        self.assertEqual(first_div["seq"], 1705)
        D = first_div["event_index"]
        ck = nearest_checkpoint_at_or_before(ckpts, D)
        self.assertEqual(ck["next_event_index"], 1500)
        sd = replay_suffix_from_checkpoint(ck, dom, cubic, bug, D)
        self.assertEqual(sd["event_index"], 1704)
        # state before event 1500, resume 1500..1704 inclusive: 205 transitions,
        # including the failing event (the former 204 skipped event 1500).
        self.assertEqual(D - ck["next_event_index"] + 1, 205)


if __name__ == "__main__":
    unittest.main()
