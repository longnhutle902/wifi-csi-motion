# Rà soát mã nguồn — 10/11/2026

Phạm vi: firmware TX/RX, giải mã CSI, xử lý tín hiệu, bộ quyết định,
nguồn Serial/Replay, ghi phiên, dashboard và hai công cụ đánh giá.
Dữ liệu đo gốc và các bảng kết quả đã bàn giao được giữ để đối chiếu.

## Các lỗi đã sửa

- Kiểm tra chiều dài CSI khai báo và Base64 trước khi nhận gói.
- Xóa trạng thái chuyển động cũ khi đồng hồ thiết bị khởi động lại;
  reset bộ đếm khi mở phiên mới.
- Từ chối tốc độ Replay không hợp lệ và cho phép dừng ngay trong lúc chờ.
- Dashboard chỉ cập nhật bộ phát hiện khi có mẫu mới và tới nhịp xử lý;
  kết thúc hiệu chuẩn khi mất dữ liệu; đóng nguồn khi chuyển chế độ.
- Không che lỗi ghi tệp và không báo kiểm tra cổng Serial thành công khi lỗi.
- Tính báo nhầm trên phần giao giữa tín hiệu báo và vùng tĩnh được đánh giá,
  kể cả tín hiệu báo bắt đầu từ một lượt đi lại trước đó.
- Tính độ trễ từ timestamp, tổng hợp theo từng lượt; bỏ phần trăm 100% ghi cứng.
- Đọc WiFall có kiểm tra IQ, xử lý tràn bộ đếm và báo cáo đúng nhóm thực có.
- Đồng bộ cấu hình firmware với mục tiêu 50 Hz và baud host 921600.
- Bổ sung dependencies, kiểm thử hồi quy và CI cho phần host.

## Những điểm cần dùng đúng khi bảo vệ

1. **Xử lý chính chạy trên máy tính.** ESP32 TX phát gói; RX thu CSI và gửi
   qua Serial. Chưa có triển khai đầy đủ bộ lọc và bộ quyết định trên vi điều khiển.
2. **Chuỗi DSP hiện tại:** nội suy lưới xử lý 100 Hz từ gói thu khoảng 50 Hz;
   Hampel trên biên độ; `20*log10(max(A, 0.001)+2)`;
   trừ **trung bình** của 52 sóng mang trong mỗi gói; lọc thông thấp 6 Hz;
   tổng hợp độ lệch chuẩn và độ lệch trung vị trên cửa sổ.
   Code **không có** bộ lọc thông cao 0.3 Hz và không trừ trung vị theo gói.
   Nội suy không làm tăng tốc độ lấy mẫu vật lý. Không thay DSP để khớp lời mô tả,
   vì thay như vậy sẽ làm thay đổi thuật toán đã đo.
3. Bộ lọc dùng `sosfiltfilt` trên đoạn đệm hữu hạn. Đánh giá chính dùng cùng
   Engine xử lý đệm trượt, không dùng toàn bộ tương lai của phiên đo.
4. `STAT drop` là số gói bị bỏ do hàng đợi RX đầy, không đo toàn bộ mất gói
   trên đường vô tuyến. Không kết luận 0% mất gói vô tuyến từ chỉ số này.
5. WiFall chỉ kiểm tra **đỉnh điểm biến thiên vượt ngưỡng tham chiếu** trên
   các tệp hoạt động. Không có nhóm tĩnh tương ứng để suy ra độ chính xác nhị phân,
   độ báo nhầm hay khả năng nhận diện người. Cấu hình hiện lưu trong
   `models/motion_calib.json` khác nền/ngưỡng tham chiếu của báo cáo WiFall cũ;
   cần lưu kèm cấu hình với mỗi lần tính lại.
6. Đánh giá có vùng đệm sau vận động. Mẫu bị loại khỏi mẫu số tĩnh cần được
   công bố; phần báo kéo dài ngoài vùng đệm vẫn phải được tính là báo nhầm.
   Giải thích do người ổn định tư thế là giả thuyết, chưa có video đo đồng bộ để chứng minh.
7. `first_word_invalid` của ESP-IDF có thể ảnh hưởng bin L-LTF gần đầu đệm.
   Chưa thay tập 52 bin của thực nghiệm; đây là giới hạn cần khảo sát riêng.

## Kiểm chứng

Chạy `python -m unittest discover -s tests -v` và
`python -m compileall -q host`. Kết quả tính lại được lưu riêng trong
`reports/review_evaluation_20261110/`, không ghi đè bảng lịch sử.
Xem [bảng đối chiếu tính lại](REVALIDATION_20261110.md): 26/26 lượt,
72.1 giây báo nhầm trên 1562.8 giây tĩnh (4.61%), ổn định tĩnh 95.39%.
Build firmware không thay thế thử nghiệm trực tiếp trên hai bo mạch;
không nạp lại firmware trong đợt rà soát này.
