# AGENTS.md — Tài liệu Bàn giao Dự án cho Codex (Wi-Fi CSI Motion Detection)

Tệp này cung cấp toàn bộ ngữ cảnh dự án, cấu trúc thư mục, thông số kỹ thuật và **bộ số liệu thực nghiệm hoàn chỉnh** để **Codex** hỗ trợ người dùng soạn thảo **Slide thuyết trình** và nội dung báo cáo một cách chính xác tuyệt đối.

---

## 1. Bối cảnh Người dùng & Nguyên tắc Trình bày (RẤT QUAN TRỌNG)

- **Người thực hiện đồ án:** Sinh viên **năm nhất đại học** (First-year undergraduate student).
- **Mục tiêu bài toán:** Hệ thống **Phát hiện chuyển động người trong môi trường phòng kín (Binary Indoor Motion Detection: Có chuyển động / Không phát hiện chuyển động)** sử dụng thông tin trạng thái kênh truyền **Wi‑Fi CSI (Channel State Information)** trên 2 mạch **ESP32‑S3 (N16R8)**.
- **Yêu cầu phong cách khi làm Slide / Nội dung thuyết trình:**
  1. **Khoa học, chuyên nghiệp, trực quan, dễ bảo vệ trước hội đồng:** Giải thích bằng bản chất vật lý trực quan (sóng phản xạ đa đường trong phòng kín khi cơ thể người di chuyển làm thay đổi biên độ các sóng mang con), **KHÔNG** dùng các thuật ngữ xác suất/toán xử lý tín hiệu quá sâu (như *FPR trên từng cửa sổ phụ thuộc thời gian, p-value, định lý Nyquist-Shannon phức tạp, Z-score đa biến, Butterworth bậc cao...*) để tránh bẫy câu hỏi lý thuyết vượt quá kiến thức năm nhất.
  2. **Sử dụng thuật ngữ chuyên nghiệp:** Gọi không gian đo là **"Môi trường phòng kín trong nhà (Indoor Environment)"** hoặc **"Phòng thử nghiệm thực tế"** (tuyệt đối không dùng từ "phòng KTX / ký túc xá" trên slide).
  3. **Chỉ sử dụng số liệu thực nghiệm thật** đã thu thập và kiểm chứng bên dưới (không tự bịa số liệu). Người dùng sẽ tự vẽ biểu đồ từ các tệp CSV/Markdown đã xuất sẵn.

---

## 2. Cấu hình Phần cứng & Thuật toán Xử lý (Đã khóa cố định)

### 2.1. Phần cứng & Truyền thông
- **Thiết bị phát (TX) & Thiết bị thu (RX):** 2 bo mạch **ESP32‑S3 N16R8**, đặt ở độ cao khoảng `0.8m – 1.2m` trong phòng thử nghiệm.
- **Giao thức truyền:** **ESP‑NOW broadcast trực tiếp** giữa TX và RX (hoạt động độc lập, không phụ thuộc vào Router Wi‑Fi bên ngoài).
- **Băng tần & Kênh:** Wi‑Fi `2.4 GHz`, chuẩn `802.11n HT20`, Kênh `11`.
- **Tốc độ phát gói:** Thiết lập mục tiêu `50 Hz` (thực tế thu ổn định đạt **`50.52 – 50.73 gói/giây`** qua toàn bộ 6 thí nghiệm, tổng cộng **`121,647` gói tin**, tỉ lệ rớt gói `0%`).
- **Số kênh sóng mang con (Subcarriers):** Trích xuất **`52` sóng mang con L‑LTF** hữu ích từ `64` điểm FFT.

### 2.2. Các bước xử lý tín hiệu (Giải thích theo ngôn ngữ Sinh viên Năm nhất)
1. **Quy đổi biên độ sang đơn vị Logarit (dB):** Tính biên độ $A_k = \sqrt{I_k^2 + Q_k^2}$ của 52 sóng mang và đổi sang thang `20*log10` (dB).
2. **Chuẩn hóa độ lợi tự động (AGC offset removal):** Trừ đi mức trung vị của 52 sóng mang trong mỗi gói tin để loại bỏ hiện tượng mạch thu tự động nhảy công suất (AGC).
3. **Khử nhiễu gai & Lọc dải tần vận động (`0.3 – 6.0 Hz`):**
   - Dùng bộ lọc trung vị (Hampel/median) để cắt các gai nhiễu tức thời.
   - Giữ lại dải tần số vận động của cơ thể người (`0.3 – 6.0 Hz`), giúp **triệt tiêu nhiễu tần số cao của cánh quạt trần đang quay** và độ trôi nền chậm.
4. **Tính độ biến thiên CSI trên cửa sổ trượt:**
   - Tính độ lệch chuẩn theo thời gian trên từng sóng mang trong cửa sổ trượt, sau đó tổng hợp nhóm sóng mang nhạy nhất.
5. **Quyết định bằng Ngưỡng kép (Hysteresis) & Xác nhận liên tiếp:**
   - Tự động lấy **30 giây tĩnh đầu phiên** để đo mức nền (`baseline_median`) và độ dao động nền (`baseline_std`).
   - **Ngưỡng bật (`thr_on`):** Khi tín hiệu vượt ngưỡng bật liên tiếp đủ số nhịp xác nhận $\rightarrow$ Báo **CÓ CHUYỂN ĐỘNG**.
   - **Ngưỡng tắt (`thr_off` < `thr_on`):** Khi tín hiệu hạ xuống dưới ngưỡng tắt liên tiếp $\rightarrow$ Trả về **TRẠNG THÁI TĨNH**.

---

## 3. Vị trí các Tệp Dữ liệu & Báo cáo trong Thư mục Dự án (`e:\Wifi sensing`)

- **Bảng số liệu tổng hợp (Markdown):** `reports/experiment_results.md`
- **Bảng số liệu tiếng Việt để vẽ biểu đồ (CSV/Excel):** `reports/experiment_summary.csv`
- **Bảng thông số kỹ thuật chi tiết từng phiên (CSV):** `reports/session_metrics_raw.csv`
- **Báo cáo kiểm chứng trên bộ dữ liệu mở WiFall (10 người):** `reports/wifall_benchmark/wifall_report.md`, `reports/wifall_benchmark/wifall_by_subject.csv`, `reports/wifall_benchmark/wifall_by_activity.csv`
- **Dữ liệu gốc 6 phiên đo thực nghiệm trong nhà (`121,647` gói CSI):**
  - `data/sessions/E1/E1_baseline_3m.csv` (+ `.json`) — TN1: Điều kiện chuẩn 2.5–3m, tầm nhìn thẳng, quạt tắt (`17,080` gói)
  - `data/sessions/E2a/E2a_obstacle_4m5.csv` (+ `.json`) — TN2a: Khoảng cách xa 4–5m & vật cản nội thất (`13,342` gói)
  - `data/sessions/E2b/E2b_wall_reflection.csv` (+ `.json`) — TN2b: Tác động phản xạ đa đường gần tường chắn (`13,346` gói)
  - `data/sessions/E3a/E3a_ceiling_fan_static.csv` (+ `.json`) — TN3a: Đối chứng quạt trần Tắt vs. Bật tối đa khi tĩnh (`18,287` gói)
  - `data/sessions/E3b/E3b_ceiling_fan_walking.csv` (+ `.json`) — TN3b: Quạt trần bật tối đa + Người đi lại (`13,340` gói)
  - `data/sessions/E4/E4_empty_room_15min.csv` (+ `.json`) — TN4: Phòng trống hoàn toàn 15 phút (`46,252` gói)

---

## 4. Toàn bộ Bảng Số liệu Chuẩn để Đưa vào Slide Thuyết trình

### 4.1. Bảng Tổng hợp Chung 6 Điều kiện Thí nghiệm Trong nhà
- **Tổng số lượt đi lại đã kiểm thử:** **26/26 lượt (100.0%)** phát hiện thành công.
- **Tổng thời gian tĩnh đã đánh giá (sau khi trừ 30s lấy nền mỗi phiên):** **26.05 phút (`1,562.8` giây)** — Tổng thời gian bị báo nhầm chỉ **`25.4` giây (`1.63%`)**, độ ổn định giữ đúng trạng thái tĩnh đạt **`98.37%`**.

| Mã TN | Điều kiện thí nghiệm | Phát hiện (lượt) | Tỉ lệ báo nhầm vùng tĩnh (% thời gian & số lần) | Thời gian phản hồi TB (Nhanh–Chậm) | Dao động Tĩnh vs. Đi lại (Đỉnh) [dB] | Tỉ lệ Đi lại / Tĩnh (TB & Đỉnh) |
|---|---|---:|---:|---:|---:|---:|
| **TN1 (E1)** | **Chuẩn 2.5–3m (Quạt tắt)** | **8/8 (100%)** | **0.00%** (0 lần / 2.03p) | **3.25s** (1.9–4.0s) | `0.133` vs `0.254` (`0.508`) | TB `1.91×` — Đỉnh **`3.83×`** |
| **TN2a (E2a)** | **Xa 4–5m / Vật cản nội thất** | **6/6 (100%)** | **12.36%** (3 lần / 1.52p) | **2.37s** (0.1–3.6s) | `0.134` vs `0.247` (`0.584`) | TB `1.84×` — Đỉnh **`4.36×`** |
| **TN2b (E2b)** | **Phản xạ gần tường chắn** | **6/6 (100%)** | **8.73%** (2 lần / 1.53p) | **2.92s** (0.5–3.7s) | `0.205` vs `0.403` (`1.042`) | TB `1.96×` — Đỉnh **`5.08×`** |
| **TN3a (E3a)** | **Quạt trần (Tĩnh đối chứng)** | — (Đo tĩnh) | **0.54%** (2 lần / 4.97p) | — | Tắt: `0.094` / Bật: `0.099` | Bật/Tắt: **`1.05×` (+5%)** |
| **TN3b (E3b)** | **Quạt trần + Đi lại** | **6/6 (100%)** | **0.88%** (1 lần / 1.52p) | **4.00s** (3.4–4.3s) | `0.109` vs `0.165` (`0.450`) | TB `1.51×` — Đỉnh **`4.12×`** |
| **TN4 (E4)** | **Phòng trống 15 phút** | — (Đo tĩnh) | **0.43%** (4 lần / 14.47p) | — | Tĩnh: `0.099` | `1.00×` (Nền chuẩn) |

---

### 4.2. Bảng Chi tiết Tỉ lệ Báo nhầm và Độ ổn định trong Thời gian Tĩnh

| Mã TN | Điều kiện thí nghiệm | Tổng thời gian tĩnh đánh giá | Số lần báo nhầm (Tần suất) | Tổng số giây báo nhầm | Tỉ lệ % thời gian báo nhầm | Độ ổn định giữ đúng tĩnh (%) |
|---|---|---:|---:|---:|---:|---:|
| **TN1 (E1)** | Chuẩn 2.5–3m (Quạt tắt) | `2.03 phút` (`121.9s`) | `0 lần` (`0.00 lần/phút`) | `0.0s` | **0.00%** | **100.00%** |
| **TN2a (E2a)** | Xa 4–5m / Vật cản nội thất | `1.52 phút` (`91.4s`) | `3 lần` (`1.97 lần/phút`) | `11.3s` | **12.36%** | **87.64%** |
| **TN2b (E2b)** | Phản xạ gần tường chắn | `1.53 phút` (`91.6s`) | `2 lần` (`1.31 lần/phút`) | `8.0s` | **8.73%** | **91.27%** |
| **TN3a (E3a)** | Quạt trần (Tĩnh: 1p Tắt + 4p Bật) | `4.97 phút` (`298.4s`) | `2 lần` (`0.40 lần/phút`) | `1.6s` | **0.54%** | **99.46%** |
| **TN3b (E3b)** | Quạt trần + Đi lại | `1.52 phút` (`91.3s`) | `1 lần` (`0.66 lần/phút`) | `0.8s` | **0.88%** | **99.12%** |
| **TN4 (E4)** | Phòng trống 15 phút | `14.47 phút` (`868.2s`) | `4 lần` (`0.28 lần/phút`) | `3.7s` | **0.43%** | **99.57%** |
| **TỔNG** | **Toàn bộ 6 thí nghiệm** | **`26.05 phút` (`1,562.8s`)** | **`12 lần` (`0.46 lần/phút`)** | **`25.4s`** | **1.63%** | **98.37%** |

- **Luận điểm giải thích cực kỳ quan trọng cho Slide:**
  - Trong điều kiện tĩnh thực sự (`TN4` phòng trống 15 phút và `TN3a` bật quạt trần tối đa), hệ thống đạt độ ổn định **99.46% – 99.57%**. Các lần báo nhầm chỉ là xung nhiễu thoáng qua dài `~0.8 giây` (tổng cộng `3.7 giây` trên suốt `868.2 giây` ở `TN4`, tức chỉ `0.43%` thời gian).
  - Ở `TN2a` (`12.36%`) và `TN2b` (`8.73%`), báo nhầm rơi vào ngay đầu pha ngồi yên do khoảng cách đi lại xa (`4–5m`) và sát tường khiến người đo mất hơn `6 giây` chuyển tiếp để quay về vị trí tĩnh và ổn định tư thế (dư âm chuyển động thực).

---

### 4.3. Bảng Chi tiết Thời gian Phản hồi của Mỗi Điều kiện và Từng Lượt Đi
- **Thời gian phản hồi trung bình toàn cục:** **`3.13 giây`**.

| Mã TN | Điều kiện thí nghiệm | Số lượt phát hiện | Trung bình ± Độ lệch chuẩn | Nhanh nhất – Chậm nhất | Thời gian phản hồi từng lượt đi (`Lượt 1 → N`) |
|---|---|---:|---:|---:|---|
| **TN1 (E1)** | Chuẩn 2.5–3m (Quạt tắt) | `8/8 (100%)` | **`3.25 ± 0.64s`** | `1.90s – 4.00s` | `3.3s, 4.0s, 1.9s, 3.5s, 3.0s, 2.8s, 3.6s, 3.9s` |
| **TN2a (E2a)** | Xa 4–5m / Vật cản nội thất | `6/6 (100%)` | **`2.37 ± 1.20s`** | `0.10s – 3.60s` | `3.6s, 1.7s, 0.1s, 3.5s, 2.9s, 2.4s` |
| **TN2b (E2b)** | Phản xạ gần tường chắn | `6/6 (100%)` | **`2.92 ± 1.11s`** | `0.50s – 3.70s` | `3.7s, 3.5s, 3.1s, 3.0s, 0.5s, 3.7s` |
| **TN3b (E3b)** | Quạt trần + Đi lại | `6/6 (100%)` | **`4.00 ± 0.30s`** | `3.40s – 4.30s` | `3.9s, 4.0s, 4.2s, 4.2s, 4.3s, 3.4s` |

---

### 4.4. Bảng Chi tiết Tỉ lệ Mức Dao động Đi lại so với Tĩnh (`× lần`)

| Mã TN | Điều kiện thí nghiệm | Mức nền 30s đầu (dB) | Ngưỡng Bật `thr_on` (dB) | Ngưỡng Tắt `thr_off` (dB) | Mức Tĩnh TB (dB) | Mức Đi lại TB (dB) | Mức Đỉnh Đi lại TB (dB) | Tỉ lệ Đi lại TB / Tĩnh | Tỉ lệ Đỉnh Đi lại / Tĩnh |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **TN1 (E1)** | Chuẩn 2.5–3m (Quạt tắt) | `0.118` | `0.174` | `0.149` | `0.133` | `0.254` | `0.508` | **`1.91 lần`** | **`3.83 lần`** |
| **TN2a (E2a)** | Xa 4–5m / Vật cản nội thất | `0.108` | `0.164` | `0.140` | `0.134` | `0.247` | `0.584` | **`1.84 lần`** | **`4.36 lần`** |
| **TN2b (E2b)** | Phản xạ gần tường chắn | `0.148` | `0.236` | `0.200` | `0.205` | `0.403` | `1.042` | **`1.96 lần`** | **`5.08 lần`** |
| **TN3a (E3a)** | Quạt trần (Tĩnh) | `0.095` | `0.151` | `0.126` | `0.098` *(Tắt: `0.094`, Bật: `0.099`)* | — | — | *Quạt Bật/Tắt: **`1.05 lần`** (+5%)* | — |
| **TN3b (E3b)** | Quạt trần + Đi lại | `0.097` | `0.153` | `0.129` | `0.109` | `0.165` | `0.450` | **`1.51 lần`** | **`4.12 lần`** |
| **TN4 (E4)** | Phòng trống 15 phút | `0.099` | `0.155` | `0.131` | `0.099` | — | — | `1.00 lần` (Nền chuẩn) | — |

---

### 4.5. Bảng Số liệu Kiểm chứng Độc lập trên Bộ Dữ liệu Mở `WiFall` (10 Người, Chip ESP32‑S3)
- **Mục đích:** Bộ dữ liệu công bố quốc tế `WiFall` (thu bằng chip **ESP32‑S3**, 52 sóng mang CSI trên **10 tình nguyện viên `ID0–ID9`**) được dùng để kiểm chứng tính nhất quán của thuật toán trên nhiều vóc dáng cơ thể khác nhau.
- **Tổng số tệp kiểm chứng:** **`464/464 tệp (100.0%)`** đều vượt ngưỡng kích hoạt tham chiếu (`0.188 dB`).
- **Mức dao động trung bình toàn bộ 10 người:** **`0.685 dB`** (đỉnh trung bình **`0.882 dB`**), gấp **`5.4 lần`** mức nền tĩnh tham chiếu (`0.126 dB`).

| Nhóm phân loại | Chi tiết | Số tệp đo | Dao động TB ± SD (dB) | Dao động Đỉnh TB (dB) | Tỉ lệ vượt ngưỡng (`0.188 dB`) |
|---|---|---:|---:|---:|---:|
| **Theo hoạt động** | Đi bộ (`walk`) | 118 | `0.828 ± 0.144` | `0.992` | **118/118 (100%)** |
| **Theo hoạt động** | Bật nhảy (`Jump`) | 116 | `0.734 ± 0.216` | `0.975` | **116/116 (100%)** |
| **Theo hoạt động** | Đứng lên (`stand`) | 114 | `0.673 ± 0.233` | `0.879` | **114/114 (100%)** |
| **Theo hoạt động** | Ngồi xuống (`sit`) | 116 | `0.502 ± 0.162` | `0.679` | **116/116 (100%)** |
| **Theo 10 người** | Từ `ID0` đến `ID9` | 464 | Thấp nhất `0.516` (`ID9`) – Cao nhất `0.804` (`ID6`) | `0.649 – 0.982` | **464/464 (100%)** |
