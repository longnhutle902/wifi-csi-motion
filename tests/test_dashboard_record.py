"""Regression coverage for dashboard timing and experiment recording failures."""
from pathlib import Path
import queue
import json
import sys
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))
import record
import web_dashboard as dashboard
from wifisense.csi_io import CsiPacket


class IdleSource:
    def __init__(self, port="COM4", baud=115200, **kwargs):
        self.port = port
        self.ser = None
        self.q = queue.Queue()
        self.stopped = False

    def start(self):
        pass

    def stop(self):
        self.stopped = True

    def join(self, timeout=None):
        pass


class StopLoop(Exception):
    pass


def enqueue(source, start, count):
    for i in range(count):
        pkt = CsiPacket(i, i, int((start + i * .02) * 1e6), -50,
                        -90, 0, 1, 0, 0, 11, 0, np.ones(52, dtype=np.complex64))
        source.q.put((1000.0 + start + i * .02, "CSI,test", pkt))


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        args = SimpleNamespace(calib=str(Path(self.tmp.name) / "calib.json"),
                               motion_model=None, replay=None, port="COM4", baud=115200, speed=1.)
        with patch.object(dashboard, "SerialSource", IdleSource):
            self.state = dashboard.WebState(args)

    def run_ticks(self, actions):
        actions = iter(actions)

        def tick(_seconds):
            try:
                action = next(actions)
            except StopIteration:
                raise StopLoop
            action()

        with patch.object(dashboard.time, "sleep", tick):
            with self.assertRaises(StopLoop):
                self.state.loop()

    def test_stalled_stream_does_not_repeat_detector_confirmations(self):
        enqueue(self.state.src, 1., 151)
        self.run_ticks([lambda: None] * 4)
        self.assertEqual(len(self.state.h_score), 1)

    def test_dashboard_uses_configured_device_time_hop(self):
        enqueue(self.state.src, 1., 151)
        self.run_ticks([lambda: None,
                        lambda: enqueue(self.state.src, 4.04, 1),
                        lambda: enqueue(self.state.src, 4.12, 1)])
        self.assertEqual(len(self.state.h_score), 2)

    def test_calibration_expires_when_transmitter_is_offline(self):
        self.state.calibrating_until = 1.0
        self.run_ticks([lambda: None])
        self.assertIsNone(self.state.calibrating_until)
        self.assertFalse(Path(self.state.args.calib).exists())

    def test_hop_schedule_does_not_drift_with_ui_poll_interval(self):
        enqueue(self.state.src, 1., 151)
        self.run_ticks([lambda: None,
                        lambda: enqueue(self.state.src, 4.08, 1),
                        lambda: enqueue(self.state.src, 4.16, 1),
                        lambda: enqueue(self.state.src, 4.24, 1)])
        self.assertEqual(len(self.state.h_score), 3)

    def test_http_bind_failure_releases_source(self):
        with patch.object(sys, "argv", ["web_dashboard.py"]), \
             patch.object(dashboard, "WebState", return_value=self.state), \
             patch.object(dashboard, "ThreadingHTTPServer", side_effect=OSError("address in use")):
            with self.assertRaisesRegex(OSError, "address in use"):
                dashboard.main()
        self.assertTrue(self.state.src.stopped)

    def test_english_page_and_event_snapshot_preserve_signal_values(self):
        english = dashboard.dashboard_page()
        self.assertIn('<html lang="en">', english)
        self.assertIn("Wi-Fi CSI Motion Monitor", english)
        self.assertIn("No motion detected", english)
        english_state = self.state.snapshot(language="en")
        self.assertIn("Monitor started", english_state["events"][0])
        self.assertEqual(english_state["thr_on"], self.state.motion.cfg.thr_on)
        self.assertIn("Giám sát Chuyển động", dashboard.dashboard_page("vi"))


class RecordingTests(unittest.TestCase):
    def test_transmitter_loss_at_end_fails_recording_quality(self):
        now = [1000.0]

        class Source(IdleSource):
            def start(self):
                enqueue(self, 1., 2)
                items = [self.q.get_nowait(), self.q.get_nowait()]
                for index, (_ht, line, pkt) in enumerate(items):
                    self.q.put((1000.0 + index * .02, line, pkt))

        def sleep(seconds):
            now[0] += seconds

        tiny_spec = dict(record.EXPERIMENT_SPECS["e1"])
        tiny_spec["steps"] = [("still", 4., "test", "still")]
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(record.EXPERIMENT_SPECS, {"e1": tiny_spec}), \
             patch.object(record, "SerialSource", Source), \
             patch.object(record, "check_port_available", return_value=(True, "COM4")), \
             patch.object(record, "play_cue"), \
             patch.object(record.time, "time", side_effect=lambda: now[0]), \
             patch.object(record.time, "sleep", side_effect=sleep):
            self.assertFalse(record.run_protocol("e1", "COM4", 115200, tmp))
            meta = json.loads(next(Path(tmp).rglob("*.json")).read_text(encoding="utf-8"))
            self.assertGreater(meta["qc"]["max_gap_s"], 3.9)

    def test_empty_room_duration_must_be_finite_and_positive(self):
        for duration in (0., -1., float("nan"), float("inf")):
            with self.subTest(duration=duration), \
                 patch.object(record, "check_port_available", return_value=(False, "unavailable")):
                with self.assertRaises(ValueError):
                    record.run_protocol("e4", "COM4", 115200, ".", empty_minutes=duration)

    def test_record_creation_failure_releases_source(self):
        sources = []

        class Source(IdleSource):
            def start(self):
                sources.append(self)
                enqueue(self, 1., 1)

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(record, "SerialSource", Source), \
             patch.object(record, "Recorder", side_effect=OSError("disk unavailable")), \
             patch.object(record, "check_port_available", return_value=(True, "COM4")):
            with self.assertRaisesRegex(OSError, "disk unavailable"):
                record.run_protocol("e1", "COM4", 115200, tmp)
        self.assertTrue(sources[0].stopped)

    def test_unavailable_port_is_reported_as_failure(self):
        with patch("serial.tools.list_ports.comports", return_value=[]), \
             patch("serial.Serial", side_effect=OSError("port not found")):
            ok, _message = record.check_port_available("COM404")
        self.assertFalse(ok)

    def test_preflight_checks_requested_baud(self):
        calls = []

        def open_port(port, baud, **kwargs):
            calls.append((port, baud))
            return SimpleNamespace(close=lambda: None)

        with patch("serial.tools.list_ports.comports", return_value=[]), \
             patch("serial.Serial", open_port):
            record.check_port_available("COM4", 230400)
        self.assertEqual(calls, [("COM4", 230400)])

    def test_write_errors_are_not_swallowed_as_empty_queue(self):
        class Source(IdleSource):
            def start(self):
                enqueue(self, 1., 2)

        class DiskFullRecorder(record.Recorder):
            def write(self, host_t, line):
                raise OSError("disk full")

        tiny_spec = dict(record.EXPERIMENT_SPECS["e1"])
        tiny_spec["steps"] = [("still", .05, "test", "still")]
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(record.EXPERIMENT_SPECS, {"e1": tiny_spec}), \
             patch.object(record, "SerialSource", Source), \
             patch.object(record, "Recorder", DiskFullRecorder), \
             patch.object(record, "check_port_available", return_value=(True, "COM4")), \
             patch.object(record, "play_cue"):
            with self.assertRaisesRegex(OSError, "disk full"):
                record.run_protocol("e1", "COM4", 115200, tmp)


@unittest.skipUnless(sys.platform == "win32", "Windows batch launcher regression")
class LauncherTests(unittest.TestCase):
    def test_failed_idf_setup_stops_before_build_or_flash(self):
        project = Path(__file__).resolve().parents[1]
        for board in ("rx", "tx"):
            with self.subTest(board=board), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "esp-idf").mkdir()
                (root / "Python311").mkdir()
                (root / "esp-idf" / "export.bat").write_text("@exit /b 7\n")
                (root / "Python311" / "idf.py.bat").write_text("@echo BUILD_WAS_RUN\n@exit /b 0\n")
                source = (project / "scripts" / f"build_and_flash_{board}.bat").read_text()
                # Redirect only the installed-tool directory in this executable
                # fixture; the launcher control flow is the production script.
                script = root / "launcher.bat"
                script.write_text(source.replace("E:\\WifiSensingTools", str(root)))
                result = subprocess.run(["cmd.exe", "/d", "/c", str(script), "COM404"],
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
                self.assertNotIn("BUILD_WAS_RUN", result.stdout)


if __name__ == "__main__":
    unittest.main()
