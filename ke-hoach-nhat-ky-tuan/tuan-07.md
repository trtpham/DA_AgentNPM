# Tuần 07 — Hiệu chỉnh trên tập phát triển

## Kế hoạch

- [ ] Tính confusion matrix, Precision, Recall, F1, FPR và tỉ lệ suspicious (TV3-5).
- [ ] Quét ngưỡng 0,50–0,95 riêng cho từng model trên tập phát triển.
- [ ] Kiểm tra độ tin cậy, chọn ngưỡng và đóng băng cấu hình trước khi mở tập kiểm tra.
- [ ] **Báo cáo 2 cấu hình tách biệt** (PO chốt 05/11/2026):
  - **Chỉ agent:** tắt hoàn toàn tín hiệu OSV/Registry. Mô phỏng khoảng trống zero-day, khi danh sách đen chưa biết gói; đây là con số chính của đồ án.
  - **Agent + OSV:** hiệu quả cả hệ thống.
  - Thêm chỉ số: trong các gói OSV đã biết là độc, agent tự bắt được bao nhiêu khi **không** được biết trước.
  - Lý do: phần lớn mẫu độc lấy từ Datadog/OSV. Nếu để OSV chặn sớm, Recall sẽ là thành tích của danh sách đen chứ không phải của agent (rò rỉ nhãn, AGENTS §3).
- [ ] Nguyên tắc sản phẩm **"chặn trước, phân tích sau"**: OSV báo độc thì chặn giao gói ngay, nhưng agent vẫn phân tích bản cách ly để làm phiếu báo cáo có bằng chứng và đối chiếu với OSV. Agent không được thấy kết quả OSV khi phân tích.

## Mốc nghiệm thu

Có bảng ngưỡng, lý do chọn ngưỡng và script tái hiện; không dùng tập kiểm tra để điều chỉnh.

## Nhật ký

- Ngày / người thực hiện / người kiểm tra: chưa cập nhật.
- Đã làm: chưa cập nhật.
- Kiểm chứng (lệnh và PASS/FAIL/NOT_RUN): chưa cập nhật.
- Vướng mắc / bước tiếp: chưa cập nhật.

## Ảnh kết quả

![Chưa có ảnh kết quả tuần 07](hinh-anh/chua-co-anh.svg)

*Thay ảnh này bằng ảnh kết quả thật khi có bằng chứng.*
