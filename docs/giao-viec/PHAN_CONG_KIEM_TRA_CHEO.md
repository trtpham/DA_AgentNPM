# Phân công kiểm tra chéo nhãn — 15 lượt (cập nhật 08/11/2026)

**Người giao:** TV2 Phạm Minh Triết (PO) · **Căn cứ:** [kế hoạch gỡ điểm tắc](../ke-hoach/KE_HOACH_GO_STUCK_2026-11-08.md) (đã duyệt), Gate B0 08/11
**Mốc:** đóng băng nhãn v1 ngày **19/11/2026**. Cách điền phiếu: [W5-10_KIEM_TRA_CHEO_NHAN.md](W5-10_KIEM_TRA_CHEO_NHAN.md).

Claude/Codex soạn nhãn và bằng chứng nên **không** được kiểm tra. Ba người dưới đây đều khác người soạn.

## Bảng lượt

| Lượt | Nội dung | Dòng | Phút/dòng | Người | Hạn |
| --- | --- | --- | --- | --- | --- |
| 1 | Gói lành cũ (esbuild, swc) | 20 | 3 | Lê Đặng Thiên Phước | 10/11 |
| 2 | Chiến dịch `npm-token-worm-2026-03` | 18 | 2 | Nguyễn Đình Thiên | 10/11 |
| 3 | Chiến dịch `shai-hulud-2-2025-11` | 18 | 2 | Nguyễn Đình Thiên | 10/11 |
| 4 | Gói độc cũ, các họ khác | 20 | 3 | Lê Đặng Thiên Phước | 10/11 |
| 5 | Lành nháp, nhóm A (không thấy dấu hiệu rủi ro) | 40 | 2 | Phạm Minh Triết | 12/11 |
| 6 | Lành nháp, nhóm A | 40 | 2 | Nguyễn Đình Thiên | 13/11 |
| 7 | Lành nháp, nhóm A | 40 | 2 | Phạm Minh Triết | 13/11 |
| 8 | Lành nháp, "B nhẹ" (có `child_process`/gọi mạng: đọc kỹ các dòng đó) | 40 | 3 | Nguyễn Đình Thiên | 14/11 |
| 9 | Lành nháp, "B nhẹ" | 40 | 3 | Phạm Minh Triết | 14/11 |
| 10 | Độc từ Datadog (mỗi dòng một cụm khác nhau) | 40 | 2 | Lê Đặng Thiên Phước | 14/11 |
| 11 | Độc từ Datadog | 40 | 2 | Lê Đặng Thiên Phước | 15/11 |
| 12 | Độc từ Datadog | 40 | 2 | Lê Đặng Thiên Phước | 16/11 |
| 13 | Độc từ Datadog | 40 | 2 | Lê Đặng Thiên Phước | 17/11 |
| 14 | Độc từ Datadog | 40 | 2 | Nguyễn Đình Thiên | 17/11 |
| 15 | Độc từ Datadog | 40 | 2 | Phạm Minh Triết | 17/11 |
| **Tổng** | | **516** | | | |

**Khối lượng mỗi người:** Phước 200 dòng (~7 giờ) · Thiên 156 dòng (~6 giờ) · Triết 160 dòng (~6 giờ) + xử lý `revise`/`exclude` và chốt.

## Đọc gì ở mỗi loại lượt

- **Lành nháp (5–9):** nhãn `benign` là đề xuất của Claude từ phân loại tĩnh. Đọc đoạn trích: hook chạy file gì, file đó làm gì (nguồn → hành động → đích). Thấy gọi mạng, đọc secret, chạy lệnh lạ không giải thích được → `revise` (ghi nhãn đề xuất trong `note`) hoặc `exclude`.
- **Độc Datadog (10–15):** nhãn `malicious` là của Datadog (nguồn chuyên gia độc lập). Việc của bạn: xác nhận đoạn trích trên đường cài đặt cho thấy hành vi độc, và ghi hành vi đó bằng lời của bạn trong `observed_behavior`. Đoạn trích 150 dòng đầu không cho thấy gì → `exclude` kèm `note: hành vi nằm ngoài đoạn trích`.
- **Mọi lượt:** `observed_behavior` **bắt buộc** với dòng `verified` của các lượt 5–15 — đây là mô tả hành vi được ghi vào nhãn v1.

## Bằng chứng

`data/review_rounds/evidence/round-N.md`, chỉ có trên máy Triết (chứa đoạn mã độc dạng chữ; không gửi lên nhóm, không đưa lên Git). Tự kiểm trước khi báo xong:

```powershell
py -3.14 -m data.scripts.review_sheet check data/review_rounds/round-N.csv
py -3.14 -m data.scripts.data_report
```

## Sau 18/11

Triết chạy `check` cho cả 15 lượt và `data_report`; ngày 19/11 Claude chạy `freeze_labels` (chỉ lấy dòng `verified`) theo [quy trình thực nghiệm](../ke-hoach/QUY_TRINH_THUC_NGHIEM_TUAN_07_10.md).
