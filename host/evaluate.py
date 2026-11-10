"""Chấm điểm tự động và xuất bảng kết quả + biểu đồ tiếng Việt cho báo cáo đồ án.

Chỉ đánh giá chức năng phân loại nhị phân của sản phẩm cuối:
    Có chuyển động (walk)  vs.  Trạng thái tĩnh (empty, still, fan_empty)

Chạy lệnh:
    python evaluate.py
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from wifisense.csi_io import list_sessions, load_session  # noqa: E402
from wifisense.detectors import MotionConfig, MotionDetector  # noqa: E402
from wifisense.pipeline import run_offline  # noqa: E402

POS_LABELS = {"walk", "motion"}
NEG_LABELS = {"empty", "still", "fan_empty"}
CALIB_LABELS = {"calib", "empty", "still"}
HOP = 0.1

EXP_TITLES_VI = {
    "E1": "TN1: Chuẩn 2.5–3m (Quạt tắt)",
    "E2a": "TN2a: Xa 4–5m / Đồ đạc",
    "E2b": "TN2b: Tường phía sau",
    "E3a": "TN3a: Quạt trần (Tĩnh)",
    "E3b": "TN3b: Quạt trần + Đi lại",
    "E4": "TN4: Phòng trống 15 phút",
}


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Tìm các đoạn liên tiếp có giá trị True -> danh sách (bắt_đầu, kết_thúc_không_gồm)."""
    m = np.r_[False, np.asarray(mask, dtype=bool), False]
    d = np.diff(m.astype(int))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def calibrate_causal_from_session(sess, motion: MotionDetector, calib_s: float = 30.0) -> float | None:
    """Lấy mức nền từ đoạn tĩnh đầu tiên của phiên bằng đúng bộ xử lý trượt thời gian thực."""
    probe = MotionDetector(MotionConfig())
    t_limit = float(sess.host_t[0] + calib_s + 40.0) if len(sess.host_t) else None
    pre = run_offline(sess, probe, None, HOP, None, t_stop=t_limit)
    if len(pre["host_t"]) < 30:
        return None
    ht = pre["host_t"]
    raw_sc = pre["raw_score"]
    lab = pre["label"]

    is_quiet = np.isin(lab, list(CALIB_LABELS))
    quiet_runs = runs(is_quiet)
    if not quiet_runs:
        return None

    # Chọn đoạn tĩnh đầu tiên đủ dài (>= 6 giây)
    chosen = None
    for s, e in quiet_runs:
        if (ht[e - 1] - ht[s]) >= 6.0:
            chosen = (s, e)
            break
    if chosen is None:
        return None

    s0, e0 = chosen
    t_block_start = float(ht[s0])
    t_block_end = float(ht[e0 - 1])
    t_settle = t_block_start + 2.0
    t_cal_end = min(t_settle + calib_s, t_block_end)
    if t_cal_end - t_settle < 4.0:
        return None

    sel = is_quiet & (ht >= t_settle) & (ht <= t_cal_end)
    if int(sel.sum()) < 15:
        return None

    motion.calibrate(raw_sc[sel])
    return t_cal_end


def compute_intuitive_metrics(res: dict, tol_hops: int = 30) -> dict:
    """Event overlap and nominal-hop static metrics, with an explicit release guard.

    A hit means an ON state overlaps a labelled movement event; this does not
    require a new OFF-to-ON transition. Durations count observed 0.1 s hops,
    rather than treating missing output intervals as observed static time.
    """
    lab = res["label"]
    pred = res["motion"].astype(bool)
    sc = res["score"]
    ht = np.asarray(res.get("host_t", np.arange(len(lab)) * HOP), dtype=float)

    valid = np.isin(lab, list(POS_LABELS | NEG_LABELS))
    gt_pos = np.isin(lab, list(POS_LABELS)) & valid
    gt_neg = np.isin(lab, list(NEG_LABELS)) & valid

    # 1. Đếm theo lượt đi lại (Event-level detection) & Thời gian phản hồi
    tp_ev = fn_ev = 0
    latencies: list[float] = []
    walk_peaks: list[float] = []
    for s, e in runs(gt_pos):
        if e - s < 5:  # bỏ qua đoạn cắt vụn < 0.5s nếu có
            continue
        walk_peaks.append(float(np.max(sc[s:e])))
        hit = np.where(pred[s:e])[0]
        if len(hit) > 0:
            tp_ev += 1
            latencies.append(float(ht[s + hit[0]] - ht[s]))
        else:
            fn_ev += 1

    # 2. Đếm số lần báo nhầm trong vùng tĩnh (bỏ qua 3.0s đuôi nhả ngay sau khi vừa đi xong)
    pos_guard = gt_pos.copy()
    for s, e in runs(gt_pos):
        pos_guard[e:min(len(pos_guard), e + tol_hops)] = True

    fp_ev = 0
    fp_fan_off = 0
    fp_fan_on = 0
    fp_still = 0
    neg_eval_mask = gt_neg & (~pos_guard)
    # Clip predictions to evaluated negatives before counting. A long ON run
    # may start during motion/guard/unlabelled time and still be wrong later.
    fp_mask = pred & neg_eval_mask
    for s, e in runs(fp_mask):
        fp_ev += 1
        seg_labs = set(lab[s:e])
        if "fan_empty" in seg_labs:
            fp_fan_on += 1
        elif "empty" in seg_labs:
            fp_fan_off += 1
        else:
            fp_still += 1

    neg_seconds = float(neg_eval_mask.sum() * HOP)
    neg_minutes = neg_seconds / 60.0
    fp_seconds = float(fp_mask.sum() * HOP)
    fp_time_pct = (100.0 * fp_seconds / neg_seconds) if neg_seconds > 0 else float("nan")
    static_acc_pct = 100.0 - fp_time_pct
    fp_per_min = (fp_ev / neg_minutes) if neg_minutes > 0 else float("nan")

    empty_minutes = float(((lab == "empty") & (~pos_guard)).sum() * HOP / 60.0)
    fan_empty_minutes = float(((lab == "fan_empty") & (~pos_guard)).sum() * HOP / 60.0)
    still_minutes = float(((lab == "still") & (~pos_guard)).sum() * HOP / 60.0)

    # 3. Mức dao động tín hiệu trung bình & đỉnh (dB) + Tỉ lệ Đi lại / Tĩnh
    walk_db = float(np.mean(sc[gt_pos])) if gt_pos.any() else float("nan")
    walk_peak_db = float(np.mean(walk_peaks)) if walk_peaks else float("nan")
    quiet_db = float(np.mean(sc[neg_eval_mask])) if neg_eval_mask.any() else float("nan")
    empty_db = float(np.mean(sc[(lab == "empty") & (~pos_guard)])) if ((lab == "empty") & (~pos_guard)).any() else float("nan")
    fan_empty_db = float(np.mean(sc[(lab == "fan_empty") & (~pos_guard)])) if ((lab == "fan_empty") & (~pos_guard)).any() else float("nan")

    ratio_mean_x = (walk_db / quiet_db) if (np.isfinite(walk_db) and np.isfinite(quiet_db) and quiet_db > 0) else float("nan")
    ratio_peak_x = (walk_peak_db / quiet_db) if (np.isfinite(walk_peak_db) and np.isfinite(quiet_db) and quiet_db > 0) else float("nan")

    total_walk = tp_ev + fn_ev
    detect_pct = (100.0 * tp_ev / total_walk) if total_walk > 0 else float("nan")
    lat_each_str = ", ".join(f"{v:.1f}s" for v in latencies)

    return {
        "walk_total": total_walk,
        "walk_tp": tp_ev,
        "walk_fn": fn_ev,
        "detect_pct": detect_pct,
        "fp_total": fp_ev,
        "fp_empty": fp_fan_off,
        "fp_fan_empty": fp_fan_on,
        "fp_still": fp_still,
        "neg_seconds": round(neg_seconds, 1),
        "neg_minutes": round(neg_minutes, 2),
        "fp_seconds": round(fp_seconds, 1),
        "fp_time_pct": round(fp_time_pct, 2),
        "static_acc_pct": round(static_acc_pct, 2),
        "fp_per_min": round(fp_per_min, 2),
        "empty_minutes": round(empty_minutes, 2),
        "fan_empty_minutes": round(fan_empty_minutes, 2),
        "still_minutes": round(still_minutes, 2),
        "lat_mean_s": float(np.mean(latencies)) if latencies else float("nan"),
        "lat_std_s": float(np.std(latencies)) if latencies else float("nan"),
        "lat_min_s": float(np.min(latencies)) if latencies else float("nan"),
        "lat_max_s": float(np.max(latencies)) if latencies else float("nan"),
        "lat_each": lat_each_str,
        "latencies_s": latencies,
        "walk_db": walk_db,
        "walk_peak_db": walk_peak_db,
        "quiet_db": quiet_db,
        "empty_db": empty_db,
        "fan_empty_db": fan_empty_db,
        "ratio_mean_x": ratio_mean_x,
        "ratio_peak_x": ratio_peak_x,
    }


def _setup_vn_matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Segoe UI", "Arial", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def plot_session_vi(title: str, res: dict, motion: MotionDetector, out_png: str):
    plt = _setup_vn_matplotlib()
    t = res["host_t"] - res["host_t"][0]
    sc = res["score"]
    lab = res["label"]
    pred = res["motion"].astype(bool)

    fig, ax = plt.subplots(1, 1, figsize=(12.5, 4.4), dpi=160)
    fig.patch.set_facecolor("#FFFFFF")

    gt_walk = np.isin(lab, list(POS_LABELS))
    gt_fan = lab == "fan_empty"

    first_walk = True
    for s, e in runs(gt_walk):
        ax.axvspan(t[s], t[min(e, len(t) - 1)], color="#DCFCE7", alpha=0.85,
                   label="Thực tế: Có người đi lại" if first_walk else None)
        first_walk = False

    first_fan = True
    for s, e in runs(gt_fan):
        ax.axvspan(t[s], t[min(e, len(t) - 1)], color="#FEF3C7", alpha=0.65,
                   label="Thực tế: Bật quạt trần tối đa (tĩnh)" if first_fan else None)
        first_fan = False

    ax.plot(t, sc, color="#1D4ED8", lw=1.25, label="Độ biến thiên CSI (dB)")

    ymax = max(float(sc.max()) * 1.18 if len(sc) else 0.5, motion.cfg.thr_on * 1.6, 0.35)
    ax.fill_between(
        t, 0, ymax, where=pred, color="#F97316", alpha=0.18, step="post",
        label="Hệ thống báo: Có chuyển động",
    )

    if motion.cfg.calibrated:
        ax.axhline(motion.cfg.thr_on, color="#DC2626", ls="--", lw=1.3,
                   label=f"Ngưỡng kích hoạt ({motion.cfg.thr_on:.3f} dB)")
        ax.axhline(motion.cfg.thr_off, color="#64748B", ls=":", lw=1.1,
                   label=f"Ngưỡng duy trì ({motion.cfg.thr_off:.3f} dB)")

    ax.set_xlim(0, float(t[-1]) if len(t) else 1.0)
    ax.set_ylim(0, ymax)
    ax.set_xlabel("Thời gian đánh giá (giây)", fontsize=10, fontweight="bold")
    ax.set_ylabel("Độ biến thiên CSI (dB)", fontsize=10, fontweight="bold")
    ax.set_title(title, fontsize=11.5, fontweight="bold", pad=10)
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="upper right", fontsize=8.5, ncol=2, frameon=True, facecolor="#F8FAFC")

    fig.tight_layout()
    fig.savefig(out_png, dpi=170)
    plt.close(fig)


def plot_slide_geometry_comparison(by_exp: dict[str, dict], out_png: str):
    """Hình 2: So sánh mức dao động tín hiệu & tỉ lệ phát hiện giữa E1, E2a, E2b, E4."""
    order = [k for k in ("E1", "E2a", "E2b", "E4") if k in by_exp]
    if not order:
        return
    plt = _setup_vn_matplotlib()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.8, 4.8), dpi=160)
    fig.patch.set_facecolor("#FFFFFF")

    short_names = {
        "E1": "TN1: Chuẩn\n(2.5–3m)",
        "E2a": "TN2a: Xa 4–5m\n/ Đồ đạc",
        "E2b": "TN2b: Tường\nphía sau",
        "E4": "TN4: Phòng trống\n(15 phút)",
    }
    x = np.arange(len(order))
    w = 0.34
    quiet_vals = [by_exp[k]["quiet_db"] if np.isfinite(by_exp[k]["quiet_db"]) else 0.0 for k in order]
    walk_vals = [by_exp[k]["walk_db"] if np.isfinite(by_exp[k]["walk_db"]) else 0.0 for k in order]
    peak_vals = [by_exp[k].get("walk_peak_db", float("nan")) for k in order]

    b1 = ax1.bar(x - w / 2, quiet_vals, width=w, color="#94A3B8", edgecolor="#475569",
                 label="Trạng thái Tĩnh (Ngồi yên / Phòng trống)")
    b2 = ax1.bar(x + w / 2, walk_vals, width=w, color="#2563EB", edgecolor="#1E3A8A",
                 label="Khi đi lại — Mức TB (dB)")
    valid_pk_x = [xi + w / 2 for xi, pv in zip(x, peak_vals) if np.isfinite(pv) and pv > 0]
    valid_pk_y = [pv for pv in peak_vals if np.isfinite(pv) and pv > 0]
    if valid_pk_y:
        ax1.scatter(valid_pk_x, valid_pk_y, color="#0F172A", s=34, zorder=4, label="Khi đi lại — Đỉnh TB (dB)")
        for px, py in zip(valid_pk_x, valid_pk_y):
            ax1.text(px, py + 0.015, f"Đỉnh: {py:.2f}", ha="center", va="bottom",
                     fontsize=7.8, fontweight="bold", color="#0F172A")

    thr_mean = float(np.nanmean([by_exp[k]["thr_on"] for k in order]))
    ax1.axhline(thr_mean, color="#DC2626", ls="--", lw=1.3, label=f"Ngưỡng kích hoạt TB ({thr_mean:.2f} dB)")

    ax1.set_xticks(x)
    ax1.set_xticklabels([short_names.get(k, k) for k in order], fontsize=9.5, fontweight="bold")
    ax1.set_ylabel("Độ biến thiên CSI (dB)", fontsize=10, fontweight="bold")
    ax1.set_title("A. So sánh mức dao động tín hiệu (dB)", fontsize=11, fontweight="bold", pad=10)
    top_y = max(walk_vals + quiet_vals + (valid_pk_y if valid_pk_y else [0.4]))
    ax1.set_ylim(0, max(top_y * 1.40, 0.55))
    ax1.grid(axis="y", ls="--", alpha=0.35)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.legend(loc="upper left", ncol=2, fontsize=7.8, frameon=True, facecolor="#F8FAFC")

    for rect in list(b1) + list(b2):
        h = rect.get_height()
        if h > 0.005:
            ax1.text(rect.get_x() + rect.get_width() / 2, h + 0.010, f"{h:.2f}",
                     ha="center", va="bottom", fontsize=8.0, fontweight="bold", color="#1E3A8A")

    walk_keys = [k for k in ("E1", "E2a", "E2b") if k in by_exp and by_exp[k]["walk_total"] > 0]
    if walk_keys:
        xw = np.arange(len(walk_keys))
        pcts = [by_exp[k]["detect_pct"] for k in walk_keys]
        bars = ax2.bar(xw, pcts, width=0.5, color=["#0D9488", "#2563EB", "#7C3AED"][:len(walk_keys)],
                       edgecolor="#0F172A", alpha=0.9)
        ax2.set_xticks(xw)
        ax2.set_xticklabels([short_names.get(k, k) for k in walk_keys], fontsize=9.5, fontweight="bold")
        ax2.set_ylim(0, 115)
        ax2.set_ylabel("Tỉ lệ phát hiện đúng theo lượt (%)", fontsize=10, fontweight="bold")
        ax2.set_title("B. Tỉ lệ phát hiện & Thời gian phản hồi", fontsize=11, fontweight="bold", pad=10)
        ax2.grid(axis="y", ls="--", alpha=0.35)
        ax2.spines["top"].set_visible(False)
        ax2.spines["right"].set_visible(False)
        for rect, k in zip(bars, walk_keys):
            d = by_exp[k]
            lat_txt = f"\n(Trễ TB: {d['lat_mean_s']:.2f}s)" if np.isfinite(d["lat_mean_s"]) else ""
            ax2.text(
                rect.get_x() + rect.get_width() / 2, rect.get_height() + 2.0,
                f"{d['walk_tp']}/{d['walk_total']} lượt ({d['detect_pct']:.0f}%){lat_txt}",
                ha="center", va="bottom", fontsize=8.5, fontweight="bold",
            )
    else:
        ax2.axis("off")

    fig.suptitle("Ảnh hưởng của Khoảng cách, Vật cản và Tường chắn trong Phòng Thử nghiệm",
                 fontsize=12.5, fontweight="bold", y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out_png, dpi=180)
    plt.close(fig)


def plot_slide_ceiling_fan(by_exp: dict[str, dict], out_png: str):
    """Hình 3: Đối chứng khả năng chống nhiễu Quạt trần (E3a + E3b)."""
    if "E3a" not in by_exp and "E3b" not in by_exp:
        return
    plt = _setup_vn_matplotlib()
    fig, ax = plt.subplots(1, 1, figsize=(9.2, 4.8), dpi=160)
    fig.patch.set_facecolor("#FFFFFF")

    labels, vals, peaks, colors, notes = [], [], [], [], []
    thr_refs = []

    if "E3a" in by_exp:
        d3a = by_exp["E3a"]
        thr_refs.append(d3a["thr_on"])
        if np.isfinite(d3a["empty_db"]):
            labels.append("1. Tắt quạt trần\n(Trạng thái tĩnh)")
            vals.append(d3a["empty_db"])
            peaks.append(float("nan"))
            colors.append("#94A3B8")
            notes.append(f"Báo nhầm: {d3a['fp_empty']} lần")
        if np.isfinite(d3a["fan_empty_db"]):
            labels.append("2. Bật quạt trần TỐI ĐA\n(Không có người đi)")
            vals.append(d3a["fan_empty_db"])
            peaks.append(float("nan"))
            colors.append("#F59E0B")
            notes.append(f"Báo nhầm: {d3a['fp_fan_empty']} lần ({d3a['fan_empty_minutes']:.1f}p)")

    if "E3b" in by_exp:
        d3b = by_exp["E3b"]
        thr_refs.append(d3b["thr_on"])
        if np.isfinite(d3b["quiet_db"]):
            labels.append("3. Quạt trần BẬT\n(Người ngồi yên)")
            vals.append(d3b["quiet_db"])
            peaks.append(float("nan"))
            colors.append("#64748B")
            notes.append(f"Báo nhầm: {d3b['fp_total']} lần")
        if np.isfinite(d3b["walk_db"]):
            labels.append("4. Quạt trần BẬT\n+ Người đi lại")
            vals.append(d3b["walk_db"])
            peaks.append(d3b.get("walk_peak_db", float("nan")))
            colors.append("#0D9488")
            notes.append(f"Phát hiện: {d3b['walk_tp']}/{d3b['walk_total']} lượt ({d3b['detect_pct']:.0f}%)")

    if not vals:
        plt.close(fig)
        return

    x = np.arange(len(vals))
    bars = ax.bar(x, vals, width=0.50, color=colors, edgecolor="#0F172A", linewidth=0.9, alpha=0.9,
                  label="Mức dao động trung bình (dB)")
    pk_x = [xi for xi, pv in zip(x, peaks) if np.isfinite(pv) and pv > 0]
    pk_y = [pv for pv in peaks if np.isfinite(pv) and pv > 0]
    if pk_y:
        ax.scatter(pk_x, pk_y, color="#0F172A", s=38, zorder=4, label="Mức đỉnh TB khi đi lại (dB)")
        for px, py in zip(pk_x, pk_y):
            ax.text(px, py + 0.018, f"Đỉnh TB: {py:.2f} dB", ha="center", va="bottom",
                    fontsize=8.5, fontweight="bold", color="#0F172A")

    thr_avg = float(np.mean(thr_refs)) if thr_refs else 0.19
    ax.axhline(thr_avg, color="#DC2626", ls="--", lw=1.5, label=f"Ngưỡng kích hoạt ({thr_avg:.3f} dB)")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9.5, fontweight="bold")
    ax.set_ylabel("Độ biến thiên CSI (dB)", fontsize=10.5, fontweight="bold")
    ax.set_title("Thực nghiệm Chống nhiễu Quạt trần trong Môi trường Thực tế", fontsize=12, fontweight="bold", pad=12)
    top_v = max(vals + (pk_y if pk_y else [0.35]))
    ax.set_ylim(0, max(top_v * 1.32, thr_avg * 1.8, 0.55))
    ax.grid(axis="y", ls="--", alpha=0.35)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="upper left", fontsize=9.0, frameon=True, facecolor="#F8FAFC")

    for rect, v, nt in zip(bars, vals, notes):
        ax.text(
            rect.get_x() + rect.get_width() / 2, v + 0.012,
            f"TB: {v:.3f} dB\n({nt})",
            ha="center", va="bottom", fontsize=8.3, fontweight="bold", color="#0F172A",
            bbox=dict(boxstyle="round,pad=0.18", facecolor="#FFFFFF", edgecolor="none", alpha=0.82),
        )

    fig.tight_layout()
    fig.savefig(out_png, dpi=180)
    plt.close(fig)


def plot_unified_signal_and_ratios(by_exp: dict[str, dict], out_png: str):
    """Biểu đồ Chung 1: So sánh Mức dao động (dB) và Tỉ lệ chênh lệch Đi lại / Tĩnh qua tất cả điều kiện."""
    order = [k for k in ("E1", "E2a", "E2b", "E3a", "E3b", "E4") if k in by_exp]
    if not order:
        return
    plt = _setup_vn_matplotlib()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.6, 5.1), dpi=160)
    fig.patch.set_facecolor("#FFFFFF")

    short_names = {
        "E1": "TN1\nChuẩn 3m",
        "E2a": "TN2a\nXa 4–5m",
        "E2b": "TN2b\nTường sau",
        "E3a": "TN3a\nQuạt (Tĩnh)",
        "E3b": "TN3b\nQuạt + Đi",
        "E4": "TN4\nTrống 15p",
    }

    # --- Panel A: Mức dao động Tĩnh vs Đi lại trên cả 6 thí nghiệm ---
    x = np.arange(len(order))
    w = 0.35
    q_vals = [by_exp[k]["quiet_db"] if np.isfinite(by_exp[k]["quiet_db"]) else 0.0 for k in order]
    w_vals = [by_exp[k]["walk_db"] if np.isfinite(by_exp[k]["walk_db"]) else 0.0 for k in order]
    p_vals = [by_exp[k].get("walk_peak_db", float("nan")) for k in order]
    thr_vals = [by_exp[k]["thr_on"] for k in order]

    b1 = ax1.bar(x - w / 2, q_vals, width=w, color="#94A3B8", edgecolor="#334155", linewidth=0.8,
                 label="Mức Tĩnh TB (dB)")
    b2 = ax1.bar(x + w / 2, w_vals, width=w, color="#2563EB", edgecolor="#1E3A8A", linewidth=0.8,
                 label="Mức Đi lại TB (dB)")
    ax1.plot(x, thr_vals, color="#DC2626", ls="--", marker="s", markersize=4.5, lw=1.3,
             label="Ngưỡng kích hoạt từng phiên (dB)")

    pk_x = [xi + w / 2 for xi, pv in zip(x, p_vals) if np.isfinite(pv) and pv > 0]
    pk_y = [pv for pv in p_vals if np.isfinite(pv) and pv > 0]
    if pk_y:
        ax1.scatter(pk_x, pk_y, color="#0F172A", s=36, zorder=5, label="Mức Đỉnh Đi lại TB (dB)")
        for px, py in zip(pk_x, pk_y):
            ax1.text(px, py + 0.02, f"{py:.2f}", ha="center", va="bottom",
                     fontsize=8.0, fontweight="bold", color="#0F172A")

    for rect in list(b1) + list(b2):
        h = rect.get_height()
        if h > 0.005:
            ax1.text(rect.get_x() + rect.get_width() / 2, h + 0.012, f"{h:.2f}",
                     ha="center", va="bottom", fontsize=7.6, fontweight="bold", color="#1E3A8A",
                     bbox=dict(boxstyle="round,pad=0.12", facecolor="#FFFFFF", edgecolor="none", alpha=0.82))

    top_a = max(q_vals + w_vals + (pk_y if pk_y else [0.5]))
    ax1.set_xticks(x)
    ax1.set_xticklabels([short_names.get(k, k) for k in order], fontsize=9.0, fontweight="bold")
    ax1.set_ylabel("Độ biến thiên CSI (dB)", fontsize=10, fontweight="bold")
    ax1.set_title("A. Mức dao động Tĩnh vs. Đi lại qua cả 6 thí nghiệm", fontsize=11, fontweight="bold", pad=10)
    ax1.set_ylim(0, max(top_a * 1.38, 0.6))
    ax1.grid(axis="y", ls="--", alpha=0.35)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.legend(loc="upper left", ncol=2, fontsize=7.8, frameon=True, facecolor="#F8FAFC")

    # --- Panel B: Tỉ lệ gấp mấy lần giữa Đi lại so với Tĩnh (Walk / Quiet Ratio) ---
    walk_keys = [k for k in ("E1", "E2a", "E2b", "E3b") if k in by_exp and by_exp[k]["walk_total"] > 0]
    xr = np.arange(len(walk_keys) + (1 if "E3a" in by_exp else 0))
    r_mean = [by_exp[k]["ratio_mean_x"] for k in walk_keys]
    r_peak = [by_exp[k]["ratio_peak_x"] for k in walk_keys]
    r_labels = [short_names.get(k, k) for k in walk_keys]

    w2 = 0.34
    xw_idx = np.arange(len(walk_keys))
    bm = ax2.bar(xw_idx - w2 / 2, r_mean, width=w2, color="#3B82F6", edgecolor="#1D4ED8",
                 label="Tỉ lệ: Đi lại TB / Tĩnh (lần)")
    bp = ax2.bar(xw_idx + w2 / 2, r_peak, width=w2, color="#0D9488", edgecolor="#0F766E",
                 label="Tỉ lệ: Đỉnh Đi lại / Tĩnh (lần)")

    for rect in list(bm) + list(bp):
        h = rect.get_height()
        if np.isfinite(h) and h > 0:
            ax2.text(rect.get_x() + rect.get_width() / 2, h + 0.08, f"{h:.2f}×",
                     ha="center", va="bottom", fontsize=8.3, fontweight="bold", color="#0F172A")

    if "E3a" in by_exp and by_exp["E3a"]["empty_db"] > 0:
        fan_ratio = by_exp["E3a"]["fan_empty_db"] / by_exp["E3a"]["empty_db"]
        idx_fan = len(walk_keys)
        bf = ax2.bar([idx_fan], [fan_ratio], width=0.42, color="#F59E0B", edgecolor="#B45309",
                     label="Đối chứng TN3a: Quạt bật / Quạt tắt")
        ax2.text(idx_fan, fan_ratio + 0.08, f"{fan_ratio:.2f}×\n(Chỉ nhích +{(fan_ratio - 1) * 100:.0f}%)",
                 ha="center", va="bottom", fontsize=8.0, fontweight="bold", color="#92400E")
        r_labels.append("TN3a\nQuạt Bật/Tắt")

    ax2.axhline(1.0, color="#64748B", ls=":", lw=1.2, label="Mốc 1.0× (Bằng mức nền tĩnh)")
    top_b = max((r_peak if r_peak else [2.0]) + [2.0])
    ax2.set_xticks(xr)
    ax2.set_xticklabels(r_labels, fontsize=9.0, fontweight="bold")
    ax2.set_ylabel("Tỉ lệ gấp mấy lần mức Tĩnh (× lần)", fontsize=10, fontweight="bold")
    ax2.set_title("B. Tỉ lệ chênh lệch Đi lại so với Tĩnh (Đi lại / Tĩnh)", fontsize=11, fontweight="bold", pad=10)
    ax2.set_ylim(0, top_b * 1.35)
    ax2.grid(axis="y", ls="--", alpha=0.35)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.legend(loc="upper left", fontsize=8.0, frameon=True, facecolor="#F8FAFC")

    fig.suptitle("Tổng hợp Mức dao động CSI và Tỉ lệ Chênh lệch Đi lại / Tĩnh qua các Điều kiện",
                 fontsize=12.5, fontweight="bold", y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out_png, dpi=180)
    plt.close(fig)


def plot_unified_latency_and_false_alarms(by_exp: dict[str, dict], out_png: str):
    """Biểu đồ Chung 2: So sánh Thời gian phản hồi (giây) và Tỉ lệ báo nhầm vùng tĩnh (%) qua tất cả điều kiện."""
    order = [k for k in ("E1", "E2a", "E2b", "E3a", "E3b", "E4") if k in by_exp]
    if not order:
        return
    plt = _setup_vn_matplotlib()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.6, 5.1), dpi=160)
    fig.patch.set_facecolor("#FFFFFF")

    short_names = {
        "E1": "TN1\nChuẩn 3m",
        "E2a": "TN2a\nXa 4–5m",
        "E2b": "TN2b\nTường sau",
        "E3a": "TN3a\nQuạt (Tĩnh)",
        "E3b": "TN3b\nQuạt + Đi",
        "E4": "TN4\nTrống 15p",
    }

    # --- Panel A: Thời gian phản hồi của mỗi điều kiện có người đi lại ---
    walk_keys = [k for k in ("E1", "E2a", "E2b", "E3b") if k in by_exp and by_exp[k]["walk_total"] > 0]
    if walk_keys:
        xw = np.arange(len(walk_keys))
        means = [by_exp[k]["lat_mean_s"] for k in walk_keys]
        mins = [by_exp[k]["lat_min_s"] for k in walk_keys]
        maxs = [by_exp[k]["lat_max_s"] for k in walk_keys]
        yerr_low = [max(0.0, m - mn) for m, mn in zip(means, mins)]
        yerr_high = [max(0.0, mx - m) for m, mx in zip(means, maxs)]

        bars1 = ax1.bar(
            xw, means, yerr=[yerr_low, yerr_high], capsize=5, width=0.48,
            color=["#0D9488", "#2563EB", "#7C3AED", "#D97706"][:len(walk_keys)],
            edgecolor="#0F172A", alpha=0.88,
            error_kw={"elinewidth": 1.4, "ecolor": "#1E293B"},
            label="Thời gian phản hồi TB (kèm khoảng Nhanh–Chậm)",
        )
        overall_lat = float(np.mean(means))
        ax1.axhline(overall_lat, color="#DC2626", ls="--", lw=1.3,
                    label=f"Trung bình toàn bộ các điều kiện ({overall_lat:.2f}s)")

        for rect, k, m_val, mn_val, mx_val in zip(bars1, walk_keys, means, mins, maxs):
            ax1.text(
                rect.get_x() + rect.get_width() / 2, mx_val + 0.14,
                f"TB: {m_val:.2f}s\n({mn_val:.1f}–{mx_val:.1f}s)\nBắt: {by_exp[k]['walk_tp']}/{by_exp[k]['walk_total']} lượt",
                ha="center", va="bottom", fontsize=8.1, fontweight="bold", color="#0F172A",
            )

        ax1.set_xticks(xw)
        ax1.set_xticklabels([short_names.get(k, k) for k in walk_keys], fontsize=9.2, fontweight="bold")
        ax1.set_ylabel("Thời gian phản hồi phát hiện (giây)", fontsize=10, fontweight="bold")
        ax1.set_title("A. Thời gian phản hồi theo từng điều kiện đi lại", fontsize=11, fontweight="bold", pad=10)
        ax1.set_ylim(0, max(maxs) * 1.38)
        ax1.grid(axis="y", ls="--", alpha=0.35)
        ax1.spines["top"].set_visible(False)
        ax1.spines["right"].set_visible(False)
        ax1.legend(loc="upper left", fontsize=8.2, frameon=True, facecolor="#F8FAFC")

    # --- Panel B: Tỉ lệ thời gian giữ đúng trạng thái tĩnh (%) & Tỉ lệ báo nhầm (%) qua 6 thí nghiệm ---
    xb = np.arange(len(order))
    fp_pcts = [by_exp[k]["fp_time_pct"] for k in order]
    acc_pcts = [by_exp[k]["static_acc_pct"] for k in order]
    fp_counts = [by_exp[k]["fp_total"] for k in order]
    neg_mins = [by_exp[k]["neg_minutes"] for k in order]

    bar_colors = ["#10B981" if c == 0 else ("#F59E0B" if p < 2.0 else "#3B82F6") for c, p in zip(fp_counts, fp_pcts)]
    bars2 = ax2.bar(xb, fp_pcts, width=0.50, color=bar_colors, edgecolor="#0F172A", alpha=0.9,
                    label="Tỉ lệ % thời gian bị báo nhầm trên tổng thời gian tĩnh")

    for rect, fp_c, fp_p, acc_p, n_m in zip(bars2, fp_counts, fp_pcts, acc_pcts, neg_mins):
        ax2.text(
            rect.get_x() + rect.get_width() / 2, rect.get_height() + 0.35,
            f"{fp_p:.2f}% thời gian\n({fp_c} lần / {n_m:.1f}p)\nĐúng tĩnh: {acc_p:.1f}%",
            ha="center", va="bottom", fontsize=7.8, fontweight="bold", color="#0F172A",
        )

    ax2.set_xticks(xb)
    ax2.set_xticklabels([short_names.get(k, k) for k in order], fontsize=9.0, fontweight="bold")
    ax2.set_ylabel("Tỉ lệ thời gian báo nhầm trong vùng tĩnh (%)", fontsize=10, fontweight="bold")
    ax2.set_title("B. Tỉ lệ báo nhầm & Độ ổn định trong thời gian tĩnh", fontsize=11, fontweight="bold", pad=10)
    ax2.set_ylim(0, max(max(fp_pcts) * 1.55, 8.0))
    ax2.grid(axis="y", ls="--", alpha=0.35)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.legend(loc="upper right", fontsize=8.2, frameon=True, facecolor="#F8FAFC")

    fig.suptitle("Tổng hợp Thời gian Phản hồi và Tỉ lệ Báo nhầm qua các Điều kiện Thí nghiệm",
                 fontsize=12.5, fontweight="bold", y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out_png, dpi=180)
    plt.close(fig)


def fmt_num(v: float, ndigits: int = 2) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    return f"{v:.{ndigits}f}"


def main():
    ap = argparse.ArgumentParser(description="Chấm điểm và xuất bảng số liệu kết quả thực nghiệm.")
    ap.add_argument("--data", default=os.path.join(HERE, "..", "data", "sessions"),
                    help="Thư mục chứa các phiên đo thực nghiệm (mặc định: data/sessions)")
    ap.add_argument("--out", default=os.path.join(HERE, "..", "reports"),
                    help="Thư mục xuất báo cáo (mặc định: reports)")
    ap.add_argument("--calib", default=None,
                    help="Tệp JSON hiệu chuẩn cố định (mặc định: tự lấy nền 30s đầu mỗi phiên)")
    ap.add_argument("--calib-s", type=float, default=30.0)
    ap.add_argument("--plot", action="store_true",
                    help="Tùy chọn vẽ thêm các biểu đồ PNG (mặc định: chỉ xuất bảng số liệu sạch)")
    args = ap.parse_args()

    data_dir = os.path.abspath(args.data)
    files = list_sessions(data_dir)
    if not files:
        print("\n[CHƯA CÓ DỮ LIỆU ĐO THẬT TRONG data/sessions]")
        print(f"  Thư mục kiểm tra: {data_dir}")
        print("  -> Hãy chạy `python host/record.py` để thu các phiên E1..E4 trước.")
        return

    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    session_rows: list[dict] = []
    e1_plot_src: str | None = None

    for path in files:
        try:
            sess = load_session(path)
        except Exception as e:
            print(f"[Bỏ qua tệp lỗi] {path}: {e}")
            continue

        exp_id = sess.meta.get("experiment_id") or sess.meta.get("position") or os.path.basename(os.path.dirname(path))
        cfg = MotionConfig.load(args.calib) if args.calib else MotionConfig()
        motion = MotionDetector(cfg, None)

        t_start = None
        if not args.calib:
            t_start = calibrate_causal_from_session(sess, motion, args.calib_s)
            if t_start is None:
                print(f"[Bỏ qua] {sess.name}: Không đủ đoạn tĩnh đầu phiên (>= 6s) để lấy mức nền.")
                continue

        res = run_offline(sess, motion, None, HOP, t_start)
        if len(res["host_t"]) == 0:
            print(f"[Bỏ qua] {sess.name}: Phiên quá ngắn sau bước lấy nền.")
            continue

        m = compute_intuitive_metrics(res)
        title_vi = EXP_TITLES_VI.get(exp_id, sess.meta.get("title_vi", exp_id))
        if args.plot:
            png_path = os.path.join(out_dir, f"{sess.name}.png")
            plot_session_vi(f"{title_vi} — Phiên {sess.name}", res, motion, png_path)
            if exp_id == "E1" and e1_plot_src is None:
                e1_plot_src = png_path
            elif e1_plot_src is None and m["walk_total"] > 0:
                e1_plot_src = png_path

        qc = sess.meta.get("qc", {})
        row = {
            "session": sess.name,
            "exp_id": exp_id,
            "title_vi": title_vi,
            "baseline_db": round(motion.cfg.baseline_median, 4),
            "thr_on": round(motion.cfg.thr_on, 4),
            "thr_off": round(motion.cfg.thr_off, 4),
            "avg_rate_hz": qc.get("avg_rate_hz", round((len(sess.dev_t) - 1) / max(sess.dev_t[-1] - sess.dev_t[0], 1e-3), 1)),
            "avg_rssi_dbm": qc.get("avg_rssi_dbm", round(float(np.mean(sess.rssi)), 1)),
            "note": sess.meta.get("note", ""),
            **m,
        }
        session_rows.append(row)
        walk_str = f"{m['walk_tp']}/{m['walk_total']}" if m["walk_total"] > 0 else "—"
        print(f"  [OK] {exp_id:<4} ({sess.name}): Phát hiện = {walk_str:<6} | "
              f"Báo nhầm = {m['fp_total']} lần ({m['neg_minutes']:.1f} phút tĩnh) | "
              f"Trễ TB = {fmt_num(m['lat_mean_s'])}s")

    if not session_rows:
        print("Không có phiên hợp lệ nào để tổng hợp.")
        return

    import pandas as pd
    df = pd.DataFrame(session_rows)
    raw_csv_path = os.path.join(out_dir, "session_metrics_raw.csv")
    df.to_csv(raw_csv_path, index=False, encoding="utf-8-sig")

    summary_df = pd.DataFrame({
        "Mã TN": df["exp_id"],
        "Tên thí nghiệm": df["title_vi"],
        "Tổng lượt đi": df["walk_total"],
        "Lượt phát hiện đúng": df["walk_tp"],
        "Tỉ lệ phát hiện (%)": df["detect_pct"].round(1),
        "Mức nền 30s đầu (dB)": df["baseline_db"].round(3),
        "Ngưỡng Bật thr_on (dB)": df["thr_on"].round(3),
        "Ngưỡng Tắt thr_off (dB)": df["thr_off"].round(3),
        "Mức Tĩnh TB (dB)": df["quiet_db"].round(3),
        "Mức Đi lại TB (dB)": df["walk_db"].round(3),
        "Mức Đỉnh Đi lại TB (dB)": df["walk_peak_db"].round(3),
        "Tỉ lệ Đi lại TB / Tĩnh (lần)": df["ratio_mean_x"].round(2),
        "Tỉ lệ Đỉnh Đi lại / Tĩnh (lần)": df["ratio_peak_x"].round(2),
        "Thời gian phản hồi TB (s)": df["lat_mean_s"].round(2),
        "Độ lệch chuẩn phản hồi (s)": df["lat_std_s"].round(2),
        "Phản hồi nhanh nhất (s)": df["lat_min_s"].round(2),
        "Phản hồi chậm nhất (s)": df["lat_max_s"].round(2),
        "Phản hồi từng lượt (s)": df["lat_each"],
        "Tổng thời gian tĩnh (s)": df["neg_seconds"].round(1),
        "Tổng thời gian tĩnh (phút)": df["neg_minutes"].round(2),
        "Số lần báo nhầm": df["fp_total"],
        "Số giây báo nhầm (s)": df["fp_seconds"].round(1),
        "Tỉ lệ % thời gian báo nhầm": df["fp_time_pct"].round(2),
        "Độ ổn định giữ đúng tĩnh (%)": df["static_acc_pct"].round(2),
        "Tần suất báo nhầm (lần/phút)": df["fp_per_min"].round(2),
        "Tốc độ gói TB (Hz)": df["avg_rate_hz"].round(2),
        "RSSI TB (dBm)": df["avg_rssi_dbm"].round(1),
    })
    summary_csv_path = os.path.join(out_dir, "experiment_summary.csv")
    summary_df.to_csv(summary_csv_path, index=False, encoding="utf-8-sig")

    # Gom nhóm theo mã thí nghiệm (E1, E2a, E2b, E3a, E3b, E4)
    by_exp: dict[str, dict] = {}
    for exp_id, grp in df.groupby("exp_id", sort=False):
        latencies = [value for values in grp["latencies_s"] for value in values]
        w_tot = int(grp["walk_total"].sum())
        w_tp = int(grp["walk_tp"].sum())
        neg_s_tot = float(grp["neg_seconds"].sum())
        fp_s_tot = float(grp["fp_seconds"].sum())
        fp_tot = int(grp["fp_total"].sum())
        neg_m_tot = neg_s_tot / 60.0
        fp_pct_tot = (100.0 * fp_s_tot / neg_s_tot) if neg_s_tot > 0 else float("nan")
        q_db_m = float(grp["quiet_db"].dropna().mean()) if grp["quiet_db"].notna().any() else float("nan")
        w_db_m = float(grp["walk_db"].dropna().mean()) if grp["walk_db"].notna().any() else float("nan")
        p_db_m = float(grp["walk_peak_db"].dropna().mean()) if grp["walk_peak_db"].notna().any() else float("nan")
        by_exp[exp_id] = {
            "exp_id": exp_id,
            "title_vi": EXP_TITLES_VI.get(exp_id, grp["title_vi"].iloc[0]),
            "n_sessions": len(grp),
            "walk_total": w_tot,
            "walk_tp": w_tp,
            "detect_pct": (100.0 * w_tp / w_tot) if w_tot > 0 else float("nan"),
            "fp_total": fp_tot,
            "fp_empty": int(grp["fp_empty"].sum()),
            "fp_fan_empty": int(grp["fp_fan_empty"].sum()),
            "fp_still": int(grp["fp_still"].sum()),
            "neg_seconds": neg_s_tot,
            "neg_minutes": neg_m_tot,
            "fp_seconds": fp_s_tot,
            "fp_time_pct": fp_pct_tot,
            "static_acc_pct": 100.0 - fp_pct_tot,
            "fp_per_min": (fp_tot / neg_m_tot) if neg_m_tot > 0 else float("nan"),
            "empty_minutes": float(grp["empty_minutes"].sum()),
            "fan_empty_minutes": float(grp["fan_empty_minutes"].sum()),
            "still_minutes": float(grp["still_minutes"].sum()),
            "lat_mean_s": float(np.mean(latencies)) if latencies else float("nan"),
            "lat_std_s": float(np.std(latencies)) if latencies else float("nan"),
            "lat_min_s": float(grp["lat_min_s"].dropna().min()) if grp["lat_min_s"].notna().any() else float("nan"),
            "lat_max_s": float(grp["lat_max_s"].dropna().max()) if grp["lat_max_s"].notna().any() else float("nan"),
            "lat_each": "; ".join(grp["lat_each"].dropna().tolist()),
            "walk_db": w_db_m,
            "walk_peak_db": p_db_m,
            "quiet_db": q_db_m,
            "empty_db": float(grp["empty_db"].dropna().mean()) if grp["empty_db"].notna().any() else float("nan"),
            "fan_empty_db": float(grp["fan_empty_db"].dropna().mean()) if grp["fan_empty_db"].notna().any() else float("nan"),
            "ratio_mean_x": (w_db_m / q_db_m) if (np.isfinite(w_db_m) and np.isfinite(q_db_m) and q_db_m > 0) else float("nan"),
            "ratio_peak_x": (p_db_m / q_db_m) if (np.isfinite(p_db_m) and np.isfinite(q_db_m) and q_db_m > 0) else float("nan"),
            "thr_on": float(grp["thr_on"].mean()),
        }

    if args.plot:
        if e1_plot_src and os.path.exists(e1_plot_src):
            shutil.copy2(e1_plot_src, os.path.join(out_dir, "Hinh1_ChuoiThoiGian_Chuan.png"))
        plot_slide_geometry_comparison(by_exp, os.path.join(out_dir, "Hinh2_SoSanh_KhoangCach_Tuong.png"))
        plot_slide_ceiling_fan(by_exp, os.path.join(out_dir, "Hinh3_ChongNhieu_QuatTran.png"))
        plot_unified_signal_and_ratios(by_exp, os.path.join(out_dir, "TongHop1_DaoDong_Va_TiLe_ChenhLech.png"))
        plot_unified_latency_and_false_alarms(by_exp, os.path.join(out_dir, "TongHop2_ThoiGianPhanHoi_Va_TiLeBaoNham.png"))

    # Xuất báo cáo Markdown tổng hợp chuẩn tiếng Việt
    md_path = os.path.join(out_dir, "experiment_results.md")
    tot_walk = sum(v["walk_total"] for v in by_exp.values())
    tot_tp = sum(v["walk_tp"] for v in by_exp.values())
    tot_fp = sum(v["fp_total"] for v in by_exp.values())
    tot_neg_s = sum(v["neg_seconds"] for v in by_exp.values())
    tot_fp_s = sum(v["fp_seconds"] for v in by_exp.values())
    tot_neg_min = tot_neg_s / 60.0
    tot_fp_pct = (100.0 * tot_fp_s / tot_neg_s) if tot_neg_s > 0 else float("nan")
    tot_acc_pct = 100.0 - tot_fp_pct

    ordered_keys = [k for k in ("E1", "E2a", "E2b", "E3a", "E3b", "E4") if k in by_exp] + [
        k for k in by_exp if k not in {"E1", "E2a", "E2b", "E3a", "E3b", "E4"}
    ]

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Báo cáo Tổng hợp Kết quả Thực nghiệm Phát hiện Chuyển động Wi‑Fi CSI\n\n")
        f.write(f"- **Thời điểm tổng hợp:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("- **Cách tính:** Phát hiện theo lượt là trạng thái bật chồng lên đoạn có nhãn chuyển động; "
                "không bắt buộc có lần chuyển từ tắt sang bật mới. Độ trễ tính từ nhãn chuyển động đầu tiên "
                "đến trạng thái bật đầu tiên theo thời gian ghi nhận.\n")
        f.write("- **Thời gian tĩnh đánh giá:** Chỉ tính các nhịp đầu ra quan sát được, mỗi nhịp quy ước 0.1 giây; "
                "loại phần lấy nền và 3.0 giây sau mỗi đoạn chuyển động. Nhãn thủ công và khoảng mất dữ liệu "
                "giới hạn độ chính xác thời gian.\n")
        f.write(f"- **Tổng số lượt đi lại đã kiểm thử:** **{tot_tp}/{tot_walk} lượt** "
                f"({(100.0 * tot_tp / tot_walk) if tot_walk else 0.0:.1f}%)\n")
        f.write(f"- **Tổng thời gian tĩnh đã đánh giá:** **{tot_neg_min:.2f} phút ({tot_neg_s:.1f} giây)** — "
                f"Thời gian bị báo nhầm: **{tot_fp_s:.1f} giây ({tot_fp_pct:.2f}%)**, "
                f"Độ ổn định giữ đúng trạng thái tĩnh: **{tot_acc_pct:.2f}%** ({tot_fp} lần chớp)\n\n")

        f.write("## 1. Bảng tổng hợp chung qua tất cả các điều kiện thí nghiệm\n\n")
        f.write("| Thí nghiệm | Phát hiện (lượt) | Tỉ lệ báo nhầm vùng tĩnh (% thời gian & số lần) | Thời gian phản hồi TB (Nhanh–Chậm) | Dao động Tĩnh vs. Đi lại (Đỉnh) [dB] | Tỉ lệ Đi lại / Tĩnh (TB & Đỉnh) |\n")
        f.write("|---|---:|---:|---:|---:|---:|\n")
        for k in ordered_keys:
            d = by_exp[k]
            det_str = f"{d['walk_tp']}/{d['walk_total']} ({d['detect_pct']:.0f}%)" if d["walk_total"] > 0 else "— (Đo tĩnh)"
            fp_str = f"{d['fp_time_pct']:.2f}% ({d['fp_total']} lần / {d['neg_minutes']:.1f}p)"
            lat_str = (
                f"{d['lat_mean_s']:.2f}s ({d['lat_min_s']:.1f}–{d['lat_max_s']:.1f}s)"
                if np.isfinite(d["lat_mean_s"]) else "—"
            )
            if k == "E3a":
                db_str = f"Tắt: {fmt_num(d['empty_db'], 3)} / Bật: {fmt_num(d['fan_empty_db'], 3)}"
                rat_f = (d["fan_empty_db"] / d["empty_db"]) if d["empty_db"] > 0 else float("nan")
                rat_str = f"Bật/Tắt: {rat_f:.2f}× (+{(rat_f - 1) * 100:.0f}%)"
            elif np.isfinite(d.get("walk_peak_db", float("nan"))):
                db_str = f"{fmt_num(d['quiet_db'], 3)} vs {fmt_num(d['walk_db'], 3)} ({fmt_num(d['walk_peak_db'], 3)})"
                rat_str = f"TB {d['ratio_mean_x']:.2f}× — Đỉnh **{d['ratio_peak_x']:.2f}×**"
            else:
                db_str = f"Tĩnh: {fmt_num(d['quiet_db'], 3)}"
                rat_str = "1.00× (Nền chuẩn)"
            f.write(f"| **{d['title_vi']}** | {det_str} | {fp_str} | {lat_str} | {db_str} | {rat_str} |\n")

        f.write("\n## 2. Bảng chi tiết Tỉ lệ báo nhầm và Độ ổn định trong thời gian tĩnh\n\n")
        f.write("| Thí nghiệm | Tổng thời gian tĩnh | Số lần báo nhầm | Tổng số giây báo nhầm | Tỉ lệ % thời gian báo nhầm | Độ ổn định giữ đúng tĩnh (%) |\n")
        f.write("|---|---:|---:|---:|---:|---:|\n")
        for k in ordered_keys:
            d = by_exp[k]
            f.write(
                f"| **{d['title_vi']}** | {d['neg_minutes']:.2f} phút ({d['neg_seconds']:.0f}s) | "
                f"{d['fp_total']} lần ({d['fp_per_min']:.2f} lần/phút) | {d['fp_seconds']:.1f}s | "
                f"**{d['fp_time_pct']:.2f}%** | **{d['static_acc_pct']:.2f}%** |\n"
            )
        f.write(
            f"| **TỔNG HỢP TOÀN BỘ** | **{tot_neg_min:.2f} phút ({tot_neg_s:.0f}s)** | "
            f"**{tot_fp} lần ({tot_fp / max(tot_neg_min, 1e-3):.2f} lần/phút)** | **{tot_fp_s:.1f}s** | "
            f"**{tot_fp_pct:.2f}%** | **{tot_acc_pct:.2f}%** |\n"
        )

        f.write("\n## 3. Bảng chi tiết Thời gian phản hồi của từng lượt đi lại\n\n")
        f.write("| Thí nghiệm | Số lượt phát hiện | Trung bình ± Độ lệch chuẩn | Nhanh nhất – Chậm nhất | Thời gian phản hồi từng lượt đi (Lượt 1 → N) |\n")
        f.write("|---|---:|---:|---:|---|\n")
        for k in ordered_keys:
            d = by_exp[k]
            if d["walk_total"] > 0:
                f.write(
                    f"| **{d['title_vi']}** | {d['walk_tp']}/{d['walk_total']} ({d['detect_pct']:.0f}%) | "
                    f"**{d['lat_mean_s']:.2f} ± {d['lat_std_s']:.2f}s** | "
                    f"{d['lat_min_s']:.2f}s – {d['lat_max_s']:.2f}s | `{d['lat_each']}` |\n"
                )

        f.write("\n## 4. Bảng chi tiết Tỉ lệ mức dao động Đi lại so với Tĩnh\n\n")
        f.write("| Thí nghiệm | Mức Tĩnh TB (dB) | Ngưỡng kích hoạt (dB) | Mức Đi lại TB (dB) | Mức Đỉnh Đi lại TB (dB) | Tỉ lệ Đi lại TB / Tĩnh | Tỉ lệ Đỉnh Đi lại / Tĩnh |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|\n")
        for k in ordered_keys:
            d = by_exp[k]
            r_m = f"{d['ratio_mean_x']:.2f} lần" if np.isfinite(d["ratio_mean_x"]) else "—"
            r_p = f"**{d['ratio_peak_x']:.2f} lần**" if np.isfinite(d["ratio_peak_x"]) else "—"
            f.write(
                f"| **{d['title_vi']}** | {fmt_num(d['quiet_db'], 3)} | {fmt_num(d['thr_on'], 3)} | "
                f"{fmt_num(d['walk_db'], 3)} | {fmt_num(d['walk_peak_db'], 3)} | {r_m} | {r_p} |\n"
            )

    print("\n" + "=" * 68)
    print(f"  ĐÃ XUẤT BÁO CÁO SỐ LIỆU THÀNH CÔNG!")
    print(f"  - Bảng báo cáo Markdown: {md_path}")
    print(f"  - Bảng CSV vẽ biểu đồ:   {summary_csv_path}")
    print(f"  - Bảng CSV chi tiết:     {raw_csv_path}")
    print("=" * 68)


if __name__ == "__main__":
    main()
