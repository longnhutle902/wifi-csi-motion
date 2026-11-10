# Tính lại sau rà soát mã nguồn — 10/11/2026

Không sửa dữ liệu đo gốc hoặc ghi đè các bảng kết quả lịch sử trong `reports/`.
Các đầu ra tính lại nằm riêng tại `reports/review_evaluation_20261110/`
(không đưa các bảng đầu ra tái tạo được vào Git).

## Lệnh kiểm chứng

Môi trường đã chạy: `E:\WifiSensingTools\venv\Scripts\python.exe`.

```powershell
& 'E:\WifiSensingTools\venv\Scripts\python.exe' -m unittest discover -s tests -v
& 'E:\WifiSensingTools\venv\Scripts\python.exe' host/evaluate.py --out reports/review_evaluation_20261110
& 'E:\WifiSensingTools\venv\Scripts\python.exe' host/wifall_check.py --out reports/review_evaluation_20261110/wifall_benchmark
```

Bộ kiểm thử toàn dự án: **23 kiểm thử đạt**, 34.385 giây, mã thoát 0.
Riêng 8 kiểm thử đánh giá/WiFall đã được chạy trước khi sửa: 6 thất bại
khẳng định và 2 lỗi đọc/biểu đồ; sau khi sửa cả 8 đều đạt.

## Sáu phiên thực nghiệm trong nhà

Đã chạy lại đủ 6 phiên bằng bộ đệm trượt của Engine, mã thoát 0.
Phát hiện vẫn đạt **26/26 lượt**; thời gian tĩnh đánh giá vẫn **1,562.8 giây**.
Theo cách đếm đã sửa, thời gian báo nhầm là **72.1 giây (4.61%)**, gồm
**32 đoạn báo**, độ ổn định tĩnh **95.39%**. Độ trễ trung bình gộp 26 lượt
theo timestamp: **3.1396769102 giây** (làm tròn 3.14 giây).

| Phiên | Báo nhầm lịch sử: số lần / giây / % | Tính lại: số đoạn / giây / % | Độ trễ TB tính lại (s) |
|---|---:|---:|---:|
| E1 | 0 / 0.0 / 0.00 | 8 / 14.4 / 11.81 | 3.2478374839 |
| E2a | 3 / 11.3 / 12.36 | 9 / 26.1 / 28.56 | 2.3763499657 |
| E2b | 2 / 8.0 / 8.73 | 9 / 22.6 / 24.67 | 2.9065500100 |
| E3a | 2 / 1.6 / 0.54 | 0 / 0.0 / 0.00 | Không có lượt vận động |
| E3b | 1 / 0.8 / 0.88 | 6 / 9.0 / 9.86 | 3.9919166565 |
| E4 | 4 / 3.7 / 0.43 | 0 / 0.0 / 0.00 | Không có lượt vận động |
| Tổng | 12 / 25.4 / 1.63 | 32 / 72.1 / 4.61 | 3.1396769102 |

Các đoạn báo ở phần tĩnh còn lại sau vận động trước đây có thể bị loại cả
đoạn nếu bắt đầu trong lượt đi lại hoặc vùng đệm. Bản sửa tính phần giao
với vùng tĩnh được đánh giá. Mỗi đoạn giao liên tục được tính một đoạn báo;
không nhất thiết là một lần chuyển trạng thái bật mới của thiết bị.

**E3a và E4 chưa tái lập được số báo nhầm lịch sử bằng mã hiện có.** Không
quy sự giảm này cho bản sửa cách đếm: với cùng đầu ra dự đoán, phép lấy giao
không thể làm giảm thời gian báo nhầm so với cách đếm cũ. Chưa xác định đầy
đủ phiên bản mã/môi trường tạo các bảng lịch sử. Vì vậy, đây là kết quả tính
lại với mã hiện tại, không phải phép chứng minh nguyên nhân của mọi sai khác.

## WiFall

Đã xử lý lại **464 tệp**, thuộc 10 người và 4 hoạt động; lệnh hoàn tất với
mã thoát 0. Điểm trung bình và đỉnh khớp bảng lịch sử ở mức làm tròn công bố.

| Đại lượng | Báo cáo lịch sử | Tính lại |
|---|---:|---:|
| Số tệp có đỉnh vượt ngưỡng | 464/464 | 464/464 |
| Điểm trung bình (dB) | 0.685 | 0.6851258621 |
| Điểm đỉnh trung bình (dB) | 0.882 | 0.8819898707 |
| Nền tham chiếu (dB) | 0.126 | 0.1405872255563736 |
| Ngưỡng bật tham chiếu (dB) | 0.188 | 0.2155607610940933 |
| Tỉ số điểm trung bình / nền | khoảng 5.4 lần | 4.8733151917 lần |

Lần tính lại tự tải `models/motion_calib.json` đang lưu, có:

```json
{
  "win_s": 1.2,
  "hop_s": 0.1,
  "k_on": 6.5,
  "k_off": 3.8,
  "min_margin": 0.035,
  "n_on": 3,
  "n_off": 8,
  "baseline_median": 0.1405872255563736,
  "baseline_std": 0.01153439008272611,
  "calibrated": true,
  "sensitivity": "normal"
}
```

Ngưỡng tắt tương ứng: **0.1844179078707328 dB**.
Khác biệt ngưỡng và tỉ số nền xuất phát từ cấu hình đang lưu khác báo cáo cũ;
không thay đổi cấu hình để ép khớp số liệu lịch sử.

## Giới hạn khi diễn giải

- Báo nhầm phải tính cả phần tín hiệu bật kéo dài vào vùng tĩnh, sau vùng
  đệm 3 giây. Code cũ loại cả lần báo nếu bất kỳ phần nào chạm đoạn đi lại,
  vùng đệm hoặc đoạn không có nhãn; do đó có thể đếm thiếu thời gian báo nhầm.
- Một lượt được tính phát hiện khi trạng thái bật chồng lên nhãn vận động.
  Không bắt buộc có một lần chuyển mới từ tắt sang bật, nên một tín hiệu bật
  kéo dài có thể làm độ trễ của lượt sau gần 0. Đây là độ trễ theo nhãn ghi nhận,
  chưa phải phép đo đồng bộ chính xác thời điểm cơ thể bắt đầu chuyển động.
- Thời gian tĩnh tính theo số nhịp đầu ra quan sát được, mỗi nhịp 0.1 giây;
  đã loại phần lấy nền và 3 giây sau vận động. Khoảng mất đầu ra không được
  tự tính thành thời gian quan sát. Phiên không có mẫu tĩnh trả về `NaN`
  cho phần trăm báo nhầm/độ ổn định, không báo 100% ổn định.
- WiFall kiểm tra đỉnh đặc trưng trên tệp vận động, chưa kiểm tra quyết định
  ngưỡng kép và xác nhận liên tiếp. Lọc toàn tệp WiFall khác xử lý từng đệm
  của thực nghiệm chính; không dùng kết quả này làm độ chính xác nhị phân.
- Số tệp theo người không cân bằng: riêng ID2 chiếm **320/464 tệp**;
  trung bình toàn bộ tệp không phải trung bình cân bằng theo 10 người.
- Không có đoạn tĩnh trong nhóm WiFall được phân tích, nên không suy ra
  báo nhầm hoặc khả năng khái quát sang người chưa kiểm thử từ 464/464.
