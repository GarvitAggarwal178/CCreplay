"""Phase-3 Kali analysis tests (scripts/kali/*.py): the stdlib Student-t,
Welch CI and TOST verdict rules frozen in data/phase3_kali/SPEC.md Part C,
the iperf3 / ss parsers, and the M9 summarizer on synthetic run files.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "experiments", "kali"))
from experiments.kali import lab_metrics as lm  # noqa: E402
from experiments.kali import lab_summarize  # noqa: E402
from experiments.kali import nonint_analyze as na  # noqa: E402


def _iperf(path, bps, mean_rtt_us, retrans=3):
    json.dump({"end": {"sum_received": {"bits_per_second": bps, "seconds": 60.0},
                       "sum_sent": {"bits_per_second": bps * 1.01, "retransmits": retrans},
                       "streams": [{"sender": {"mean_rtt": mean_rtt_us, "min_rtt": 40000, "max_rtt": 250000}}]}},
              open(path, "w"))


class TestStudentT(unittest.TestCase):
    def test_table_values(self):
        # Standard two-sided critical values.
        for p, df, want in ((0.95, 10, 1.812461), (0.95, 18, 1.734064), (0.975, 5, 2.570582),
                            (0.95, 1, 6.313752), (0.95, 1e6, 1.644855)):
            self.assertAlmostEqual(lm.t_quantile(p, df), want, places=4, msg=(p, df))

    def test_cdf_symmetry(self):
        self.assertAlmostEqual(lm.t_cdf(0.0, 7), 0.5, places=12)
        self.assertAlmostEqual(lm.t_cdf(1.3, 7) + lm.t_cdf(-1.3, 7), 1.0, places=12)


class TestTost(unittest.TestCase):
    def test_verdicts(self):
        self.assertEqual(lm.tost_verdict(-0.5, 0.5, 1.0), "EQUIVALENT")
        self.assertEqual(lm.tost_verdict(1.2, 3.0, 1.0), "NOT EQUIVALENT")
        self.assertEqual(lm.tost_verdict(-3.0, -1.5, 1.0), "NOT EQUIVALENT")
        self.assertEqual(lm.tost_verdict(0.5, 1.5, 1.0), "INCONCLUSIVE")

    def test_welch_ci_hand_computed(self):
        a, b = [10, 12, 11, 13], [9, 10, 9, 11]
        d, lo, hi, df, se = lm.welch_ci(a, b, 0.90)
        self.assertAlmostEqual(d, 1.75)
        self.assertAlmostEqual(se, ((5 / 3) / 4 + (11 / 12) / 4) ** 0.5)
        self.assertTrue(lo < d < hi)


class TestParsers(unittest.TestCase):
    def test_ss_excludes_minrtt(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "ss.log")
            open(p, "w").write("@ 1.0\n cubic rto:204 rtt:120.5/3.2 minrtt:40.1 cwnd:80\n"
                               "@ 1.1\n cubic rtt:130/2.0 minrtt:40\n")
            self.assertEqual(lm.ss_srtt_samples(p), [120.5, 130.0])

    def test_ss_picks_data_socket_not_control(self):
        # Real shape from results/lab/raw: iperf3's control socket (tiny
        # bytes_acked) and the data socket both match `dport = 5201`.
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "ss.log")
            open(p, "w").write(
                "@ 1.0\nESTAB 0 0 10.0.0.1:40460 10.0.1.1:5201\n reno rtt:41.4/15.6 bytes_acked:38 minrtt:40\n"
                "ESTAB 0 110048 10.0.0.1:40476 10.0.1.1:5201\n reno rtt:210.2/3.1 bytes_acked:5000000 minrtt:40\n"
                "@ 1.1\nESTAB 0 0 10.0.0.1:40460 10.0.1.1:5201\n reno rtt:41.0/15.0 bytes_acked:38\n"
                "ESTAB 0 99000 10.0.0.1:40476 10.0.1.1:5201\n reno rtt:215.0/3.0 bytes_acked:5100000\n")
            self.assertEqual(lm.ss_srtt_samples(p), [210.2, 215.0])

    def test_iperf_error_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.json")
            json.dump({"error": "control socket has closed unexpectedly"}, open(p, "w"))
            with self.assertRaises(ValueError):
                lm.iperf3_metrics(p)

    def test_percentile(self):
        self.assertEqual(lm.percentile([1, 2, 3, 4], 50), 2.5)
        self.assertEqual(lm.percentile([5], 95), 5)


class TestNonintAnalysis(unittest.TestCase):
    def _rows(self, rtt_shift_ms, n=10):
        rows = []
        for i in range(n):
            for arm, shift in (("R", rtt_shift_ms), ("C", 0.0)):
                rows.append({"run": len(rows) + 1, "arm": arm, "throughput_bps": 9.6e6 + (i % 3) * 1e3,
                             "mean_rtt_ms": 200.0 + (i % 4) * 0.2 + shift, "retransmits": 5,
                             "invocations_all_callbacks": 25000})
        return rows

    def test_identical_arms_pass(self):
        self.assertEqual(na.analyze(self._rows(0.0))["verdict"], "PASS")

    def test_rtt_shift_fails(self):
        r = na.analyze(self._rows(5.0))
        self.assertEqual(r["metrics"]["mean_rtt"]["verdict"], "NOT EQUIVALENT")
        self.assertEqual(r["verdict"], "FAIL")

    def test_too_few_runs_incomplete(self):
        self.assertEqual(na.analyze(self._rows(0.0, n=5))["verdict"], "INCOMPLETE")

    def test_reads_run_files(self):
        with tempfile.TemporaryDirectory() as d:
            for i, arm in enumerate("CR", 1):
                _iperf(os.path.join(d, f"run{i:02d}_{arm}_iperf3.json"), 9.6e6, 200000)
                json.dump({"invocations": 100, "emitted": 0 if arm == "C" else 100, "drops": 0},
                          open(os.path.join(d, f"run{i:02d}_{arm}.meta.json"), "w"))
            rows = na.run_rows(d)
            self.assertEqual([(r["run"], r["arm"], r["mean_rtt_ms"]) for r in rows], [(1, "C", 200.0), (2, "R", 200.0)])


class TestLabSummarize(unittest.TestCase):
    def test_summarize_competing_run(self):
        with tempfile.TemporaryDirectory() as raw, tempfile.TemporaryDirectory() as out:
            p = os.path.join(raw, "L0-reno-vs-cubic_rep1")
            json.dump({"config": "L0-reno-vs-cubic", "loss_pct": 0, "cca": "reno", "competing_cca": "cubic",
                       "rep": 1, "duration_s": 30, "buffer_bytes": 250000}, open(p + "_config.json", "w"))
            _iperf(p + "_iperf3_5201.json", 4e6, 180000)
            _iperf(p + "_iperf3_5301.json", 5.6e6, 185000)
            open(p + "_ss_5201.log", "w").write("rtt:180/1\n")
            open(p + "_ss_5301.log", "w").write("rtt:185/1\n")
            lab_summarize.main(raw, out)
            res = json.load(open(os.path.join(out, "L0-reno-vs-cubic_rep1.json")))
            self.assertEqual([f["cca"] for f in res["flows"]], ["reno", "cubic"])
            self.assertEqual(res["flows"][1]["throughput_bps"], 5.6e6)
            self.assertIn("not CCReplay replay output", res["note"])


if __name__ == "__main__":
    unittest.main()
