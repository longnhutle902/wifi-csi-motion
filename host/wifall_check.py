"""Kiểm chứng thuật toán tính Độ biến thiên CSI trên bộ dữ liệu mở WiFall (ESP32-S3, 10 người).

Chỉ sử dụng 4 hoạt động vận động sinh hoạt thường ngày (Đi bộ, Bật nhảy, Ngồi xuống, Đứng lên)
để đánh giá tính nhất quán của đặc trưng phát hiện chuyển động trên nhiều vóc dáng cơ thể khác nhau.

Chạy lệnh:
    python wifall_check.py
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from wifisense import dsp  # noqa: E402
from wifisense.detectors import MotionConfig  # noqa: E402

ACTIVITIES_VI = {
    "walk": "Đi bộ (walk)",
    "Jump": "Bật nhảy (Jump)",
    "sit": "Ngồi xuống (sit)",
    "stand": "Đứng lên (stand)",
}
ACTIVITY_ORDER = ["walk", "Jump", "sit", "stand"]


def load_wifall_csv(path: str) -> tuple[np.ndarray, np.ndarray] | None:
    """Đọc tệp CSV của WiFall -> (thời_gian_giây, biên_độ_52_kênh)."""
    t_list: list[float] = []
    amp_list: list[np.ndarray] = []
    previous_us = None
    wrap_offset = 0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ts_us = int(row["local_timestamp"])
                iq = json.loads(row["data"])
                if ts_us < 0 or not isinstance(iq, list) or len(iq) < 104:
                    continue
                arr = np.asarray(iq[:104], dtype=np.float32).reshape(52, 2)
                if not np.isfinite(arr).all():
                    continue
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            if previous_us is not None:
                if ts_us == previous_us:
                    continue
                if ts_us < previous_us:
                    if previous_us > 3 * (2 ** 32) // 4 and ts_us < (2 ** 32) // 4:
                        wrap_offset += 2 ** 32
                    else:
                        # A reset/out-of-order recording has no reliable continuous
                        # time axis. Do not invent a fixed-rate replacement interval.
                        return None
            previous_us = ts_us
            amp = np.hypot(arr[:, 0], arr[:, 1])
            t_list.append((ts_us + wrap_offset) * 1e-6)
            amp_list.append(amp)
    if len(t_list) < 40:
        return None
    t = np.asarray(t_list, dtype=np.float64)
    t = t - t[0]
    return t, np.stack(amp_list)


def analyze_wifall(raw_dir: str, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    calib_path = os.path.join(HERE, "..", "models", "motion_calib.json")
    cfg = MotionConfig.load(calib_path) if os.path.exists(calib_path) else MotionConfig()
    win_samples = int(cfg.win_s * dsp.FS)   # 120 mẫu (1.2 giây)
    hop_samples = int(cfg.hop_s * dsp.FS)   # 10 mẫu (0.1 giây)
    ref_thr = cfg.thr_on
    ref_base = cfg.baseline_median

    subjects = sorted(
        d for d in os.listdir(raw_dir)
        if os.path.isdir(os.path.join(raw_dir, d)) and d.upper().startswith("ID")
    )
    if not subjects:
        raise FileNotFoundError(f"Không tìm thấy thư mục ID0..ID9 tại: {raw_dir}")

    records: list[dict] = []
    print(f"Đang phân tích dữ liệu WiFall cho {len(subjects)} người tham gia ({', '.join(subjects)})...")

    for sid in subjects:
        for act in ACTIVITY_ORDER:
            files = sorted(glob.glob(os.path.join(raw_dir, sid, act, "*.csv")))
            for fp in files:
                loaded = load_wifall_csv(fp)
                if loaded is None:
                    continue
                t, amp = loaded
                if t[-1] - t[0] < cfg.win_s + 0.2:
                    continue
                tu, xu, valid = dsp.resample_uniform(t, amp)
                if len(xu) < win_samples + 5 or float(np.mean(valid)) < 0.8:
                    continue
                xp = dsp.preprocess(xu)
                _, sc = dsp.motion_score_series(xp, win=win_samples, hop=hop_samples)
                if len(sc) == 0:
                    continue
                mean_sc = float(np.mean(sc))
                peak_sc = float(np.max(sc))
                dur_s = float(t[-1] - t[0])
                rate_hz = (len(t) - 1) / max(dur_s, 1e-3)
                records.append({
                    "subject": sid,
                    "activity": act,
                    "activity_vi": ACTIVITIES_VI[act],
                    "file": os.path.basename(fp),
                    "duration_s": round(dur_s, 2),
                    "pkt_rate_hz": round(rate_hz, 1),
                    "mean_score_db": round(mean_sc, 4),
                    "peak_score_db": round(peak_sc, 4),
                    "exceeds_ref_thr": int(peak_sc > ref_thr),
                })

    if not records:
        raise RuntimeError("Không đọc được tệp hợp lệ nào từ WiFall.")

    import pandas as pd
    df = pd.DataFrame(records)
    participant_ids = sorted(df["subject"].unique())
    n_subjects = len(participant_ids)
    n_activities = int(df["activity"].nunique())
    df.to_csv(os.path.join(out_dir, "wifall_per_file.csv"), index=False, encoding="utf-8-sig")

    by_subj = (
        df.groupby("subject", as_index=False)
        .agg(
            n_files=("file", "count"),
            mean_db=("mean_score_db", "mean"),
            std_db=("mean_score_db", "std"),
            peak_db=("peak_score_db", "mean"),
            detect_pct=("exceeds_ref_thr", lambda x: 100.0 * float(np.mean(x))),
        )
    )
    by_subj.to_csv(os.path.join(out_dir, "wifall_by_subject.csv"), index=False, encoding="utf-8-sig")

    by_act = (
        df.groupby(["activity", "activity_vi"], as_index=False)
        .agg(
            n_files=("file", "count"),
            mean_db=("mean_score_db", "mean"),
            std_db=("mean_score_db", "std"),
            peak_db=("peak_score_db", "mean"),
            detect_pct=("exceeds_ref_thr", lambda x: 100.0 * float(np.mean(x))),
        )
    )
    by_act["order"] = by_act["activity"].map({a: i for i, a in enumerate(ACTIVITY_ORDER)})
    by_act = by_act.sort_values("order").drop(columns=["order"])
    by_act.to_csv(os.path.join(out_dir, "wifall_by_activity.csv"), index=False, encoding="utf-8-sig")

    fig_path = os.path.join(out_dir, "Hinh4_WiFall_10Nguoi.png")
    _plot_wifall_figure(df, by_subj, by_act, ref_base, ref_thr, fig_path)

    md_path = os.path.join(out_dir, "wifall_report.md")
    total_files = len(df)
    total_pass = int(df["exceeds_ref_thr"].sum())
    overall_pct = 100.0 * total_pass / total_files

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Kết quả Kiểm chứng trên Bộ dữ liệu Mở WiFall (ESP32‑S3, {n_subjects} người)\n\n")
        f.write("## 1. Tóm tắt chung\n\n")
        f.write(f"- **Phần cứng thu dữ liệu WiFall:** Chip ESP32‑S3, 52 kênh sóng mang CSI (tương đồng phần cứng đồ án).\n")
        f.write(f"- **Quy mô kiểm chứng:** **{total_files} tệp đo** thuộc **{n_subjects} người tham gia "
                f"({', '.join(participant_ids)})** với {n_activities} loại hoạt động có tệp hợp lệ.\n")
        f.write(f"- **Tỉ lệ tệp có biên độ dao động vượt ngưỡng kích hoạt tham chiếu (`{ref_thr:.3f} dB`):** "
                f"**{total_pass}/{total_files} tệp ({overall_pct:.1f}%)**.\n")
        f.write(f"- **Mức dao động trung bình toàn bộ {n_subjects} người:** **{df['mean_score_db'].mean():.3f} dB** "
                f"(đỉnh trung bình **{df['peak_score_db'].mean():.3f} dB**), cao gấp **~{df['mean_score_db'].mean() / ref_base:.1f} lần** "
                f"mức nền phòng tĩnh tham chiếu (`{ref_base:.3f} dB`).\n\n")

        f.write("## 2. Thống kê theo từng loại vận động\n\n")
        f.write("| Hoạt động | Số tệp đo | Dao động trung bình (dB) | Dao động đỉnh TB (dB) | Tỉ lệ vượt ngưỡng tham chiếu |\n")
        f.write("|---|---:|---:|---:|---:|\n")
        for _, r in by_act.iterrows():
            n_ok = int(round(r["detect_pct"] * r["n_files"] / 100.0))
            f.write(
                f"| {r['activity_vi']} | {int(r['n_files'])} | "
                f"{r['mean_db']:.3f} ± {r['std_db']:.3f} | {r['peak_db']:.3f} | "
                f"{n_ok}/{int(r['n_files'])} ({r['detect_pct']:.1f}%) |\n"
            )

        f.write(f"\n## 3. Thống kê theo {n_subjects} người tham gia\n\n")
        f.write("| Mã người | Số tệp đo | Dao động trung bình (dB) | Dao động đỉnh TB (dB) | Tỉ lệ vượt ngưỡng tham chiếu |\n")
        f.write("|---|---:|---:|---:|---:|\n")
        for _, r in by_subj.iterrows():
            n_ok = int(round(r["detect_pct"] * r["n_files"] / 100.0))
            f.write(
                f"| {r['subject']} | {int(r['n_files'])} | "
                f"{r['mean_db']:.3f} ± {r['std_db']:.3f} | {r['peak_db']:.3f} | "
                f"{n_ok}/{int(r['n_files'])} ({r['detect_pct']:.1f}%) |\n"
            )

        f.write("\n## 4. Nhận xét đưa vào Báo cáo / Thuyết trình\n\n")
        f.write("1. **Ý nghĩa chỉ số:** Mỗi tệp đạt khi ít nhất một cửa sổ có điểm đỉnh vượt ngưỡng tham chiếu. "
                "Đây là kiểm tra đặc trưng trên các đoạn vận động, chưa phải tỉ lệ chính xác của hệ thống "
                "phân loại nhị phân có ngưỡng kép và xác nhận liên tiếp.\n")
        f.write("2. **Giới hạn xử lý:** Tệp WiFall được lọc trên toàn đoạn; thực nghiệm trong nhà xử lý từng "
                "bộ đệm trượt. Mức điểm giữa hai cách xử lý cần được đối chiếu thận trọng.\n")
        f.write("3. **Giới hạn dữ liệu:** Phân tích này chỉ chọn các hoạt động vận động, không đánh giá đoạn tĩnh; "
                "do đó không suy ra tỉ lệ báo nhầm hoặc khả năng khái quát cho người chưa kiểm thử.\n")

    print(f"\nHoàn tất kiểm chứng WiFall ({total_files} tệp)!")
    print(f"  - Tỉ lệ vượt ngưỡng tham chiếu: {total_pass}/{total_files} ({overall_pct:.1f}%)")
    print(f"  - Báo cáo chi tiết: {md_path}")
    print(f"  - Biểu đồ Slide:    {fig_path}")


def _plot_wifall_figure(df, by_subj, by_act, ref_base: float, ref_thr: float, out_png: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Segoe UI", "Arial", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.2, 5.2), dpi=160)
    fig.patch.set_facecolor("#FFFFFF")

    # --- Panel trái: Theo 10 người tham gia (ID0 - ID9) ---
    x1 = np.arange(len(by_subj))
    bars1 = ax1.bar(
        x1, by_subj["mean_db"], yerr=by_subj["std_db"].fillna(0),
        capsize=3.5, width=0.62, color="#2563EB", alpha=0.88,
        edgecolor="#1E40AF", linewidth=0.8, error_kw={"elinewidth": 1.1, "ecolor": "#334155"},
        label="Dao động TB ± độ lệch chuẩn (dB)",
    )
    ax1.scatter(x1, by_subj["peak_db"], color="#0F172A", s=28, zorder=4, label="Mức đỉnh trung bình (dB)")
    ax1.axhline(ref_thr, color="#DC2626", linestyle="--", linewidth=1.4,
                label=f"Ngưỡng kích hoạt tham chiếu ({ref_thr:.2f} dB)")
    ax1.axhline(ref_base, color="#64748B", linestyle=":", linewidth=1.2,
                label=f"Mức nền phòng tĩnh ({ref_base:.2f} dB)")

    ax1.set_xticks(x1)
    ax1.set_xticklabels(by_subj["subject"], fontsize=9.5, fontweight="bold")
    ax1.set_ylabel("Độ biến thiên CSI (dB)", fontsize=10.5, fontweight="bold")
    ax1.set_title(f"A. Độ biến thiên CSI trên {len(by_subj)} người", fontsize=11, fontweight="bold", pad=10)
    top1 = float(np.maximum(by_subj["peak_db"], by_subj["mean_db"] + by_subj["std_db"].fillna(0)).max())
    ax1.set_ylim(0, max(top1 * 1.38, 1.35))
    ax1.grid(axis="y", linestyle="--", alpha=0.35)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.legend(loc="upper right", ncol=2, fontsize=8.0, frameon=True, facecolor="#F8FAFC")

    for rect, (_, row) in zip(bars1, by_subj.iterrows()):
        y_lbl = max(float(row["peak_db"]), float(row["mean_db"] + np.nan_to_num(row["std_db"]))) + 0.028
        ax1.text(rect.get_x() + rect.get_width() / 2.0, y_lbl, f"{row['mean_db']:.2f}",
                 ha="center", va="bottom", fontsize=8.2, fontweight="bold", color="#1E3A8A")

    # --- Panel phải: Theo 4 hoạt động vận động ---
    labels_short = [ACTIVITIES_VI[activity] for activity in by_act["activity"]]
    color_map = dict(zip(ACTIVITY_ORDER, ["#0D9488", "#2563EB", "#D97706", "#7C3AED"]))
    colors2 = [color_map[activity] for activity in by_act["activity"]]
    x2 = np.arange(len(by_act))
    bars2 = ax2.bar(
        x2, by_act["mean_db"], yerr=by_act["std_db"].fillna(0),
        capsize=4.5, width=0.55, color=colors2, alpha=0.88,
        edgecolor="#1E293B", linewidth=0.8, error_kw={"elinewidth": 1.2, "ecolor": "#334155"},
        label="Dao động trung bình (dB)",
    )
    ax2.scatter(x2, by_act["peak_db"], color="#0F172A", s=34, zorder=4, label="Mức đỉnh trung bình (dB)")
    ax2.axhline(ref_thr, color="#DC2626", linestyle="--", linewidth=1.4,
                label=f"Ngưỡng kích hoạt ({ref_thr:.2f} dB)")
    ax2.axhline(ref_base, color="#64748B", linestyle=":", linewidth=1.2,
                label=f"Mức nền tĩnh ({ref_base:.2f} dB)")

    ax2.set_xticks(x2)
    ax2.set_xticklabels(labels_short, fontsize=9.5, fontweight="bold")
    ax2.set_ylabel("Độ biến thiên CSI (dB)", fontsize=10.5, fontweight="bold")
    ax2.set_title("B. So sánh giữa các kiểu vận động hàng ngày", fontsize=11, fontweight="bold", pad=10)
    top2 = float(np.maximum(by_act["peak_db"], by_act["mean_db"] + by_act["std_db"].fillna(0)).max())
    ax2.set_ylim(0, max(top2 * 1.42, 1.40))
    ax2.grid(axis="y", linestyle="--", alpha=0.35)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.legend(loc="upper right", ncol=2, fontsize=8.0, frameon=True, facecolor="#F8FAFC")

    for rect, (_, row) in zip(bars2, by_act.iterrows()):
        y_top = max(float(row["peak_db"]), float(row["mean_db"] + row["std_db"])) + 0.04
        ax2.text(
            rect.get_x() + rect.get_width() / 2.0, y_top,
            f"TB: {row['mean_db']:.2f} dB\n({row['detect_pct']:.0f}% vượt ngưỡng)",
            ha="center", va="bottom", fontsize=8.2, fontweight="bold", color="#0F172A",
        )

    fig.suptitle(
        f"Kiểm chứng trên Bộ dữ liệu Mở WiFall (ESP32-S3, 52 sóng mang — {len(df)} bản ghi của {len(by_subj)} người)",
        fontsize=12.5, fontweight="bold", y=0.99,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out_png, dpi=180)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="Đánh giá thuật toán trên bộ dữ liệu mở WiFall (10 người).")
    ap.add_argument(
        "--raw",
        default=os.path.join(HERE, "..", "datasets", "raw", "WiFall", "WiFall"),
        help="Đường dẫn tới thư mục gốc WiFall chứa ID0..ID9",
    )
    ap.add_argument(
        "--out",
        default=os.path.join(HERE, "..", "reports", "wifall_benchmark"),
        help="Thư mục lưu bảng kết quả và biểu đồ",
    )
    args = ap.parse_args()
    analyze_wifall(os.path.abspath(args.raw), os.path.abspath(args.out))


if __name__ == "__main__":
    main()
