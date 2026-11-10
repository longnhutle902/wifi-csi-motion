import base64
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'host'))
from wifisense.csi_io import CsiPacket, parse_line
from wifisense.detectors import MotionDetector
from wifisense.pipeline import Engine, ReplaySource


class PipelineTests(unittest.TestCase):
    def test_declared_csi_length_must_match_payload(self):
        payload = base64.b64encode(bytes(128)).decode()
        self.assertIsNone(parse_line('CSI,0,1,100,-60,-95,11,1,0,0,11,0,256,' + payload))

    def test_reboot_clears_motion_and_previous_result(self):
        engine = Engine(MotionDetector())
        def packet(ts):
            return CsiPacket(0, 0, ts, -60, 0, 0, 0, 0, 0, 11, 0, np.ones(52))
        engine.push(packet(10_000_000))
        engine.motion.state = True
        engine.last_result = {'motion': True}
        engine.push(packet(0))
        self.assertFalse(engine.motion.state)
        self.assertEqual(engine.last_result, {})

    def test_reset_clears_packet_count(self):
        engine = Engine(MotionDetector())
        engine.n_packets = 10
        engine.reset()
        self.assertEqual(engine.n_packets, 0)

    def test_replay_speed_must_be_positive(self):
        for speed in (0, -1, float('nan')):
            with self.assertRaises(ValueError):
                ReplaySource('unused.csv', speed=speed)

    def test_replay_stop_interrupts_long_delay(self):
        payload = base64.b64encode(bytes(128)).decode()
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'session.csv')
            with open(path, 'w') as stream:
                for t in (0, 60):
                    stream.write(f'{t},still,CSI,0,1,{t*1000000},-60,-95,11,1,0,0,11,0,128,{payload}\n')
            source = ReplaySource(path)
            source.start()
            source.q.get(timeout=2)
            source.stop()
            source.join(timeout=1)
            self.assertFalse(source.is_alive())


if __name__ == '__main__':
    unittest.main()
