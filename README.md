# Hệ thống Phát hiện Chuyển động Trong nhà qua Tín hiệu Wi‑Fi CSI (2× ESP32‑S3)

Tiếng Việt · [English](README.en.md)

Hệ thống phát hiện chuyển động người trong môi trường phòng kín (**Binary Indoor Motion Detection: Có chuyển động / Trạng thái tĩnh**) sử dụng thông tin trạng thái kênh truyền **Wi‑Fi CSI (Channel State Information)** trên **2 bo mạch ESP32‑S3 N16R8** mà không cần camera hay cảm biến đeo người.

---

> Rà soát ngày 10/11/2026: đọc [CODE_REVIEW.md](reports/CODE_REVIEW.md) trước khi dùng số liệu cho slide. Mô tả DSP cũ có điểm chưa khớp code và công thức đánh giá đã được sửa. Các bảng kết quả dưới đây là bản lịch sử.

## 1. Kiến trúc Hệ thống & Thông số Kỹ thuật

- **Phần cứng:** 2 bo mạch **ESP32‑S3 N16R8** (1 mạch Phát `TX`, 1 mạch Thu `RX`), bố trí ở độ cao `0.8 – 1.2 m`.
- **Giao thức truyền thông:** **ESP‑NOW broadcast trực tiếp** giữa TX và RX ở băng tần `2.4 GHz` (`802.11n HT20`, Kênh `11`, điều chế `MCS0_LGI`), hoạt động độc lập không phụ thuộc vào Router Wi‑Fi.
- **Tốc độ lấy mẫu CSI:** Thiết lập `50 Hz` (thực tế thu ổn định đạt **`50.52 – 50.73 gói/giây`** qua toàn bộ `121,647` gói tin thực nghiệm, tỉ lệ rớt gói `0%`).
- **Không gian sóng mang:** Trích xuất biên độ của **`52` sóng mang con L‑LTF** hữu ích từ `64` điểm FFT.
- **Quy trình xử lý tín hiệu số (DSP) & Phát hiện:**
  1. **Khử nhiễu gai (Hampel)** trên biên độ, quy đổi theo `20*log10(max(A, 0.001)+2)` và trừ trung bình của 52 sóng mang trong mỗi gói để giảm nhảy bậc AGC.
  2. **Lọc thông thấp 6 Hz** để giảm nhiễu tần số cao. Code hiện không có bộ lọc thông cao 0.3 Hz.
  3. **Trích xuất độ biến thiên CSI** trong cửa sổ trượt và **quyết định bằng Ngưỡng kép thích nghi (Adaptive Dual-Threshold Hysteresis)** tự hiệu chuẩn từ `30 giây` tĩnh đầu phiên.

---

## 2. Cấu trúc Thư mục Dự án

```text
wifi-csi-motion-sensing/
├── firmware/
│   ├── csi_tx/                          # Firmware ESP-IDF cho bo ESP32-S3 Phát (TX)
│   └── csi_rx/                          # Firmware ESP-IDF cho bo ESP32-S3 Thu (RX)
├── host/
│   ├── wifisense/
│   │   ├── csi_io.py                    # Giải mã gói tin CSI (52 subcarriers L-LTF) & đọc/ghi phiên
│   │   ├── dsp.py                       # Khử AGC, lọc Hampel, lọc thông thấp 6 Hz, tính độ biến thiên CSI
│   │   ├── detectors.py                 # Bộ phát hiện chuyển động Ngưỡng kép thích nghi (Hysteresis)
│   │   └── pipeline.py                  # Luồng xử lý thời gian thực (Serial/Replay) & đánh giá Offline
│   ├── web_dashboard.py                 # Giao diện Web giám sát thời gian thực (http://localhost:8050)
│   ├── record.py                        # Công cụ thu dữ liệu thực nghiệm theo kịch bản có âm báo
│   ├── evaluate.py                      # Công cụ chấm điểm tự động và xuất bảng số liệu báo cáo
│   └── wifall_check.py                  # Công cụ kiểm chứng độc lập trên bộ dữ liệu mở WiFall (10 người)
├── data/
│   └── sessions/                        # 6 phiên dữ liệu CSI thực nghiệm (121,647 gói tin)
│       ├── E1/E1_baseline_3m.csv        # TN1: Khoảng cách chuẩn 2.5–3m, tầm nhìn thẳng (quạt tắt)
│       ├── E2a/E2a_obstacle_4m5.csv     # TN2a: Khoảng cách xa 4–5m & vật cản nội thất
│       ├── E2b/E2b_wall_reflection.csv  # TN2b: Tác động phản xạ đa đường gần tường chắn
│       ├── E3a/E3a_ceiling_fan_static.csv  # TN3a: Đối chứng nhiễu quạt trần ở trạng thái tĩnh
│       ├── E3b/E3b_ceiling_fan_walking.csv # TN3b: Di chuyển dưới nhiễu quạt trần tốc độ tối đa
│       └── E4/E4_empty_room_15min.csv   # TN4: Phòng trống liên tục 15 phút (độ ổn định dài hạn)
├── models/
│   └── motion_calib.json                # Cấu hình tham số chuẩn của bộ phát hiện chuyển động
├── reports/
│   ├── experiment_results.md            # Báo cáo tổng hợp kết quả 6 kịch bản thực nghiệm trong nhà
│   ├── experiment_summary.csv           # Bảng số liệu tổng hợp (UTF-8 CSV) phục vụ vẽ biểu đồ
│   ├── session_metrics_raw.csv          # Thông số kỹ thuật chi tiết của từng phiên đo
│   └── wifall_benchmark/                # Kết quả kiểm chứng trên bộ dữ liệu mở WiFall (464 tệp, 10 người)
├── scripts/
│   ├── build_and_flash_tx.bat           # Biên dịch và nạp firmware cho mạch Phát (TX)
│   ├── build_and_flash_rx.bat           # Biên dịch và nạp firmware cho mạch Thu (RX)
│   ├── record_session.bat               # Khởi chạy menu thu dữ liệu thực nghiệm
│   └── run_evaluation.bat               # Chạy chấm điểm tự động và cập nhật bảng kết quả
└── start_dashboard.bat                  # Khởi chạy nhanh giao diện Web Dashboard thời gian thực
```

---

## 3. Tóm tắt Kết quả Thực nghiệm Chính

- **Độ nhạy phát hiện theo lượt di chuyển:** Đạt **100% (`26/26` lượt đi lại)** qua toàn bộ các kịch bản thử nghiệm trong nhà (`E1`, `E2a`, `E2b`, `E3b`).
- **Khả năng chống nhiễu quạt trần (`E3a` & `E3b`):** Khi bật quạt trần tốc độ tối đa ở trạng thái tĩnh (`E3a`), mức dao động CSI chỉ nhích từ `0.094 dB` lên `0.099 dB` (**`1.05×`, +5%**), nằm sâu dưới ngưỡng kích hoạt (`0.151 dB`). Khi có người đi lại dưới quạt trần (`E3b`), đỉnh tín hiệu tăng gấp **`4.12 lần`** mức tĩnh và phát hiện đủ `6/6` lượt.
- **Độ ổn định dài hạn (`E4`):** Trong `14.47 phút` (`868.2 giây`) phòng trống sau hiệu chuẩn, độ ổn định giữ đúng trạng thái tĩnh đạt **`99.57%`** (chỉ xuất hiện `3.7 giây` nhiễu thoáng qua, tương đương `0.43%` thời gian).
- **Kiểm chứng độc lập trên 10 người (`WiFall` dataset):** Đạt **`464/464` tệp (`100.0%`)** vượt ngưỡng kích hoạt tham chiếu trên 10 tình nguyện viên (`ID0`–`ID9`).

---

## 4. Hướng dẫn Sử dụng Nhanh

### 4.1. Khởi chạy Giao diện Giám sát Thời gian thực (Web Dashboard)
```powershell
.\start_dashboard.bat
```
Truy cập `http://localhost:8050` trên trình duyệt để quan sát phổ sóng mang CSI, đồ thị mức độ biến thiên theo thời gian thực hoặc phát lại (Replay) các phiên dữ liệu trong `data/sessions/`.

### 4.2. Thu Dữ liệu Thực nghiệm Mới
```powershell
.\scripts\record_session.bat
```

### 4.3. Tổng hợp & Xuất Bảng Số liệu Đánh giá
```powershell
.\scripts\run_evaluation.bat
```
Kết quả sẽ được cập nhật trực tiếp tại `reports/experiment_results.md` và `reports/experiment_summary.csv`.

## 5. Cài đặt và kiểm thử

Khuyến nghị Python 3.11. DSP và bộ quyết định chạy trên máy tính; ESP32 thu/phát CSI.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe host/web_dashboard.py
```

Để tính lại vào thư mục riêng, dùng `python host/evaluate.py --out reports/review_validation`.
Firmware dùng ESP-IDF 5.3.2, target `esp32s3`. Các script `.bat` hiện dùng bộ công cụ đã cài tại `E:\WifiSensingTools`; trên máy khác có thể chạy trực tiếp các lệnh Python và `idf.py` trong môi trường tương ứng.
