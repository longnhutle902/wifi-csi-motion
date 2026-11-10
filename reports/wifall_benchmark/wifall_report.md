# Kết quả Kiểm chứng trên Bộ dữ liệu Mở WiFall (ESP32‑S3, 10 Người)

## 1. Tóm tắt chung

- **Phần cứng thu dữ liệu WiFall:** Chip ESP32‑S3, 52 kênh sóng mang CSI (tương đồng phần cứng đồ án).
- **Quy mô kiểm chứng:** **464 tệp đo** thuộc **10 người tham gia (`ID0` – `ID9`)** với 4 hoạt động vận động thường ngày (*Đi bộ, Bật nhảy, Ngồi xuống, Đứng lên*).
- **Tỉ lệ tệp có biên độ dao động vượt ngưỡng kích hoạt tham chiếu (`0.188 dB`):** **464/464 tệp (100.0%)**.
- **Mức dao động trung bình toàn bộ 10 người:** **0.685 dB** (đỉnh trung bình **0.882 dB**), cao gấp **~5.4 lần** mức nền phòng tĩnh tham chiếu (`0.126 dB`).

## 2. Thống kê theo từng loại vận động

| Hoạt động | Số tệp đo | Dao động trung bình (dB) | Dao động đỉnh TB (dB) | Tỉ lệ vượt ngưỡng tham chiếu |
|---|---:|---:|---:|---:|
| Đi bộ (walk) | 118 | 0.828 ± 0.144 | 0.992 | 118/118 (100.0%) |
| Bật nhảy (Jump) | 116 | 0.734 ± 0.216 | 0.975 | 116/116 (100.0%) |
| Ngồi xuống (sit) | 116 | 0.502 ± 0.162 | 0.679 | 116/116 (100.0%) |
| Đứng lên (stand) | 114 | 0.673 ± 0.233 | 0.879 | 114/114 (100.0%) |

## 3. Thống kê theo 10 người tham gia (`ID0` – `ID9`)

| Mã người | Số tệp đo | Dao động trung bình (dB) | Dao động đỉnh TB (dB) | Tỉ lệ vượt ngưỡng tham chiếu |
|---|---:|---:|---:|---:|
| ID0 | 16 | 0.641 ± 0.183 | 0.862 | 16/16 (100.0%) |
| ID1 | 16 | 0.572 ± 0.133 | 0.734 | 16/16 (100.0%) |
| ID2 | 320 | 0.724 ± 0.235 | 0.931 | 320/320 (100.0%) |
| ID3 | 16 | 0.596 ± 0.175 | 0.788 | 16/16 (100.0%) |
| ID4 | 16 | 0.535 ± 0.162 | 0.671 | 16/16 (100.0%) |
| ID5 | 16 | 0.589 ± 0.161 | 0.752 | 16/16 (100.0%) |
| ID6 | 16 | 0.804 ± 0.189 | 0.982 | 16/16 (100.0%) |
| ID7 | 16 | 0.574 ± 0.170 | 0.797 | 16/16 (100.0%) |
| ID8 | 16 | 0.553 ± 0.110 | 0.730 | 16/16 (100.0%) |
| ID9 | 16 | 0.516 ± 0.140 | 0.649 | 16/16 (100.0%) |

## 4. Nhận xét đưa vào Báo cáo / Thuyết trình

1. **Tính nhất quán trên nhiều vóc dáng cơ thể:** Cả 10 tình nguyện viên (`ID0` – `ID9`) đều tạo ra độ biến thiên CSI nằm trong dải cao hơn rõ rệt so với ngưỡng kích hoạt tĩnh, chứng tỏ thuật toán không phụ thuộc vào một người đo duy nhất.
2. **Phản ánh đúng quy luật vật lý:** Các chuyển động dịch chuyển toàn thân trong không gian (*Đi bộ*, *Bật nhảy*) tạo độ biến thiên sóng lớn hơn các chuyển động tại chỗ (*Ngồi xuống*, *Đứng lên*).
3. **Giới hạn của dữ liệu mở:** Bộ `WiFall` chỉ ghi các đoạn có người vận động (~3 giây/tệp), không có bản ghi phòng trống dài hạn; do đó chỉ số **báo nhầm khi tĩnh** được kiểm định trực tiếp bằng thực nghiệm trong nhà.
