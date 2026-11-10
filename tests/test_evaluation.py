"""Regression tests for metric accounting and external-dataset reporting."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import evaluate
import wifall_check
from wifisense.detectors import MotionConfig


def result(labels, predictions, times=None):
    n = len(labels)
    return {
        "label": np.asarray(labels),
        "motion": np.asarray(predictions, dtype=bool),
        "score": np.full(n, 0.2),
        "host_t": np.arange(n) * 0.1 if times is None else np.asarray(times),
    }


class MotionMetricsTests(unittest.TestCase):
    def test_stuck_on_prediction_counts_static_tail_after_release_guard(self):
        res = result(["walk"] * 10 + ["still"] * 50, [True] * 60)
        metrics = evaluate.compute_intuitive_metrics(res)
        self.assertEqual(metrics["walk_tp"], 1)
        self.assertEqual(metrics["neg_seconds"], 2.0)
        self.assertEqual(metrics["fp_seconds"], 2.0)
        self.assertEqual(metrics["fp_total"], 1)
        self.assertEqual(metrics["fp_still"], 1)
        self.assertEqual(metrics["static_acc_pct"], 0.0)

    def test_prediction_across_unlabelled_region_counts_only_labelled_negatives(self):
        res = result(["empty"] * 5 + ["unlabeled"] * 4 + ["fan_empty"] * 5, [True] * 14)
        metrics = evaluate.compute_intuitive_metrics(res)
        self.assertEqual(metrics["fp_seconds"], 1.0)
        self.assertEqual(metrics["fp_total"], 2)
        self.assertEqual(metrics["fp_empty"], 1)
        self.assertEqual(metrics["fp_fan_empty"], 1)

    def test_latency_uses_recorded_timestamps_when_output_hops_are_missing(self):
        res = result(["walk"] * 6, [False, False, True, True, True, True],
                     [10.0, 10.1, 10.7, 10.8, 10.9, 11.0])
        self.assertAlmostEqual(evaluate.compute_intuitive_metrics(res)["lat_mean_s"], 0.7)

    def test_absent_static_observations_do_not_report_perfect_stability(self):
        metrics = evaluate.compute_intuitive_metrics(result(["walk"] * 6, [False] * 6))
        self.assertTrue(np.isnan(metrics["static_acc_pct"]))
        self.assertTrue(np.isnan(metrics["fp_time_pct"]))


class EvaluationReportTests(unittest.TestCase):
    def test_report_percentages_and_latency_pool_across_sessions(self):
        # Session 1: one hit at 0.2 s, one miss. Session 2: three hits at 0.4 s.
        first = result(["walk"] * 10 + ["still"] * 40 + ["walk"] * 10,
                       [False] * 2 + [True] * 8 + [False] * 50)
        labels = (["walk"] * 10 + ["still"] * 40) * 3
        predictions = ([False] * 4 + [True] * 6 + [False] * 40) * 3
        second = result(labels, predictions)
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "calib.json"
            MotionConfig().save(str(cfg))
            session = SimpleNamespace(name="one", meta={"experiment_id": "E1"},
                                      dev_t=np.array([0.0, 1.0]), rssi=np.array([-50, -50]))
            session2 = SimpleNamespace(**{**vars(session), "name": "two"})
            with patch.object(sys, "argv", ["evaluate.py", "--out", tmp, "--calib", str(cfg)]), \
                 patch.object(evaluate, "list_sessions", return_value=["one", "two"]), \
                 patch.object(evaluate, "load_session", side_effect=[session, session2]), \
                 patch.object(evaluate, "run_offline", side_effect=[first, second]):
                evaluate.main()
            report = (Path(tmp) / "experiment_results.md").read_text(encoding="utf-8")
            self.assertIn("4/5 (80%)", report)
            self.assertNotIn("4/5 (100%)", report)
            self.assertIn("0.35 ± 0.09s", report)


class WiFallTests(unittest.TestCase):
    def write_csv(self, path, timestamps, extra_rows=()):
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["local_timestamp", "data"])
            writer.writerows(extra_rows)
            for i, timestamp in enumerate(timestamps):
                iq = [int(20 + 6 * np.sin(i * 0.4 + sub * 0.1)) for sub in range(104)]
                writer.writerow([timestamp, json.dumps(iq)])

    def test_malformed_iq_rows_are_skipped_without_poisoning_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.csv"
            self.write_csv(path, range(0, 800000, 20000), [
                [0, json.dumps(None)], [0, json.dumps(["bad"] * 104)],
                [0, json.dumps([float("nan")] * 104)],
            ])
            loaded = wifall_check.load_wifall_csv(str(path))
            self.assertIsNotNone(loaded)
            t, amplitude = loaded
            self.assertEqual(amplitude.shape, (40, 52))
            self.assertTrue(np.isfinite(amplitude).all())
            self.assertAlmostEqual(t[-1], 0.78)

    def test_32_bit_timestamp_wrap_preserves_actual_packet_interval(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.csv"
            timestamps = [((2 ** 32 - 100000) + i * 20000) % (2 ** 32) for i in range(40)]
            self.write_csv(path, timestamps)
            t, _ = wifall_check.load_wifall_csv(str(path))
            np.testing.assert_allclose(np.diff(t), 0.02, atol=1e-8)
            self.assertAlmostEqual(t[-1], 0.78)

    def test_single_subject_activity_subset_produces_accurate_report_and_plot(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "raw" / "ID2" / "walk"
            source.mkdir(parents=True)
            for i in range(2):
                self.write_csv(source / f"walk{i}.csv", range(0, 3000000, 20000))
            destination = Path(tmp) / "out"
            wifall_check.analyze_wifall(str(source.parents[1]), str(destination))
            report = (destination / "wifall_report.md").read_text(encoding="utf-8")
            self.assertIn("1 người", report)
            self.assertNotIn("10 người", report)
            self.assertTrue((destination / "Hinh4_WiFall_10Nguoi.png").is_file())


if __name__ == "__main__":
    unittest.main()
