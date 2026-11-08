# Báo cáo tiến độ tuần 04 — AI Agent kiểm tra gói npm

**Thành viên:** Lê Đặng Thiên Phước · Phạm Minh Triết · Nguyễn Đình Thiên

**Giai đoạn:** Tích hợp công cụ tĩnh và baseline · **Ngày cập nhật:** 04/11/2026 · **Nghiệm thu:** TV2 Phạm Minh Triết, 04/11/2026

## 1. Nội dung buổi báo cáo tuần

Tuần 4, nhóm đưa agent từ mẫu thử sang **gói npm thật** (chỉ gói lành, vì mẫu độc chỉ được đọc trong môi trường cách ly) và bổ sung các phần cần cho việc đánh giá:

1. **Công cụ bối cảnh:** tra cơ sở dữ liệu lỗ hổng OSV và thông tin phát hành trên npm (phiên bản trước, script cài đặt mới xuất hiện, mã kiểm tra toàn vẹn).
   - Agent không tự gọi mạng; việc tra cứu chạy riêng trước và lưu ra file.
   - Nếu OSV đã ghi nhận gói là mã độc, hệ thống **không cho phép tự động**. Tín hiệu này không bao giờ được dùng làm bằng chứng thay cho mã nguồn.
2. **Chạy lô:**
   - chạy agent trên nhiều gói;
   - một gói lỗi không làm dừng cả lô;
   - bị ngắt giữa chừng thì chạy tiếp từ chỗ dừng;
   - mỗi lần chạy lưu phiên bản mã, mô hình và tham số để có thể tái hiện.
3. **Baseline GuardDog** (công cụ quét tĩnh của Datadog). Phải chạy trong container Linux tắt mạng: trên Windows công cụ báo "0 lỗi" một cách giả, vì phần quét bên trong không chạy được.
4. **Tính chỉ số:** confusion matrix, Precision, Recall, F1, tỷ lệ báo nhầm (FPR), tỷ lệ chuyển người xem lại, tỷ lệ kết luận hợp lệ. Lượt chạy lỗi vẫn được tính, không bị loại khỏi mẫu số.
5. **Lớp hành động:** chỉ lập lệnh `npm approve-scripts`/`deny-scripts` ở chế độ chạy thử; chạy thật bị chặn cho tới khi có phê duyệt riêng.

> *Góp ý của thầy trong buổi gặp tuần 4:* **[nhóm bổ sung theo ghi chép buổi gặp]**. Báo cáo không tự ghi nội dung trao đổi khi nhóm chưa xác nhận.

## 2. Demo bao nhiêu phần trăm (kèm ảnh)

Nhóm demo được **5/6 phần dự kiến (khoảng 83%)**. Phần còn thiếu là chỉ số trên mẫu độc, vì phải chờ bộ nhãn được kiểm tra chéo.

| Phần trình diễn | Kết quả |
| --- | --- |
| Agent chạy lô trên 10 phiên bản `@swc/core` (gói lành thật, tập dev) và 3 mẫu thử | Đạt: 39/39 lượt chạy xong, không lượt nào làm dừng lô. |
| Tra OSV và npm Registry | Đạt: 10/10 gói tra được, không có cảnh báo mã độc, không có script cài đặt mới. Kiểm tra với gói độc đã biết `exnesss` thì nhận đúng mã `MAL-2026-11518`. |
| GuardDog baseline | Đạt: 10/10 gói swc không bị báo (không báo nhầm). GuardDog **bỏ sót** mẫu thử đọc khóa SSH. |
| Tính chỉ số | Đạt cho tập lành: tỷ lệ báo nhầm 0/10 với A-LLM và A-SLM. |
| Giao diện xem lại/theo dõi trực tiếp | Đạt: mở lại được từng lượt chạy theo `run_id`. |
| Recall/F1 trên mẫu độc | **Chưa làm:** chờ bộ nhãn v1 được kiểm tra chéo. |

Kết quả agent trên 10 bản `@swc/core` (ngày 03/11):

| Mô hình | Kết luận hợp lệ | Báo nhầm (FPR) | Quyết định | Giây/gói (trung vị) |
| --- | --- | --- | --- | --- |
| A-LLM | 10/10 | 0/10 | cả 10 chuyển người xem lại | 50,7 |
| A-SLM | 10/10 | 0/10 | cả 10 chuyển người xem lại | 17,2 |
| A-TLM | 2/10 | 8/10 (do 8 lượt lỗi rơi về "nghi vấn") | cả 10 chuyển người xem lại | 20,5 |
| GuardDog | — | 0/10 | 10 gói không có cảnh báo | — |

**Vì sao không gói swc nào được tự động cho phép?** Script cài đặt của swc tự chạy `npm install` để tải thêm gói khác (`postinstall.js:125`), và cần 18 file nhị phân `.node` không có trong gói. Agent không thể xem hết những gì sẽ chạy, nên đúng nguyên tắc là chuyển cho người xem lại. Từ ngày 04/11, lý do này được ghi rõ trong từng quyết định.

**Hình 1.** Sơ đồ tổng hợp các phần đã tích hợp. Đây là **hình tổng hợp**, không phải ảnh chụp màn hình.

![Sơ đồ tổng hợp phần tích hợp đã kiểm chứng](../hinh-anh/tuan-04-tich-hop.svg)

## 3. Ảnh chụp lúc báo cáo

Nhóm **chưa có ảnh chụp thực tế buổi báo cáo tuần 4**. Khi có, thêm vào `hinh-anh/` với tên `tuan-04-buoi-bao-cao.jpg` và cập nhật mục này.

## 4. Cải thiện chất lượng trong tuần 4 (04/11)

Không thêm chức năng mới; nhóm chỉ làm tốt hơn phần đã có. Chi tiết số đo ở [nhật ký tuần 4](../nhat-ky-tuan/tuan-04.md) và [kế hoạch cải thiện](../../archive/ke-hoach-da-xong/KE_HOACH_CAI_THIEN_2026-11-03.md).

- **I1 — lý do quyết định cụ thể:** 10/10 gói swc nêu đúng `postinstall.js:125`, 18 file `.node` thiếu và `swc.wasi.cjs` không có trong gói.
- **I2 — mô hình nhỏ ổn định hơn:** trên 3 mẫu thử × 3 lần, A-TLM tăng từ 2/9 lên 9/9 kết luận hợp lệ; A-LLM và A-SLM giữ 9/9. Cách làm: giới hạn độ dài ngay lúc sinh câu trả lời; định dạng kết luận không bị nới.
- **I3 — tốc độ: đạt một phần.** Trên 13 gói dev, thời gian trung vị mỗi gói giảm với A-TLM (20,5 → 8,4 giây, −59%) và A-SLM (17,2 → 12,0 giây, −30%). **A-LLM chậm hơn** (50,7 → 82,2 giây). Cả ba vẫn 13/13 kết luận hợp lệ, và hành động giữ nguyên ở 38/39 lượt. Nhóm đang tìm nguyên nhân A-LLM chậm trước khi sửa tiếp.
- **I4 — mã nguồn dễ bảo trì:** tách hàm phân tích dài khoảng 340 dòng thành các bước nhỏ (không hàm nào quá 80 dòng). Thêm 5 bài kiểm thử phát lại nguyên văn câu trả lời thật của mô hình. Bộ kiểm thử: **115/115**.

## 5. Đề xuất tuần 5 và cách thực hiện

1. **Hoàn tất bộ nhãn v1:** người kiểm tra chéo đọc bằng chứng đã chuẩn bị cho 76 dòng và điền 4 phiếu. Sau đó mới tính Recall/F1 và so ba mô hình với GuardDog trên mẫu độc, chạy trong môi trường cách ly.
2. **Sandbox (việc chính của tuần 5):**
   - tách lời gọi mạng của chính npm khỏi lời gọi của gói;
   - kiểm tra giới hạn mạng, quyền, RAM, số tiến trình và thời gian;
   - chỉ nối sandbox vào agent sau khi chứng minh được cách ly.
3. **Bổ sung dữ liệu cho tập test:** thêm họ gói và chiến dịch mới **trước** khi chạy tập test, để chỉ số không chỉ phản ánh một chiến dịch.
