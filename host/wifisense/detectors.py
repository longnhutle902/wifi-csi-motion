"""Motion and fall detectors (shared by dashboard, offline evaluation)."""
from __future__ import annotations

import json
import os
from collections import deque
from dataclasses import dataclass, asdict, fields

import numpy as np

from . import dsp


# --------------------------------------------------------------------------
# Motion detection: calibrated threshold + hysteresis + temporal smoothing
# --------------------------------------------------------------------------

@dataclass
class MotionConfig:
    win_s: float = 1.2        # sliding window length (seconds)
    hop_s: float = 0.1        # evaluation interval (seconds)
    k_on: float = 6.5         # thr_on = median + max(k_on * std, prop_margin)
    k_off: float = 3.8        # hysteresis release factor
    min_margin: float = 0.035 # dB, minimum base margin
    n_on: int = 3             # consecutive hops above thr_on to confirm MOTION
    n_off: int = 8            # consecutive hops below thr_off to return to STILL
    baseline_median: float = 0.126
    baseline_std: float = 0.0095
    calibrated: bool = True
    sensitivity: str = "normal"   # "high" | "normal" | "low"

    @property
    def thr_on(self) -> float:
        sens = "low" if self.sensitivity == "strict" else self.sensitivity
        scale = {"high": 0.74, "normal": 1.0, "low": 1.35}.get(sens, 1.0)
        prop_margin = max(self.min_margin * 1.6, self.baseline_median * 0.28) * scale
        stat_margin = (self.k_on * scale) * self.baseline_std
        return self.baseline_median + max(stat_margin, prop_margin)

    @property
    def thr_off(self) -> float:
        sens = "low" if self.sensitivity == "strict" else self.sensitivity
        scale = {"high": 0.76, "normal": 1.0, "low": 1.30}.get(sens, 1.0)
        prop_margin = max(self.min_margin * 0.9, self.baseline_median * 0.15) * scale
        stat_margin = (self.k_off * scale) * self.baseline_std
        return self.baseline_median + max(stat_margin, prop_margin)

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "MotionConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("sensitivity") == "strict":
            data["sensitivity"] = "low"
        valid = {fld.name for fld in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid}
        return cls(**filtered)


class MotionDetector:
    def __init__(self, cfg: MotionConfig | None = None, ml_model_path: str | None = None):
        self.cfg = cfg or MotionConfig()
        self.state = False
        self._above = 0
        self._below = 0
        self._score_hist: deque[float] = deque(maxlen=3)
        self.last_smoothed_score: float = 0.0
        self.ml = None
        if ml_model_path and os.path.exists(ml_model_path):
            import joblib
            self.ml = joblib.load(ml_model_path)

    def calibrate(self, empty_scores: np.ndarray):
        s = np.asarray(empty_scores, dtype=np.float64)
        s = s[np.isfinite(s)]
        if len(s) == 0:
            return
        # Pass 1: initial robust median & MAD to reject accidental transient spikes
        med0 = float(np.median(s))
        mad0 = float(np.median(np.abs(s - med0)) * 1.4826)
        cutoff = med0 + max(3.8 * mad0, 0.05)
        s_clean = s[s <= cutoff]
        if len(s_clean) < max(5, int(0.7 * len(s))):
            s_clean = np.sort(s)[:max(5, int(0.85 * len(s)))]

        med = float(np.median(s_clean))
        mad = float(np.median(np.abs(s_clean - med)) * 1.4826)
        iqr_std = float((np.percentile(s_clean, 75) - np.percentile(s_clean, 25)) / 1.349)
        p96 = float(np.percentile(s_clean, 96))
        std = max(mad, iqr_std, (p96 - med) / 2.6, 0.004)

        self.cfg.baseline_median = med
        self.cfg.baseline_std = std
        self.cfg.calibrated = True
        self.reset()

    def reset(self):
        self.state = False
        self._above = self._below = 0
        self._score_hist.clear()
        self.last_smoothed_score = 0.0

    def smooth_score(self, score: float) -> float:
        self._score_hist.append(float(score))
        if len(self._score_hist) < 3:
            self.last_smoothed_score = float(np.mean(self._score_hist))
        else:
            arr = np.asarray(self._score_hist, dtype=np.float64)
            self.last_smoothed_score = float(0.55 * np.median(arr) + 0.45 * np.mean(arr))
        return self.last_smoothed_score

    def raw_decision(self, score: float, feats: np.ndarray | None = None) -> bool:
        if self.ml is not None and feats is not None:
            return bool(self.ml.predict(feats[None, :])[0])
        if not self.cfg.calibrated:
            return False
        thr = self.cfg.thr_off if self.state else self.cfg.thr_on
        return score > thr

    def update(self, score: float, feats: np.ndarray | None = None) -> bool:
        s_val = self.smooth_score(score)
        hit = self.raw_decision(s_val, feats)
        if hit:
            strong_thr = self.cfg.thr_on + 2.2 * max(self.cfg.baseline_std, 0.015)
            step = 2 if (not self.state and s_val > strong_thr) else 1
            self._above += step
            self._below = 0
        else:
            self._below += 1
            self._above = 0
        sens = "low" if self.cfg.sensitivity == "strict" else self.cfg.sensitivity
        req_on = {"high": 2, "normal": self.cfg.n_on, "low": self.cfg.n_on + 1}.get(
            sens, self.cfg.n_on
        )
        if not self.state and self._above >= req_on:
            self.state = True
        elif self.state and self._below >= self.cfg.n_off:
            self.state = False
        return self.state


# --------------------------------------------------------------------------
# Fall detection: ONNX model + post-event stillness confirmation
# --------------------------------------------------------------------------

@dataclass
class FallConfig:
    model_path: str = ""
    win_s: float = 2.0
    threshold: float | None = None    # None -> value stored with the model
    confirm_s: float = 3.0           # look at this period after the candidate
    still_ratio: float = 0.6          # fraction of hops that must be "quiet"
    use_confirmation: bool = True
    cooldown_s: float = 10.0
    smooth_n: int = 3


class FallDetector:
    """Runs the fall classifier on the latest window while motion is present.

    A *candidate* is raised when the smoothed probability exceeds the
    threshold.  If confirmation is enabled, the alert is only issued if the
    following ``confirm_s`` seconds are mostly quiet (the person stays down);
    otherwise the candidate is discarded (sitting down, jumping, ...).
    """

    def __init__(self, cfg: FallConfig):
        self.cfg = cfg
        self.sess = None
        self.meta = {}
        if cfg.model_path and os.path.exists(cfg.model_path):
            import onnxruntime as ort
            self.sess = ort.InferenceSession(cfg.model_path, providers=["CPUExecutionProvider"])
            self.input_name = self.sess.get_inputs()[0].name
            meta_path = os.path.splitext(cfg.model_path)[0] + ".json"
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    self.meta = json.load(f)
                self.cfg.win_s = float(self.meta.get("win_s", cfg.win_s))
                if cfg.threshold is None and "threshold" in self.meta:
                    self.cfg.threshold = float(self.meta["threshold"])
        if self.cfg.threshold is None:
            self.cfg.threshold = 0.6
        self._hist: list[float] = []
        self._candidate_t: float | None = None
        self._quiet: list[bool] = []
        self._last_alert = -1e9
        self.last_prob = 0.0

    @property
    def available(self) -> bool:
        return self.sess is not None

    def predict_proba(self, win: np.ndarray) -> float:
        """win: preprocessed (T,S) window of length win_s*FS."""
        if self.sess is None:
            return 0.0
        x = dsp.model_input(win)[None]
        out = self.sess.run(None, {self.input_name: x})[0]
        out = np.asarray(out).reshape(-1)
        if out.size == 1:  # logit
            return float(1.0 / (1.0 + np.exp(-out[0])))
        e = np.exp(out - out.max())
        p = e / e.sum()
        return float(p[1])

    def update(self, t: float, win: np.ndarray | None, motion: bool, quiet: bool) -> str | None:
        """Returns 'candidate', 'fall' or None."""
        p = self.predict_proba(win) if (win is not None and (motion or self._candidate_t is None)) else 0.0
        self._hist = (self._hist + [p])[-self.cfg.smooth_n:]
        self.last_prob = float(np.mean(self._hist))
        event = None
        if self._candidate_t is None:
            if (self.last_prob >= self.cfg.threshold and motion
                    and t - self._last_alert > self.cfg.cooldown_s):
                if not self.cfg.use_confirmation:
                    self._last_alert = t
                    return "fall"
                self._candidate_t = t
                self._quiet = []
                event = "candidate"
        else:
            # skip the first second after the candidate (end of the fall itself)
            if t - self._candidate_t > 1.0:
                self._quiet.append(quiet)
            if t - self._candidate_t >= self.cfg.confirm_s + 1.0:
                ratio = float(np.mean(self._quiet)) if self._quiet else 0.0
                self._candidate_t = None
                if ratio >= self.cfg.still_ratio:
                    self._last_alert = t
                    event = "fall"
        return event
