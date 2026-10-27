"""Replay ABI ablation harness tests (data/abi_ablation/SPEC.md sections 4-5):
- masking works on a copy and never alters the recorded event (the oracle);
- no mask contains an oracle (result / POST) field;
- the unmasked loop is exact self-replay on real recorded events, both modes.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from user import replay_ablation as ab  # noqa: E402
from user.ccreplay_diff import _detect_version_and_parse  # noqa: E402

PREFIX = 3000


def _events(rel_path):
    _, raw, select, names = _detect_version_and_parse(os.path.join(ab.ROOT, rel_path))
    _, ev, _ = select(raw)
    ev.sort(key=lambda e: e["seq"])
    return ev[:PREFIX], names


class TestMasks(unittest.TestCase):
    def test_no_oracle_field_is_masked(self):
        for controller in ab.TRACES:
            for _, _, fields in ab.masks_for(controller):
                for f in fields or []:
                    self.assertFalse(f.startswith(ab.ORACLE_PREFIXES), (controller, f))

    def test_masks_unique_and_cover_every_class_field(self):
        for controller in ab.TRACES:
            ids = [m for m, _, _ in ab.masks_for(controller)]
            self.assertEqual(len(ids), len(set(ids)))
            for fs in ab.classes_for(controller).values():
                for f in fs:
                    self.assertIn(f"field:{f}", ids)

    def test_mask_does_not_touch_original(self):
        e = {"pre_snd_cwnd": 10, "post_snd_cwnd": 11}
        m = ab._masked(e, ["pre_snd_cwnd"])
        self.assertEqual(m["pre_snd_cwnd"], 0)
        self.assertEqual(e["pre_snd_cwnd"], 10)
        self.assertIsNot(ab._masked(e, None), e)


class TestBaselineOnRealEvents(unittest.TestCase):
    def _baseline(self, controller, rel_path):
        events, names = _events(rel_path)
        ad = ab.Adapter(controller)
        for mode in ("A", "B"):
            r = ab.run_mask(ad, events, names, [], mode)
            self.assertEqual(r["mismatch_events"], 0, (controller, mode, r["first_failure"]))

    def test_reno_baseline(self):
        self._baseline("reno", ab.TRACES["reno"][0])

    def test_covegas_baseline(self):
        self._baseline("covegas", ab.TRACES["covegas"][0])

    def test_masked_event_is_detected(self):
        events, names = _events(ab.TRACES["reno"][0])
        r = ab.run_mask(ab.Adapter("reno"), events, names, ["pre_snd_cwnd"], "A")
        self.assertIsNotNone(r["first_failure"])
        self.assertTrue(all(f.startswith(ab.ORACLE_PREFIXES) for f in r["first_failure"]["diff_fields"]))


if __name__ == "__main__":
    unittest.main()
