"""C6 mutation-campaign harness tests (results/c6_mutation_campaign/SPEC.md
sections 3 and 5):
- the generator is deterministic;
- nothing in the oracle/harness exclusion list is ever mutated;
- the identity control (the unparsed reference, built exactly like a mutant)
  agrees with the reference on real recorded events;
- a mutant is really built from its own source (not the reference's).
"""
import os
import sys
import unittest

_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _ROOT)


from experiments.c6_mutation_campaign.complete import c6_common as common  # noqa: E402
from experiments.c6_mutation_campaign.complete import mutate  # noqa: E402
from ccreplay import controllers as controllers_mod  # noqa: E402

PREFIX = 2000  # events per trace replayed by the identity test


class TestGenerator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reno = mutate.generate("reno")
        cls.cubic = mutate.generate("cubic")

    def test_deterministic(self):
        again = mutate.generate("reno")
        self.assertEqual([(r["id"], r.get("sha256")) for r in self.reno],
                         [(r["id"], r.get("sha256")) for r in again])

    def test_ids_unique(self):
        for recs in (self.reno, self.cubic):
            ids = [r["id"] for r in recs]
            self.assertEqual(len(ids), len(set(ids)))

    def test_excluded_functions_never_mutated(self):
        for recs in (self.reno, self.cubic):
            for r in recs:
                self.assertNotIn(r["function"], mutate.EXCLUDED_FUNCS, r["id"])

    def test_excluded_module_names_never_mutated(self):
        src = mutate.MODEL_SOURCES["cubic"].read_text().splitlines()
        for r in self.cubic:
            if r["function"] != "<module>":
                continue
            line = src[r["line"] - 1]
            for name in mutate.EXCLUDED_MODULE_NAMES:
                self.assertFalse(line.startswith(name + " ="), r["id"])
            self.assertFalse(line.startswith("CCR_CB_"), r["id"])

    def test_every_live_mutant_differs_from_reference(self):
        ref = mutate.reference_source("reno")
        for r in self.reno:
            if r["status"] == "live":
                self.assertNotEqual(r["source"], ref, r["id"])
                self.assertTrue(r["diff"], r["id"])

    def test_known_mutant_is_built_from_its_own_source(self):
        rec = next(r for r in self.reno if r["id"].startswith("reno-MMS-model_ssthresh"))
        m = mutate.build_module(rec["id"], rec["source"], "reno")
        result, _ = m.model_ssthresh({"snd_cwnd": 100}, None)
        self.assertEqual(result, 2)  # min(100 >> 1, 2); the reference gives 50


class TestIdentityControl(unittest.TestCase):
    def _check(self, controller, rel_path):
        ref = controllers_mod.load_controller(controller)
        ident = mutate.build_module(f"{controller}-identity", mutate.reference_source(controller), controller)
        events, _ = common.load_events(rel_path)
        pre_fn = common.base_pre_fn(controller)
        for e in events[:PREFIX]:
            a, _ = ref.transition(e, pre_fn(e) if pre_fn else None)
            b, _ = ident.transition(e, pre_fn(e) if pre_fn else None)
            self.assertEqual(a, b, f"seq {e['seq']}")

    def test_reno_identity(self):
        self._check("reno", common.PRIMARY["reno"][0])

    def test_cubic_identity(self):
        self._check("cubic", common.PRIMARY["cubic"][0])


if __name__ == "__main__":
    unittest.main()
