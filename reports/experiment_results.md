# Báo cáo Tổng hợp Kết quả Thực nghiệm Phát hiện Chuyển động Wi‑Fi CSI

- **Thời điểm tổng hợp:** 2026-11-05 09:54:05
- **Tổng số lượt đi lại đã kiểm thử:** **26/26 lượt** (100.0%)
- **Tổng thời gian tĩnh đã đánh giá:** **26.05 phút (1562.8 giây)** — Thời gian bị báo nhầm: **25.4 giây (1.63%)**, Độ ổn định giữ đúng trạng thái tĩnh: **98.37%** (12 lần chớp)

## 1. Bảng tổng hợp chung qua tất cả các điều kiện thí nghiệm

| Thí nghiệm | Phát hiện (lượt) | Tỉ lệ báo nhầm vùng tĩnh (% thời gian & số lần) | Thời gian phản hồi TB (Nhanh–Chậm) | Dao động Tĩnh vs. Đi lại (Đỉnh) [dB] | Tỉ lệ Đi lại / Tĩnh (TB & Đỉnh) |
|---|---:|---:|---:|---:|---:|
| **TN1: Chuẩn 2.5–3m (Quạt tắt)** | 8/8 (100%) | 0.00% (0 lần / 2.0p) | 3.25s (1.9–4.0s) | 0.133 vs 0.254 (0.508) | TB 1.91× — Đỉnh **3.83×** |
| **TN2a: Xa 4–5m / Đồ đạc** | 6/6 (100%) | 12.36% (3 lần / 1.5p) | 2.37s (0.1–3.6s) | 0.134 vs 0.247 (0.584) | TB 1.84× — Đỉnh **4.36×** |
| **TN2b: Tường phía sau** | 6/6 (100%) | 8.73% (2 lần / 1.5p) | 2.92s (0.5–3.7s) | 0.205 vs 0.403 (1.042) | TB 1.96× — Đỉnh **5.08×** |
| **TN3a: Quạt trần (Tĩnh)** | — (Đo tĩnh) | 0.54% (2 lần / 5.0p) | — | Tắt: 0.094 / Bật: 0.099 | Bật/Tắt: 1.05× (+5%) |
| **TN3b: Quạt trần + Đi lại** | 6/6 (100%) | 0.88% (1 lần / 1.5p) | 4.00s (3.4–4.3s) | 0.109 vs 0.165 (0.450) | TB 1.51× — Đỉnh **4.12×** |
| **TN4: Phòng trống 15 phút** | — (Đo tĩnh) | 0.43% (4 lần / 14.5p) | — | Tĩnh: 0.099 | 1.00× (Nền chuẩn) |

## 2. Bảng chi tiết Tỉ lệ báo nhầm và Độ ổn định trong thời gian tĩnh

| Thí nghiệm | Tổng thời gian tĩnh | Số lần báo nhầm | Tổng số giây báo nhầm | Tỉ lệ % thời gian báo nhầm | Độ ổn định giữ đúng tĩnh (%) |
|---|---:|---:|---:|---:|---:|
| **TN1: Chuẩn 2.5–3m (Quạt tắt)** | 2.03 phút (122s) | 0 lần (0.00 lần/phút) | 0.0s | **0.00%** | **100.00%** |
| **TN2a: Xa 4–5m / Đồ đạc** | 1.52 phút (91s) | 3 lần (1.97 lần/phút) | 11.3s | **12.36%** | **87.64%** |
| **TN2b: Tường phía sau** | 1.53 phút (92s) | 2 lần (1.31 lần/phút) | 8.0s | **8.73%** | **91.27%** |
| **TN3a: Quạt trần (Tĩnh)** | 4.97 phút (298s) | 2 lần (0.40 lần/phút) | 1.6s | **0.54%** | **99.46%** |
| **TN3b: Quạt trần + Đi lại** | 1.52 phút (91s) | 1 lần (0.66 lần/phút) | 0.8s | **0.88%** | **99.12%** |
| **TN4: Phòng trống 15 phút** | 14.47 phút (868s) | 4 lần (0.28 lần/phút) | 3.7s | **0.43%** | **99.57%** |
| **TỔNG HỢP TOÀN BỘ** | **26.05 phút (1563s)** | **12 lần (0.46 lần/phút)** | **25.4s** | **1.63%** | **98.37%** |

## 3. Bảng chi tiết Thời gian phản hồi của từng lượt đi lại

| Thí nghiệm | Số lượt phát hiện | Trung bình ± Độ lệch chuẩn | Nhanh nhất – Chậm nhất | Thời gian phản hồi từng lượt đi (Lượt 1 → N) |
|---|---:|---:|---:|---|
| **TN1: Chuẩn 2.5–3m (Quạt tắt)** | 8/8 (100%) | **3.25 ± 0.64s** | 1.90s – 4.00s | `3.3s, 4.0s, 1.9s, 3.5s, 3.0s, 2.8s, 3.6s, 3.9s` |
| **TN2a: Xa 4–5m / Đồ đạc** | 6/6 (100%) | **2.37 ± 1.20s** | 0.10s – 3.60s | `3.6s, 1.7s, 0.1s, 3.5s, 2.9s, 2.4s` |
| **TN2b: Tường phía sau** | 6/6 (100%) | **2.92 ± 1.11s** | 0.50s – 3.70s | `3.7s, 3.5s, 3.1s, 3.0s, 0.5s, 3.7s` |
| **TN3b: Quạt trần + Đi lại** | 6/6 (100%) | **4.00 ± 0.30s** | 3.40s – 4.30s | `3.9s, 4.0s, 4.2s, 4.2s, 4.3s, 3.4s` |

## 4. Bảng chi tiết Tỉ lệ mức dao động Đi lại so với Tĩnh

| Thí nghiệm | Mức Tĩnh TB (dB) | Ngưỡng kích hoạt (dB) | Mức Đi lại TB (dB) | Mức Đỉnh Đi lại TB (dB) | Tỉ lệ Đi lại TB / Tĩnh | Tỉ lệ Đỉnh Đi lại / Tĩnh |
|---|---:|---:|---:|---:|---:|---:|
| **TN1: Chuẩn 2.5–3m (Quạt tắt)** | 0.133 | 0.174 | 0.254 | 0.508 | 1.91 lần | **3.83 lần** |
| **TN2a: Xa 4–5m / Đồ đạc** | 0.134 | 0.164 | 0.247 | 0.584 | 1.84 lần | **4.36 lần** |
| **TN2b: Tường phía sau** | 0.205 | 0.236 | 0.403 | 1.042 | 1.96 lần | **5.08 lần** |
| **TN3a: Quạt trần (Tĩnh)** | 0.098 | 0.151 | — | — | — | — |
| **TN3b: Quạt trần + Đi lại** | 0.109 | 0.153 | 0.165 | 0.450 | 1.51 lần | **4.12 lần** |
| **TN4: Phòng trống 15 phút** | 0.099 | 0.155 | — | — | — | — |
