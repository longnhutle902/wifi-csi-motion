"""Chương trình thu dữ liệu thực nghiệm có hướng dẫn bằng âm thanh (Indoor Wi-Fi CSI).

Cách chạy nhanh (giao diện menu chọn số, không cần nhớ lệnh):
    python record.py

Hoặc chạy trực tiếp từng thí nghiệm bằng dòng lệnh:
    python record.py --protocol e1 --port COM4
    python record.py --protocol e2a --port COM4
    python record.py --protocol e2b --port COM4
    python record.py --protocol e3a --port COM4
    python record.py --protocol e3b --port COM4
    python record.py --protocol e4 --port COM4
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import queue
import subprocess
import sys
import time
from dataclasses import asdict

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from wifisense import dsp  # noqa: E402
from wifisense.detectors import MotionConfig  # noqa: E402
from wifisense.pipeline import Recorder, SerialSource  # noqa: E402


def _build_walk_cycles(n_cycles: int, calib_note: str) -> list[tuple[str, float, str, str]]:
    """Tạo chuỗi: 6s chuẩn bị -> 35s lấy nền tĩnh -> N chu kỳ (15s đi lại, 6s về ghế, 15s ngồi yên)."""
    steps: list[tuple[str, float, str, str]] = [
        ("transition", 6, "Ngồi vào ghế tĩnh (cách đường nối 2 mạch >= 1m), ổn định tư thế", "prep"),
        ("calib", 35, f"LẤY MỨC NỀN ĐẦU PHIÊN (35s): {calib_note}", "still"),
    ]
    for k in range(1, n_cycles + 1):
        steps.append(("walk", 15, f"[Lượt {k}/{n_cycles}] ĐỨNG DẬY & ĐI LẠI tự nhiên qua vùng giữa 2 mạch", "walk"))
        steps.append(("transition", 6, f"[Lượt {k}/{n_cycles}] Quay về ghế ngồi xuống, để tay yên ổn định", "trans"))
        steps.append(("still", 15, f"[Lượt {k}/{n_cycles}] NGỒI YÊN KHÔNG NHÚC NHÍCH tại ghế", "still"))
    return steps


EXPERIMENT_SPECS: dict[str, dict] = {
    "e1": {
        "code": "E1",
        "title": "TN1 — Điều kiện chuẩn (2.5–3m, không vật cản, quạt tắt)",
        "setup_hint": "Đặt TX–RX cách 2.5–3m nhìn thấy nhau, cao ~1m. TẮT quạt trần. Ghế ngồi cách đường truyền >= 1m.",
        "fan": "off",
        "geometry": "LOS_2.5_3m",
        "steps": _build_walk_cycles(8, "Ngồi yên không nhúc nhích (quạt trần TẮT)"),
    },
    "e2a": {
        "code": "E2a",
        "title": "TN2a — Khoảng cách xa / Vướng đồ đạc (~4–5m chéo phòng)",
        "setup_hint": "Đặt TX–RX chéo góc phòng (~4–5m, vướng một phần bàn/tủ/nội thất). TẮT quạt trần.",
        "fan": "off",
        "geometry": "Dist_4_5m_Obstacle",
        "steps": _build_walk_cycles(6, "Ngồi yên không nhúc nhích (khoảng cách xa)"),
    },
    "e2b": {
        "code": "E2b",
        "title": "TN2b — Tác động của bức tường phía sau",
        "setup_hint": "Cách 1: Đặt 1 mạch sang bên kia bức tường phía sau (đo xuyên tường).\n"
                      "  Cách 2 (nếu không qua tường được): Đặt cặp mạch sát bức tường phía sau 15–20 cm.",
        "fan": "off",
        "geometry": "Back_Wall",
        "steps": _build_walk_cycles(6, "Ngồi yên không nhúc nhích (kiểm tra tường phía sau)"),
    },
    "e3a": {
        "code": "E3a",
        "title": "TN3a — Nhiễu quạt trần ở trạng thái tĩnh (Đối chứng Tắt vs Bật)",
        "setup_hint": "Đặt TX–RX khoảng cách chuẩn 2.5–3m. LÚC BẮT ĐẦU: QUẠT TRẦN PHẢI ĐANG TẮT!",
        "fan": "off_then_max",
        "geometry": "LOS_2.5_3m",
        "steps": [
            ("transition", 10, "Đảm bảo QUẠT TRẦN ĐANG TẮT. Ra khỏi phòng hoặc ngồi vào ghế tĩnh", "prep"),
            ("empty", 90, "GIAI ĐOẠN 1 — QUẠT TẮT (90s): Giữ tĩnh hoàn toàn (lấy nền + đối chứng)", "still"),
            ("transition", 20, "Vào BẬT QUẠT TRẦN SỐ MẠNH NHẤT, sau đó bước ra xa phòng (hoặc về ghế tĩnh)", "trans"),
            ("fan_empty", 240, "GIAI ĐOẠN 2 — QUẠT TRẦN BẬT TỐI ĐA (4 phút): Không có người đi lại", "still"),
        ],
    },
    "e3b": {
        "code": "E3b",
        "title": "TN3b — Quạt trần đang BẬT số lớn + Có người đi lại",
        "setup_hint": "Giữ QUẠT TRẦN ĐANG BẬT SỐ MẠNH NHẤT suốt cả phiên đo.",
        "fan": "max",
        "geometry": "LOS_2.5_3m_FanOn",
        "steps": _build_walk_cycles(6, "Ngồi yên không nhúc nhích (dưới quạt trần đang bật)"),
    },
    "e4": {
        "code": "E4",
        "title": "TN4 — Phòng trống liên tục (Kiểm tra báo nhầm dài hạn — 15 phút)",
        "setup_hint": "TẮT quạt trần. Bấm bắt đầu rồi bước hẳn ra ngoài phòng thử nghiệm, đóng cửa lại trong 15 phút.",
        "fan": "off",
        "geometry": "Empty_Room_Long",
        "steps": [
            ("transition", 15, "RỜI HẲN KHỎI PHÒNG và đóng cửa lại (15s chuẩn bị)", "prep"),
            ("empty", 900, "PHÒNG TRỐNG LIÊN TỤC (15 phút): Chờ đến khi nghe 3 tiếng bíp hoàn thành", "still"),
        ],
    },
    "test30s": {
        "code": "TEST",
        "title": "Thử nhanh âm thanh & kết nối mạch (30 giây — lưu nháp riêng)",
        "setup_hint": "Dùng để kiểm tra loa máy tính và đường truyền COM4 trước khi đo thật.",
        "fan": "off",
        "geometry": "Scratch_Test",
        "steps": [
            ("transition", 4, "Chuẩn bị ngồi yên thử nghiệm", "prep"),
            ("calib", 10, "Ngồi yên thử (10s)", "still"),
            ("walk", 10, "Đứng dậy đi lại thử (10s)", "walk"),
            ("transition", 4, "Về ghế ngồi yên", "trans"),
            ("still", 8, "Ngồi yên kết thúc (8s)", "still"),
        ],
    },
}


def play_cue(kind: str):
    """Phát tín hiệu âm thanh phân biệt rõ từng pha để không cần nhìn màn hình liên tục."""
    try:
        import winsound
        if kind == "walk":
            # 1 tiếng bíp CAO, rõ -> BẮT ĐẦU ĐỨNG DẬY ĐI LẠI
            winsound.Beep(1450, 300)
        elif kind == "trans":
            # 2 tiếng bíp TRUNG -> Quay về ghế ổn định
            winsound.Beep(920, 140)
            time.sleep(0.06)
            winsound.Beep(920, 140)
        elif kind == "still":
            # 1 tiếng bíp TRẦM -> Giữ yên bất động
            winsound.Beep(580, 220)
        elif kind == "tick":
            # Tiếng tích nhẹ báo đếm ngược 3..2..1 trước khi đứng dậy đi
            winsound.Beep(1050, 60)
        elif kind == "done":
            for f in (880, 1175, 1568):
                winsound.Beep(f, 180)
                time.sleep(0.04)
        else:
            winsound.Beep(800, 150)
    except Exception:
        print("\a", end="", flush=True)


def frozen_config_info() -> dict:
    cfg = MotionConfig()
    snap = {
        "motion_config": asdict(cfg),
        "dsp_fs_hz": dsp.FS,
        "dsp_lowpass_cutoff_hz": 6.0,
        "dsp_hampel_k": 9,
        "dsp_hampel_sigma": 2.5,
        "dsp_trimmed_pct": [15, 90],
    }
    digest = hashlib.sha256(json.dumps(snap, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    snap["config_hash"] = digest
    return snap


def check_port_available(port: str, baud: int = 921600) -> tuple[bool, str]:
    try:
        import serial
        import serial.tools.list_ports
        ports = [cp.device for cp in serial.tools.list_ports.comports()]
        target = port if port in ports else (ports[0] if ports else port)
        s = serial.Serial(target, baud, timeout=0.2)
        s.close()
        return True, target
    except Exception as e:
        msg = str(e)
        if "PermissionError" in msg or "Access is denied" in msg:
            return False, (
                f"Cổng {port} đang bận (có thể cửa sổ Web Dashboard đang mở).\n"
                f"  -> Hãy tắt cửa sổ Dashboard (Ctrl+C) trước khi chạy thu dữ liệu thí nghiệm!"
            )
        return False, f"Không mở được cổng {port}: {msg}"


def run_protocol(protocol_key: str, port: str, baud: int, out_root: str, note: str = "",
                 empty_minutes: float | None = None) -> bool:
    spec = EXPERIMENT_SPECS[protocol_key]
    steps = list(spec["steps"])
    if empty_minutes is not None and (not math.isfinite(empty_minutes) or empty_minutes <= 0):
        raise ValueError("empty_minutes must be finite and positive")
    if protocol_key == "e4" and empty_minutes is not None:
        steps[-1] = ("empty", float(empty_minutes) * 60.0,
                     f"PHÒNG TRỐNG LIÊN TỤC ({empty_minutes:g} phút): Không vào phòng", "still")

    total_s = sum(d for _, d, _, _ in steps)
    print("\n" + "=" * 68)
    print(f"  {spec['title']}")
    print(f"  Tổng thời gian: {total_s / 60.0:.1f} phút ({int(total_s)} giây)")
    print(f"  Hướng dẫn bố trí: {spec['setup_hint']}")
    print("=" * 68)

    ok_port, port_or_err = check_port_available(port, baud)
    if not ok_port:
        print(f"\n[LỖI CỔNG COM] {port_or_err}\n")
        return False

    if protocol_key == "test30s":
        save_root = os.path.abspath(os.path.join(HERE, "..", "data", "_scratch_test"))
    else:
        save_root = os.path.abspath(out_root)

    stamp = time.strftime("%Y%m%d_%H%M%S")
    code = spec["code"]
    base = os.path.join(save_root, code, f"{code}_{stamp}")

    src = SerialSource(port_or_err, baud)
    src.start()

    try:
        print(f"\nĐang kết nối mạch thu RX ({port_or_err})... chờ gói tin CSI...")
        t_wait = time.monotonic()
        while src.q.empty() and time.monotonic() - t_wait < 10.0:
            time.sleep(0.1)

        if src.q.empty():
            print("\n[KHÔNG NHẬN ĐƯỢC DỮ LIỆU CSI]")
            print("  1. Kiểm tra cáp USB của mạch RX đã cắm chắc chưa.")
            print("  2. Kiểm tra mạch phát TX đã được cấp nguồn (pin dự phòng / củ sạc) chưa.")
            print("  3. Đảm bảo cửa sổ Web Dashboard đã tắt để không tranh cổng COM.")
            src.stop()
            src.join(timeout=2.0)
            return False

        meta = {
            "position": code,
            "experiment_id": code,
            "protocol": protocol_key,
            "title_vi": spec["title"],
            "fan_state": spec["fan"],
            "geometry": spec["geometry"],
            "port": src.port,
            "note": note,
            "frozen_config": frozen_config_info(),
        }
        rec = Recorder(base, meta)
    except BaseException:
        src.stop()
        src.join(timeout=2.0)
        raise
    host_times: list[float] = []
    rssi_vals: list[int] = []

    def pump_step(seconds: float, label: str, next_is_walk: bool):
        rec.set_label(label)
        t_end = time.time() + seconds
        last_print = 0.0
        ticked: set[int] = set()
        while True:
            now = time.time()
            rem_f = t_end - now
            if rem_f <= 0:
                break
            try:
                while True:
                    ht, line, pkt = src.q.get_nowait()
                    rec.write(ht, line)
                    host_times.append(ht)
                    rssi_vals.append(pkt.rssi)
            except queue.Empty:
                time.sleep(0.03)

            rem_ceil = int(rem_f) + 1
            if next_is_walk and rem_ceil in (3, 2, 1) and rem_ceil not in ticked:
                ticked.add(rem_ceil)
                play_cue("tick")

            if now - last_print >= 0.5:
                last_print = now
                rate_now = 0.0
                if len(host_times) >= 10:
                    dt = host_times[-1] - host_times[max(0, len(host_times) - 60)]
                    if dt > 0:
                        rate_now = (min(len(host_times), 60) - 1) / dt
                warn = "  [SẮP ĐỨNG DẬY ĐI!]" if (next_is_walk and rem_f <= 3.2) else ""
                print(
                    f"\r  [{label.upper():^10}] còn {int(rem_f):3d}s | "
                    f"gói: {rec.n:6d} ({rate_now:4.1f} gói/s){warn:<20}",
                    end="",
                    flush=True,
                )
        print()

    aborted = False
    try:
        for i, (label, dur, instr, cue) in enumerate(steps):
            next_is_walk = (i + 1 < len(steps)) and (steps[i + 1][0] == "walk")
            print(f"\n>>> Bước {i + 1}/{len(steps)} [{int(dur)}s]: {instr}")
            play_cue(cue)
            pump_step(dur, label, next_is_walk)
        play_cue("done")
    except KeyboardInterrupt:
        aborted = True
        print("\n\n[ĐÃ DỪNG SỚM BỞI NGƯỜI DÙNG]")
    except Exception:
        aborted = True
        raise
    finally:
        recording_ended = time.time()
        src.stop()
        src.join(timeout=2.0)

        # Thống kê kiểm tra chất lượng nhanh (QC) trước khi đóng tệp
        dur_actual = (host_times[-1] - host_times[0]) if len(host_times) >= 2 else 0.0
        avg_rate = (len(host_times) - 1) / dur_actual if dur_actual > 0 else 0.0
        max_gap = float(max(
            (host_times[j] - host_times[j - 1] for j in range(1, len(host_times))),
            default=0.0,
        ))
        # Inter-packet intervals alone miss a transmitter that stops near the
        # end: two early packets can otherwise appear to be a perfect 50 Hz run.
        capture_s = max(0.0, recording_ended - rec.meta["start_time"])
        if host_times:
            max_gap = max(max_gap, host_times[0] - rec.meta["start_time"],
                          recording_ended - host_times[-1])
        else:
            max_gap = capture_s
        capture_rate = len(host_times) / capture_s if capture_s > 0 else 0.0
        avg_rssi = float(sum(rssi_vals) / len(rssi_vals)) if rssi_vals else 0.0
        qc_pass = (not aborted) and (capture_rate >= 30.0) and (max_gap <= 2.5)
        rec.meta["qc"] = {
            "aborted": aborted,
            "duration_s": round(dur_actual, 2),
            "avg_rate_hz": round(avg_rate, 2),
            "capture_duration_s": round(capture_s, 2),
            "capture_rate_hz": round(capture_rate, 2),
            "max_gap_s": round(max_gap, 3),
            "avg_rssi_dbm": round(avg_rssi, 1),
            "qc_pass": qc_pass,
        }
        rec.close()

    if aborted and rec.n < 200:
        for ext in (".csv", ".json"):
            try:
                os.remove(base + ext)
            except OSError:
                pass
        print("Đã xóa tệp nháp chưa đủ dữ liệu.")
        return False

    status_txt = "ĐẠT CHUẨN" if qc_pass else "CẦN KIỂM TRA LẠI (bị ngắt sớm hoặc mất gói)"
    print("\n" + "-" * 68)
    print(f"  ĐÃ LƯU: {base}.csv")
    print(f"  Tổng gói: {rec.n} | Tốc độ TB: {avg_rate:.1f} gói/s | RSSI TB: {avg_rssi:.1f} dBm")
    print(f"  Khoảng trễ tối đa giữa 2 gói: {max_gap:.2f}s | Chất lượng: {status_txt}")
    print("-" * 68)
    return qc_pass


def interactive_menu(default_port: str, baud: int, out_root: str):
    menu_map = {
        "1": "e1",
        "2": "e2a",
        "3": "e2b",
        "4": "e3a",
        "5": "e3b",
        "6": "e4",
        "0": "test30s",
    }
    while True:
        print("\n" + "=" * 68)
        print("  HỆ THỐNG THU DỮ LIỆU THỰC NGHIỆM TRONG NHÀ — WI-FI CSI (ESP32-S3)")
        print("=" * 68)
        print("  [1] TN1  (E1)  — Điều kiện chuẩn 2.5–3m, quạt tắt       (~5.5 phút)")
        print("  [2] TN2a (E2a) — Khoảng cách xa 4–5m / vướng đồ đạc     (~4.3 phút)")
        print("  [3] TN2b (E2b) — Tác động của bức tường phía sau        (~4.3 phút)")
        print("  [4] TN3a (E3a) — Quạt trần ở trạng thái tĩnh (Tắt->Bật) (~5.8 phút)")
        print("  [5] TN3b (E3b) — Quạt trần đang bật + Có người đi lại   (~4.3 phút)")
        print("  [6] TN4  (E4)  — Phòng trống liên tục 15 phút           (~15.2 phút)")
        print("  ------------------------------------------------------------------")
        print("  [0] Thử nhanh loa & kết nối mạch (30 giây — không tính vào báo cáo)")
        print("  [E] Chấm điểm & Xuất toàn bộ bảng + biểu đồ báo cáo (evaluate.py)")
        print("  [Q] Thoát")
        print("=" * 68)
        choice = input("  Nhập lựa chọn của bạn (1-6, 0, E, Q): ").strip().lower()
        if choice == "q":
            break
        if choice == "e":
            eval_script = os.path.join(HERE, "evaluate.py")
            subprocess.run([sys.executable, eval_script, "--data", out_root], check=False)
            continue
        if choice not in menu_map:
            print("  Lựa chọn không hợp lệ, vui lòng nhập lại.")
            continue

        pkey = menu_map[choice]
        spec = EXPERIMENT_SPECS[pkey]
        print(f"\n  Bạn đã chọn: {spec['title']}")
        print(f"  Nhắc nhở: {spec['setup_hint']}")
        note = input("  Ghi chú ngắn (ví dụ 'xuyên tường' hoặc nhấn Enter bỏ qua): ").strip()
        confirm = input("  Nhấn Enter để BẮT ĐẦU (hoặc gõ 'h' để hủy): ").strip().lower()
        if confirm == "h":
            continue
        run_protocol(pkey, default_port, baud, out_root, note=note)


def main():
    ap = argparse.ArgumentParser(description="Thu dữ liệu thí nghiệm Wi-Fi CSI có hướng dẫn âm thanh.")
    ap.add_argument("--port", default="COM4", help="Cổng COM của mạch thu RX (mặc định: COM4)")
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--protocol", default=None, choices=list(EXPERIMENT_SPECS),
                    help="Mã thí nghiệm (e1, e2a, e2b, e3a, e3b, e4, test30s). Bỏ trống để mở menu.")
    ap.add_argument("--empty-minutes", type=float, default=None,
                    help="Tùy chọn đổi số phút phòng trống cho e4 (ví dụ 45 hoặc 60 phút)")
    ap.add_argument("--out", default=os.path.join(HERE, "..", "data", "sessions"),
                    help="Thư mục lưu dữ liệu thực nghiệm")
    ap.add_argument("--note", default="", help="Ghi chú thêm lưu vào metadata JSON")
    args = ap.parse_args()

    if args.protocol is None:
        interactive_menu(args.port, args.baud, args.out)
    else:
        run_protocol(args.protocol, args.port, args.baud, args.out,
                     note=args.note, empty_minutes=args.empty_minutes)


if __name__ == "__main__":
    main()
