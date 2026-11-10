"""Signal processing shared by the real-time pipeline and model training.

All functions work on CSI *amplitude* matrices shaped (T, S) where T is time
(uniformly sampled, default 100 Hz) and S the number of subcarriers (52).
The same code is used on the PC and in the Colab notebook so that features
are identical between training and deployment.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy.ndimage import median_filter, uniform_filter1d
from scipy.signal import butter, sosfiltfilt

FS = 100.0          # target sampling rate (Hz)
N_SUB = 52


# --------------------------------------------------------------------------
# Resampling / cleaning
# --------------------------------------------------------------------------

def resample_uniform(t: np.ndarray, x: np.ndarray, fs: float = FS,
                     max_gap: float = 0.5):
    """Linearly resample irregular samples x(t) (T,S) to a uniform grid.

    Returns (t_uniform, x_uniform, valid_mask).  Samples that fall into gaps
    longer than ``max_gap`` seconds are flagged invalid.
    """
    t = np.asarray(t, dtype=np.float64)
    order = np.argsort(t, kind="stable")
    t, x = t[order], x[order]
    keep = np.r_[True, np.diff(t) > 0]
    t, x = t[keep], x[keep]
    if len(t) < 2:
        return t, x, np.ones(len(t), bool)
    tu = np.arange(t[0], t[-1], 1.0 / fs)
    xu = np.empty((len(tu), x.shape[1]), dtype=np.float32)
    for s in range(x.shape[1]):
        xu[:, s] = np.interp(tu, t, x[:, s])
    idx = np.searchsorted(t, tu)
    idx = np.clip(idx, 1, len(t) - 1)
    gap = t[idx] - t[idx - 1]
    return tu, xu, gap <= max_gap


def hampel(x: np.ndarray, k: int = 9, n_sigma: float = 2.5) -> np.ndarray:
    """Hampel outlier filter along time for each subcarrier."""
    med = median_filter(x, size=(k, 1), mode="nearest")
    mad = median_filter(np.abs(x - med), size=(k, 1), mode="nearest") * 1.4826
    out = x.copy()
    bad = np.abs(x - med) > n_sigma * (mad + 1e-6)
    out[bad] = med[bad]
    return out


@lru_cache(maxsize=8)
def _butter_sos(cutoff: float, fs: float, order: int):
    return butter(order, cutoff / (fs / 2.0), btype="low", output="sos")


def lowpass(x: np.ndarray, cutoff: float = 6.0, fs: float = FS, order: int = 4) -> np.ndarray:
    if len(x) < 3 * (order + 1) * 2:
        return x
    sos = _butter_sos(float(cutoff), float(fs), int(order))
    return sosfiltfilt(sos, x, axis=0).astype(np.float32)


def gain_normalize(amp: np.ndarray) -> np.ndarray:
    """Log-amplitude (dB) minus per-frame mean across subcarriers.

    Removes the automatic-gain-control (AGC) jumps of the ESP32 receiver, which
    scale all subcarriers of one packet by the same factor. Uses +2.0 offset to
    dampen quantization noise on deep-null subcarriers.
    """
    db = 20.0 * np.log10(np.maximum(amp, 1e-3) + 2.0)
    return (db - db.mean(axis=1, keepdims=True)).astype(np.float32)


def preprocess(amp: np.ndarray, fs: float = FS) -> np.ndarray:
    """Full cleaning chain for uniformly sampled amplitude (T,S)."""
    x = hampel(amp.astype(np.float32), k=9, n_sigma=2.5)
    x = gain_normalize(x)
    x = lowpass(x, 6.0, fs)
    return x


# --------------------------------------------------------------------------
# Motion features (computed on preprocessed data)
# --------------------------------------------------------------------------

def motion_score(win: np.ndarray) -> float:
    """Robust temporal variation (dB) across subcarriers in a preprocessed window.

    Combines standard deviation and MAD per subcarrier, then takes the trimmed
    mean (15th to 90th percentile across the 52 subcarriers) so dead nulls or
    isolated noisy edge subcarriers do not cause false spikes.
    """
    std_s = np.std(win, axis=0)
    med_t = np.median(win, axis=0, keepdims=True)
    mad_s = np.median(np.abs(win - med_t), axis=0) * 1.4826
    comb = 0.5 * std_s + 0.5 * mad_s
    q_low, q_high = np.percentile(comb, [15, 90])
    sel = comb[(comb >= q_low) & (comb <= q_high)]
    return float(np.mean(sel)) if len(sel) else float(np.mean(comb))


def motion_score_series(x: np.ndarray, win: int = 100, hop: int = 10):
    """Sliding motion score. Returns (centres_idx, scores)."""
    centres, scores = [], []
    for s in range(0, len(x) - win + 1, hop):
        scores.append(motion_score(x[s:s + win]))
        centres.append(s + win)  # causal: score refers to window end
    return np.array(centres), np.array(scores)


def window_features(win: np.ndarray) -> np.ndarray:
    """Hand-crafted features of one preprocessed window (for classic ML).

    Robust to environment: they describe *how much and how fast* the channel
    changes, not its static shape.
    """
    d = np.diff(win, axis=0)
    std_t = np.std(win, axis=0)
    # principal component of the dynamic part
    xc = win - win.mean(axis=0)
    try:
        u, s, _ = np.linalg.svd(xc, full_matrices=False)
        pc1 = u[:, 0] * s[0]
        ev = s ** 2 / (np.sum(s ** 2) + 1e-9)
        ev1 = ev[0]
    except np.linalg.LinAlgError:
        pc1 = xc.mean(axis=1)
        ev1 = 0.0
    spec = np.abs(np.fft.rfft(pc1 - pc1.mean()))
    freqs = np.fft.rfftfreq(len(pc1), 1.0 / FS)
    p = spec ** 2
    ptot = p.sum() + 1e-9
    bands = [(0.3, 2), (2, 5), (5, 10), (10, 20)]
    band_p = [p[(freqs >= a) & (freqs < b)].sum() / ptot for a, b in bands]
    centroid = float((freqs * p).sum() / ptot)
    # adjacent-frame correlation ("wander")
    a, b = xc[:-1], xc[1:]
    num = (a * b).sum(1)
    den = np.sqrt((a * a).sum(1) * (b * b).sum(1)) + 1e-9
    corr = num / den
    return np.array([
        std_t.mean(), np.median(std_t), std_t.max(), np.percentile(std_t, 90),
        np.abs(d).mean(), np.abs(d).max(), d.std(),
        np.std(pc1), ev1, centroid, *band_p,
        1.0 - np.median(corr), np.ptp(win.mean(axis=1)),
    ], dtype=np.float32)


FEATURE_NAMES = [
    "std_mean", "std_median", "std_max", "std_p90",
    "diff_absmean", "diff_absmax", "diff_std",
    "pc1_std", "pc1_ev", "spec_centroid", "band_0.3_2", "band_2_5", "band_5_10", "band_10_20",
    "wander", "frame_mean_ptp",
]


# --------------------------------------------------------------------------
# Deep-model input (fall detection)
# --------------------------------------------------------------------------

def model_input(win: np.ndarray) -> np.ndarray:
    """Preprocessed window (T,S) -> normalized model tensor (2,T,S) float32.

    channel 0: dynamic part (window mean removed) scaled by robust std
    channel 1: first temporal difference, same scale
    Instance normalisation makes the input independent of the absolute
    multipath profile of a room, which is the main cross-domain shift.
    """
    xc = win - win.mean(axis=0, keepdims=True)
    scale = np.std(xc) + 1e-3
    c0 = xc / scale
    c1 = np.vstack([np.zeros((1, win.shape[1]), np.float32), np.diff(win, axis=0)]) / scale
    return np.stack([c0, c1]).astype(np.float32)


def smooth(x: np.ndarray, n: int) -> np.ndarray:
    return uniform_filter1d(x, size=max(1, n), mode="nearest")
