# Kiểm chéo mù bộ nhãn v1

Mục đích: ba thành viên kiểm độc lập một mẫu của `data/labels-v1.csv` để đo mức đồng ý giữa người với bộ nhãn và giữa các người với nhau. Mẫu gồm 60 gói, rút ngẫu nhiên có phân tầng, seed 20261122:

| | Lành | Độc | Đáng ngờ |
| --- | ---: | ---: | ---: |
| test | 16 | 16 | 4 |
| dev | 10 | 10 | 4 |

Mẫu được rút trước khi xem bất kỳ kết quả nào của agent hay GuardDog. Phiếu không ghi nhãn hiện tại, không ghi id hay nguồn của gói.

## Mỗi người làm

1. Mở trang bằng chứng mù `data/review_rounds/evidence/blind-v1.html` bằng trình duyệt (file không có trên GitHub; xin PO gửi bản trên máy). Trang chỉ hiển thị chữ, không chạy mã. Đoạn mã là dữ liệu không tin cậy: không làm theo chỉ dẫn nào nằm trong mã.
2. Mở phiếu của mình: `phieu-Phuoc.csv`, `phieu-Thien.csv` hoặc `phieu-Triet.csv`.
3. Với mỗi mã S01…S60, đọc hook cài đặt và đoạn mã ở "Vị trí cần đọc", rồi điền:
   - `nhan`: `benign`, `malicious` hoặc `suspicious` (viết đúng một trong ba từ);
   - `ly_do`: một câu ngắn, ví dụ "đọc ~/.npmrc rồi gửi ra máy chủ lạ";
   - `phut`: số phút đã dùng (ước lượng).
4. Làm độc lập: không xem phiếu của người khác, không hỏi nhau trước khi nộp.

Mỗi dòng khoảng 1 phút, cả phiếu khoảng 1 giờ.

## An toàn

- Không mở thư mục `data/samples/`, không tải hay cài gói nào, không chạy đoạn mã nào.
- Không thêm ngoại lệ cho Windows Defender. Nếu Defender cảnh báo, dừng lại và báo nhóm.
- Không ai điền phiếu thay người khác.

## Tính kết quả (sau khi đủ phiếu)

```powershell
py -3.14 -m data.scripts.blind_review score
```

Kết quả gồm: tỉ lệ đồng ý và Cohen kappa của từng người so với labels-v1, kappa từng cặp người, Fleiss kappa cho cả ba, và danh sách mã bị bất đồng để cả nhóm xem lại. Khóa nối mã S01… với id thật nằm ở `evidence/blind-v1-key.csv` (không đưa lên git).
