"""Real-time pipeline: packet sources, recorder and processing engine."""
from __future__ import annotations

import json
import os
import queue
import threading
import time
from collections import deque

import numpy as np

from . import dsp
from .csi_io import CsiPacket, parse_line
from .detectors import FallDetector, MotionDetector


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------

class SerialSource(threading.Thread):
    """Reads the CSI stream from the RX board. Puts (host_t, raw_line, pkt)."""

    def __init__(self, port: str, baud: int = 921600):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self.ser = None
        self.q: queue.Queue = queue.Queue(maxsize=20000)
        self.running = True
        self.n_bad = 0
        self.last_stat = ""

    def run(self):
        import serial
        buf = b""
        opened_at = 0.0
        got_esp_traffic = False
        skip_until: dict[str, float] = {}

        while self.running:
            if self.ser is None or not self.ser.is_open:
                buf = b""
                now = time.time()
                usb_ports: list[str] = []
                other_ports: list[str] = []
                try:
                    import serial.tools.list_ports
                    for cp in serial.tools.list_ports.comports():
                        if cp.vid is not None:
                            usb_ports.append(cp.device)
                        else:
                            other_ports.append(cp.device)
                except Exception:
                    pass

                ordered = []
                for p in [self.port, *usb_ports, *other_ports]:
                    if p and p not in ordered and now >= skip_until.get(p, 0.0):
                        ordered.append(p)
                if not ordered and self.port:
                    ordered = [self.port]

                for port in ordered:
                    try:
                        self.ser = serial.Serial(port, self.baud, timeout=0.2)
                        self.port = port
                        self.last_stat = f"Connected {port}"
                        opened_at = time.time()
                        got_esp_traffic = False
                        break
                    except Exception as e:
                        self.last_stat = f"Waiting {port} ({type(e).__name__})"

                if self.ser is None or not self.ser.is_open:
                    time.sleep(0.5)
                    continue

            try:
                chunk = self.ser.read(self.ser.in_waiting or 1)
            except Exception:
                try:
                    self.ser.close()
                except Exception:
                    pass
                self.ser = None
                time.sleep(0.3)
                continue

            if not chunk:
                # Rotate away from silent non-ESP32 COM ports (e.g. COM1 / BT) if other ports exist
                if not got_esp_traffic and (time.time() - opened_at) > 3.5:
                    try:
                        import serial.tools.list_ports
                        all_ports = [cp.device for cp in serial.tools.list_ports.comports()]
                    except Exception:
                        all_ports = []
                    if len(all_ports) > 1:
                        skip_until[self.port] = time.time() + 6.0
                        try:
                            self.ser.close()
                        except Exception:
                            pass
                        self.ser = None
                continue

            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                line = raw.decode("ascii", errors="ignore").strip()
                if line.startswith("CSI,"):
                    got_esp_traffic = True
                    pkt = parse_line(line)
                    if pkt is None:
                        self.n_bad += 1
                        continue
                    try:
                        self.q.put_nowait((time.time(), line, pkt))
                    except queue.Full:
                        pass
                elif line.startswith("STAT,"):
                    got_esp_traffic = True
                    self.last_stat = line

    def stop(self):
        self.running = False
        try:
            self.ser.close()
        except Exception:
            pass


class ReplaySource(threading.Thread):
    """Replays a recorded session file in (scaled) real time."""

    def __init__(self, path: str, speed: float = 1.0, loop: bool = False):
        super().__init__(daemon=True)
        if not np.isfinite(speed) or speed <= 0:
            raise ValueError("Replay speed must be finite and positive")
        self.path = os.path.splitext(path)[0] + ".csv"
        self.speed = speed
        self.loop = loop
        self.q: queue.Queue = queue.Queue(maxsize=20000)
        self.running = True
        self.n_bad = 0
        self.last_stat = ""
        self.finished = False
        self._stop_event = threading.Event()

    def run(self):
        while self.running:
            t0_file = None
            t0_wall = time.time()
            with open(self.path, "r", encoding="utf-8", errors="ignore") as f:
                for row in f:
                    if not self.running:
                        return
                    p = row.rstrip("\n").split(",", 2)
                    if len(p) < 3:
                        continue
                    pkt = parse_line(p[2])
                    if pkt is None:
                        continue
                    th = float(p[0])
                    if t0_file is None:
                        t0_file = th
                    delay = (th - t0_file) / self.speed - (time.time() - t0_wall)
                    if delay > 0 and self._stop_event.wait(delay):
                        return
                    while self.running:
                        try:
                            self.q.put((time.time(), p[2], pkt), timeout=0.1)
                            break
                        except queue.Full:
                            continue
            if not self.loop:
                self.finished = True
                return

    def stop(self):
        self.running = False
        self._stop_event.set()


# --------------------------------------------------------------------------
# Recorder
# --------------------------------------------------------------------------

class Recorder:
    """Writes raw lines + current label to <out>.csv and metadata to <out>.json."""

    def __init__(self, path_no_ext: str, meta: dict):
        os.makedirs(os.path.dirname(path_no_ext) or ".", exist_ok=True)
        self.base = path_no_ext
        self.f = open(path_no_ext + ".csv", "w", encoding="utf-8", newline="\n")
        self.meta = dict(meta)
        self.meta.setdefault("segments", [])
        self.meta["start_time"] = time.time()
        self.label = "unlabeled"
        self._seg_start = time.time()
        self.n = 0

    def set_label(self, label: str):
        now = time.time()
        if label != self.label:
            self.meta["segments"].append([self.label, self._seg_start, now])
            self.label = label
            self._seg_start = now

    def write(self, host_t: float, line: str):
        self.f.write(f"{host_t:.4f},{self.label},{line}\n")
        self.n += 1

    def close(self):
        now = time.time()
        self.meta["segments"].append([self.label, self._seg_start, now])
        self.meta["end_time"] = now
        self.meta["n_packets"] = self.n
        self.f.close()
        with open(self.base + ".json", "w", encoding="utf-8") as f:
            json.dump(self.meta, f, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------

class Engine:
    """Keeps a packet buffer and computes motion / fall state every hop."""

    def __init__(self, motion: MotionDetector, fall: FallDetector | None = None,
                 buf_s: float = 6.0):
        self.motion = motion
        self.fall = fall
        self.buf_s = buf_s
        self.t = deque()
        self.amp = deque()
        self.rssi = deque()
        self.last_result: dict = {}
        self.n_packets = 0
        self.last_rx_walltime: float = 0.0

    def reset(self):
        self.t.clear()
        self.amp.clear()
        self.rssi.clear()
        self.last_result = {}
        self.last_rx_walltime = 0.0
        self.n_packets = 0
        self.motion.reset()

    def push(self, pkt: CsiPacket):
        t = pkt.ts_us * 1e-6
        if self.t and (t < self.t[-1] - 1.0 or t > self.t[-1] + 5.0):
            # Device reboot or large timestamp jump -> clear stale buffer
            self.reset()
        self.t.append(t)
        self.amp.append(np.abs(pkt.csi))
        self.rssi.append(pkt.rssi)
        self.n_packets += 1
        self.last_rx_walltime = time.time()
        while self.t and self.t[-1] - self.t[0] > self.buf_s:
            self.t.popleft(); self.amp.popleft(); self.rssi.popleft()

    @property
    def now(self) -> float:
        return self.t[-1] if self.t else 0.0

    def context(self, seconds: float):
        """Uniformly resampled + preprocessed last `seconds` of data."""
        if len(self.t) < 20:
            return None
        t = np.fromiter(self.t, dtype=np.float64)
        i0 = np.searchsorted(t, t[-1] - seconds - 0.5)
        t_seg = t[i0:]
        if len(t_seg) < 16 or (t_seg[-1] - t_seg[0]) < seconds * 0.75:
            return None
        amp = np.stack(list(self.amp)[i0:])
        tu, xu, valid = dsp.resample_uniform(t_seg, amp)
        if len(xu) < int(dsp.FS * 0.8) or float(np.mean(valid)) < 0.80:
            return None
        return dsp.preprocess(xu)

    def packet_rate(self) -> float:
        if len(self.t) < 2:
            return 0.0
        t = np.fromiter(self.t, dtype=np.float64)
        sel = t[t > t[-1] - 2.0]
        if len(sel) < 2:
            return 0.0
        return (len(sel) - 1) / max(sel[-1] - sel[0], 1e-3)

    def step(self) -> dict | None:
        mcfg = self.motion.cfg
        need = mcfg.win_s
        if self.fall is not None and self.fall.available:
            need = max(need, self.fall.cfg.win_s)
        x = self.context(need + 0.5)
        if x is None:
            return None
        nwin = int(mcfg.win_s * dsp.FS)
        win = x[-nwin:]
        raw_score = dsp.motion_score(win)
        feats = dsp.window_features(win) if self.motion.ml is not None else None
        state = self.motion.update(raw_score, feats)
        score = self.motion.last_smoothed_score
        quiet = score < mcfg.thr_off if mcfg.calibrated else False
        res = {
            "t": self.now, "score": score, "raw_score": raw_score,
            "motion": state, "quiet": quiet,
            "rate": self.packet_rate(), "rssi": float(np.mean(list(self.rssi)[-50:])),
            "fall_prob": 0.0, "fall_event": None, "latest_amp": self.amp[-1],
        }
        if self.fall is not None and self.fall.available:
            nf = int(self.fall.cfg.win_s * dsp.FS)
            fwin = x[-nf:] if len(x) >= nf else None
            ev = self.fall.update(self.now, fwin, state, quiet)
            res["fall_prob"] = self.fall.last_prob
            res["fall_event"] = ev
        self.last_result = res
        return res


def run_offline(session, motion: MotionDetector, fall: FallDetector | None = None,
                hop_s: float = 0.1, t_start: float | None = None,
                t_stop: float | None = None):
    """Runs the exact real-time logic on a recorded Session.

    Returns dict of arrays: t (device s), host_t, score, raw_score, motion,
    fall_prob, fall_event, label (ground truth at that time).
    """
    buf_s = 6.0 if fall is not None else max(motion.cfg.win_s + 1.2, 2.5)
    eng = Engine(motion, fall, buf_s=buf_s)
    out = {k: [] for k in ("t", "host_t", "score", "raw_score", "motion", "fall_prob", "fall_event", "label")}
    next_t = None
    for i in range(len(session.dev_t)):
        if t_stop is not None and session.host_t[i] > t_stop:
            break
        pkt = CsiPacket(i, 0, int(session.dev_t[i] * 1e6), int(session.rssi[i]), 0, 0, 0, 0, 0, 0, 0,
                        session.csi[i])
        eng.push(pkt)
        t = session.dev_t[i]
        if next_t is None:
            next_t = t + 1.0
        elif t < next_t - 5.0 or t > next_t + 5.0:
            next_t = t + hop_s
        if t >= next_t:
            while next_t <= t:
                next_t += hop_s
            if t_start is not None and session.host_t[i] < t_start:
                continue
            r = eng.step()
            if r is None:
                continue
            out["t"].append(t)
            out["host_t"].append(session.host_t[i])
            out["score"].append(r["score"])
            out["raw_score"].append(r["raw_score"])
            out["motion"].append(r["motion"])
            out["fall_prob"].append(r["fall_prob"])
            out["fall_event"].append(r["fall_event"] or "")
            out["label"].append(session.labels[i])
    return {k: np.array(v) for k, v in out.items()}


def scores_offline(session, win_s: float = 1.0, hop_s: float = 0.1):
    """Fast motion-score series of a whole session (used for calibration)."""
    tu, xu, valid = dsp.resample_uniform(session.dev_t, session.amp)
    x = dsp.preprocess(xu)
    win, hop = int(win_s * dsp.FS), int(hop_s * dsp.FS)
    idx, sc = dsp.motion_score_series(x, win, hop)
    host_tu = np.interp(tu, session.dev_t, session.host_t)
    lab_idx = np.searchsorted(session.host_t, host_tu[np.minimum(idx, len(tu) - 1)])
    lab_idx = np.clip(lab_idx, 0, len(session.labels) - 1)
    return host_tu[np.minimum(idx, len(tu) - 1)], sc, session.labels[lab_idx]
