"""Parsing of the CSI text stream produced by firmware/csi_rx and session I/O."""
from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass, field

import numpy as np

# ESP32-S3, HT20, L-LTF only: buffer = 64 subcarriers x [imag, real] int8.
# Buffer order: subcarrier 0..31 then -32..-1.  Valid L-LTF data/pilot
# subcarriers are -26..-1 and 1..26 -> 52 subcarriers, ordered low->high.
LLTF_INDEX = np.r_[38:64, 1:27]
N_SUB = 52


@dataclass
class CsiPacket:
    idx: int
    rx_seq: int
    ts_us: int
    rssi: int
    noise_floor: int
    rate: int
    sig_mode: int
    mcs: int
    cwb: int
    channel: int
    fwi: int
    csi: np.ndarray  # complex64 (52,)


def decode_buffer(raw: bytes) -> np.ndarray:
    """int8 [imag, real] pairs -> complex64 vector of the 52 valid subcarriers."""
    a = np.frombuffer(raw, dtype=np.int8).astype(np.float32)
    n = len(a) // 2
    a = a[: 2 * n].reshape(n, 2)
    c = a[:, 1] + 1j * a[:, 0]
    if n >= 64:
        c = c[:64][LLTF_INDEX]
    else:  # unexpected length: pad
        c = np.pad(c, (0, N_SUB - min(n, N_SUB)))[:N_SUB]
    return c.astype(np.complex64)


def parse_line(line: str) -> CsiPacket | None:
    if not line.startswith("CSI,"):
        return None
    parts = line.strip().split(",")
    if len(parts) != 14:
        return None
    try:
        v = [int(x) for x in parts[1:13]]
        raw = base64.b64decode(parts[13], validate=True)
    except (ValueError, binascii.Error):
        return None
    if len(raw) < 128 or len(raw) % 2 or len(raw) != v[11]:
        return None
    return CsiPacket(v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8], v[9], v[10],
                     decode_buffer(raw))


# --------------------------------------------------------------------------
# Session files: <name>.csv (one row per packet) + <name>.json (metadata)
# Row: host_time,label,<raw CSI line without newline>
# --------------------------------------------------------------------------

@dataclass
class Session:
    name: str
    meta: dict
    host_t: np.ndarray          # (N,) seconds (host clock)
    dev_t: np.ndarray           # (N,) seconds (ESP32 clock)
    rssi: np.ndarray            # (N,)
    csi: np.ndarray             # (N, 52) complex64
    labels: np.ndarray          # (N,) object/str
    extra: dict = field(default_factory=dict)

    @property
    def amp(self) -> np.ndarray:
        return np.abs(self.csi)


def load_session(path: str) -> Session:
    base = os.path.splitext(path)[0]
    meta = {}
    if os.path.exists(base + ".json"):
        with open(base + ".json", "r", encoding="utf-8") as f:
            meta = json.load(f)
    host_t, dev_t, rssi, csi, labels = [], [], [], [], []
    with open(base + ".csv", "r", encoding="utf-8", errors="ignore") as f:
        for row in f:
            p = row.rstrip("\n").split(",", 2)
            if len(p) < 3:
                continue
            pkt = parse_line(p[2])
            if pkt is None:
                continue
            host_t.append(float(p[0]))
            labels.append(p[1])
            dev_t.append(pkt.ts_us * 1e-6)
            rssi.append(pkt.rssi)
            csi.append(pkt.csi)
    if not csi:
        raise ValueError(f"No CSI packets in {path}")
    return Session(os.path.basename(base), meta, np.array(host_t), np.array(dev_t),
                   np.array(rssi, dtype=np.float32), np.stack(csi), np.array(labels, dtype=object))


def list_sessions(folder: str) -> list[str]:
    out = []
    for root, _, files in os.walk(folder):
        for fn in files:
            if fn.endswith(".csv"):
                out.append(os.path.join(root, fn))
    return sorted(out)
