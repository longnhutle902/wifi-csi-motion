# Tài liệu Bàn giao Số liệu & Hướng dẫn Làm Slide cho Codex (`HANDOFF_FOR_CODEX.md`)

Tài liệu này được chuẩn bị sẵn để bạn giao thẳng cho **Codex** (cài trên cùng máy tính, truy cập trực tiếp thư mục `e:\Wifi sensing`).
Khi mở Codex trong thư mục `e:\Wifi sensing`, Codex sẽ **tự động đọc tệp `AGENTS.md`** ở thư mục gốc và tệp này.

---

## 1. Câu lệnh (Prompt) mẫu để bạn copy dán cho Codex

Bạn chỉ cần mở **Codex** tại thư mục `e:\Wifi sensing` và nhắn câu lệnh sau:

```text
Hãy đọc tệp AGENTS.md, HANDOFF_FOR_CODEX.md và reports/experiment_results.md trong thư mục dự án. Mình là sinh viên năm nhất đại học, vừa hoàn thành toàn bộ thực nghiệm hệ thống phát hiện chuyển động trong nhà bằng Wi-Fi CSI trên 2 mạch ESP32-S3. Mình sẽ tự vẽ biểu đồ từ các bảng số liệu đã có. Nhiệm vụ của bạn là giúp mình thiết kế nội dung chi tiết cho từng Slide thuyết trình (tiêu đề, các ý gạch đầu dòng ngắn gọn trên slide, bảng số liệu cần chèn, và kịch bản lời nói thuyết trình cho từng slide) sao cho khoa học, chuyên nghiệp, dễ hiểu, đúng trình độ sinh viên năm nhất và bảo vệ vững chắc trước hội đồng.
```

---

## 2. Cấu trúc Dàn ý Slide Đề xuất (9 Slide Gọn & Chặt chẽ)

1. **Slide 1 — Tên Đề tài & Đặt vấn đề:**
   - Phát hiện chuyển động người trong môi trường phòng kín không dùng camera (đảm bảo quyền riêng tư, không phụ thuộc điều kiện ánh sáng, hoạt động qua vật cản) bằng sóng Wi‑Fi CSI trên 2 bo mạch ESP32‑S3.
2. **Slide 2 — Nguyên lý Vật lý Trực quan (Dành cho Sinh viên Năm nhất):**
   - Sóng Wi‑Fi truyền từ mạch Phát (TX) sang mạch Thu (RX) theo đường truyền thẳng (LOS) và phản xạ đa đường qua tường/nội thất.
   - Khi phòng tĩnh: 52 sóng mang con giữ biên độ ổn định.
   - Khi có người di chuyển: Cơ thể người làm xáo trộn các tia phản xạ đa đường $\rightarrow$ biên độ 52 sóng mang dao động mạnh.
3. **Slide 3 — Quy trình Xử lý Tín hiệu 4 Bước:**
   - Thu gói tin CSI ở tốc độ `~50.7 gói/giây` (ESP‑NOW kênh 11) $\rightarrow$ Chuẩn hóa biên độ dB & khử nhảy bậc AGC $\rightarrow$ Lọc dải tần chuyển động người (`0.3 – 6.0 Hz`, triệt tiêu nhiễu quạt trần) $\rightarrow$ Tính độ biến thiên trên cửa sổ trượt và quyết định bằng **Ngưỡng kép (Bật/Tắt)**.
4. **Slide 4 — Thiết kế 6 Kịch bản Thực nghiệm Trong nhà & Kiểm chứng Dữ liệu Mở:**
   - Tổ chức bài bản từ điều kiện chuẩn (`TN1`), thử thách khoảng cách xa & vật cản nội thất (`TN2a`), phản xạ gần tường chắn (`TN2b`), đối chứng nhiễu quạt trần (`TN3a`, `TN3b`), độ ổn định dài hạn (`TN4` – 15 phút phòng trống), kết hợp kiểm chứng độc lập trên 10 người (`WiFall`).
5. **Slide 5 — Kết quả Thực nghiệm Chuẩn (`TN1`) & Ảnh hưởng Khoảng cách, Tường chắn (`TN2a`, `TN2b`):**
   - Phát hiện **100% số lượt đi lại** (`8/8` ở TN1, `6/6` ở TN2a, `6/6` ở TN2b).
   - Hiệu ứng bức tường phía sau (`TN2b`) tạo phản xạ đa đường giúp đỉnh tín hiệu khi đi lại tăng vọt lên **`1.042 dB` (gấp `5.08 lần` mức tĩnh)**.
6. **Slide 6 — Kết quả Chống nhiễu Quạt trần (`TN3a`, `TN3b`) & Độ ổn định 15 phút (`TN4`):**
   - Khi bật quạt trần tốc độ tối đa ở trạng thái tĩnh (`TN3a`), mức dao động chỉ nhích nhẹ từ `0.094 dB` lên `0.099 dB` (**tỉ lệ `1.05×`, chỉ +5%**), nằm sâu dưới ngưỡng kích hoạt (`0.151 dB`).
   - Khi vừa bật quạt trần tối đa vừa đi lại (`TN3b`), hệ thống vẫn bắt trúng **6/6 lượt (100%)**, đỉnh vọt gấp **`4.12 lần`** mức tĩnh.
   - Trong 15 phút phòng trống (`TN4`), độ ổn định giữ đúng trạng thái tĩnh đạt **`99.57%`** (chỉ báo nhầm `3.7 giây / 868 giây = 0.43%`).
7. **Slide 7 — Tổng hợp 3 Chỉ số Đánh giá Chính (Tỉ lệ Đi lại/Tĩnh, Thời gian Phản hồi, Độ ổn định Tĩnh):**
   - Chèn bảng tổng hợp 6 điều kiện: Tỉ lệ Đỉnh Đi lại / Tĩnh đạt **`3.83× – 5.08×`**; Thời gian phản hồi trung bình **`3.13 giây`**; Độ ổn định tĩnh toàn cục đạt **`98.37%`**.
8. **Slide 8 — Kiểm chứng Độ nhất quán trên 10 Người (Bộ dữ liệu mở `WiFall`):**
   - Kiểm chứng trên `464` tệp đo của `10` tình nguyện viên (`ID0–ID9`): **464/464 tệp (100%)** đều vượt ngưỡng kích hoạt, mức dao động trung bình `0.685 dB` (gấp `5.4 lần` nền tĩnh).
9. **Slide 9 — Kết luận, Hạn chế & Hướng phát triển:**
   - Hệ thống đạt 100% phát hiện theo lượt di chuyển, chống nhiễu quạt trần hiệu quả, chạy thời gian thực trên vi điều khiển ESP32‑S3.
   - Hạn chế trung thực: Độ trễ phát hiện khoảng `~3 giây` (do đánh đổi để lọc nhiễu gai) và khi người vừa di chuyển từ xa về vị trí nghỉ cần vài giây để trường sóng ổn định lại.

---

## 3. Danh mục Tệp Số liệu Sạch trong `reports/` (Để Tự Vẽ Biểu đồ)

1. **`reports/experiment_results.md`** — Chứa trọn bộ 4 bảng số liệu Markdown của 6 thí nghiệm trong nhà.
2. **`reports/experiment_summary.csv`** — Tệp bảng tính CSV tiếng Việt (UTF‑8 BOM, mở trực tiếp bằng **Excel / Google Sheets / Origin**) chứa đầy đủ các cột số liệu đã làm tròn để bạn tự vẽ biểu đồ.
3. **`reports/session_metrics_raw.csv`** — Bảng thông số kỹ thuật gốc của từng phiên đo.
4. **`reports/wifall_benchmark/wifall_report.md`**, **`wifall_by_subject.csv`**, **`wifall_by_activity.csv`** — Bảng số liệu thống kê 10 người (`ID0–ID9`) và 4 hoạt động của bộ dữ liệu `WiFall`.
