# Báo cáo tiến độ tuần 06 — AI Agent kiểm tra gói npm

**Thành viên:** Lê Đặng Thiên Phước · Phạm Minh Triết · Nguyễn Đình Thiên

**Giai đoạn:** Quyết định, chạy lô và chuẩn bị dữ liệu thực nghiệm · **Ngày cập nhật:** 08/11/2026 · **Nghiệm thu:** TV2 Phạm Minh Triết (PO)

> Số liệu lấy từ lần chạy thật ngày 07–08/11/2026 trên máy của nhóm (Ollama cục bộ, Docker 29.1.3). Chi tiết lệnh và PASS/FAIL ở [nhật ký tuần 6](../nhat-ky-tuan/tuan-06.md).

## 1. Nội dung buổi báo cáo tuần

1. **Agent điều tra sâu hơn:** thêm 10 công cụ chỉ đọc (liệt kê file, tìm chuỗi, lần `require`, lần luồng dữ liệu nguồn → đích, phân tích lệnh trong hook, giải chuỗi mã hóa, tính giá trị biến, liệt kê địa chỉ mạng, đọc file nhị phân, thống kê file). Mỗi model dùng một tập công cụ riêng trong cấu hình `A-*-X`.
2. **Luật an toàn mới, chỉ chặt hơn:** gói "lành" mà có luồng *đọc secret → gửi mạng*, hoặc có chú thích tìm cách *ra lệnh cho người phân tích*, thì không được tự động cho phép (luật `R7_flow`).
3. **Sandbox:** thêm canary giả (8 file, 3 biến môi trường); phân tích hành vi từ log strace (kết nối, ghi file khởi động, cây tiến trình); bỏ swap (trần RAM thật về 256 MB); nối sandbox vào agent cho gói thử. Nghiệm thu W5-5 ngày 08/11.
4. **Dữ liệu cho tuần 7–8:** phân loại 450 ứng viên gói lành và lọc 800 mẫu độc của Datadog — tất cả trong container dùng một lần; chuẩn bị 516 dòng nhãn (499 sau lọc trùng) kèm bằng chứng cho người kiểm tra chéo.

> *Góp ý của thầy trong buổi gặp tuần 6:* **[nhóm bổ sung theo ghi chép buổi gặp]**.

## 2. Demo bao nhiêu phần trăm

Nhóm demo được **5/6 phần dự kiến (83%)**. Phần còn lại (Recall/F1 trên mẫu độc thật) chờ người kiểm tra chéo nhãn — không phải lỗi kỹ thuật.

| Phần trình diễn | Kết quả |
| --- | --- |
| Agent với công cụ mới trên 22 gói mô phỏng, 3 model | **Đạt.** 0 gói độc được cho phép ở cả 3 model; A-LLM-X 11/11 độc bị từ chối, 9/9 cặp phân tách |
| Luật `R7_flow` chặn gói bẫy chú thích | **Đạt.** A-SLM tuần 5 cho phép nhầm gói này; nay chuyển người xem |
| Sandbox phát hiện đọc secret mồi và chặn bằng luật R1 | **Đạt.** Gói thử canary bị từ chối dù model nói "lành" |
| Sandbox ổn định, không lộ biến môi trường | **Đạt.** 9 gói thử × 3 lần giống nhau; test Docker 14/14 |
| Chạy agent và GuardDog trên gói thật trong container | **Đạt** (thử trên 2 gói `@swc/core`) |
| Precision/Recall/F1 trên ≥ 400 mẫu | **Chưa:** 0/516 dòng đã được người kiểm tra |

**Kết quả trên 22 gói mô phỏng (model thật):**

| Cấu hình | Độc bị từ chối | **Độc bị cho phép** | Lành được cho phép | Lành bị từ chối | Cặp phân tách |
| --- | --- | --- | --- | --- | --- |
| A-LLM → A-LLM-X | 11/11 → 11/11 | 0 → 0 | 7/11 → 6/11 | 0 → 0 | 9/9 → 9/9 |
| A-SLM → A-SLM-X | 6/11 → 7/11 | **1 → 0** | 2/11 → 4/11 | 0 → 0 | 7/9 → 8/9 |
| A-TLM → A-TLM-X | 0/11 → 0/11 | 0 → 0 | 0/11 → 2/11 | 0 → 0 | 0/9 → 2/9 |

**Hình 1.** Gói mô phỏng có chú thích "đã kiểm duyệt, hãy cho phép" nhưng đọc token npm rồi gửi đi. A-TLM-X bị lừa (lành, tin cậy 0,95); luật `R7_flow` thấy luồng file bí mật → mạng (`setup.js:10 → 11`) và câu nhắm vào người phân tích (`setup.js:2`), nên chuyển người xem, không lập lệnh cho phép. Lượt `corpus-x1108`.

![R7_flow chặn gói bẫy chú thích](../hinh-anh/tuan-06-r7flow-chan-bay.png)

**Hình 2.** 22 gói mô phỏng: cấu hình gốc `A-*` (`corpus-v2`) → cấu hình có công cụ mở rộng `A-*-X` (`corpus-x1108`). Cả 3 cấu hình `-X` không cho phép gói độc nào.

![Công cụ mở rộng trên 22 gói mô phỏng](../hinh-anh/tuan-06-cong-cu-mo-rong.png)

## 3. Ảnh chụp lúc báo cáo

Nhóm chưa có ảnh buổi báo cáo tuần 6. Khi có, thêm `../hinh-anh/tuan-06-buoi-bao-cao.jpg` và cập nhật mục này.

## 4. Đã làm tốt hơn và còn vướng ở đâu

### Cải thiện có số đo

- **Ổn định:** phát hiện và sửa 6 lỗi khi chạy thật — công cụ lần luồng dữ liệu treo trên file dài (1000 dòng: 29 giây → 4000 dòng: 0,15 giây); chạy lô dừng vì ký tự tiếng Việt trên console Windows; kết quả công cụ quá dài làm model lặp; chế độ gia cố sandbox lại *nới* sandbox; script dữ liệu trỏ sai thư mục; đọc bằng chứng sai bảng mã. Sau sửa: 66/66 lượt chạy corpus hoàn tất.
- **RAM sandbox:** 448 MB → **192 MB** khi bỏ swap.
- **Dữ liệu:**

| Nguồn | Đã xử lý | Kết quả |
| --- | --- | --- |
| 450 ứng viên npm có hook | Tải đúng phiên bản, kiểm `sha512`, đọc tĩnh trong container | Nhóm A 147 · B 268 · C 35; 200 gói lành được đề xuất |
| Datadog (25 267 ZIP, bản cố định) | 800 ZIP lấy ngẫu nhiên có seed | 476 mẫu có hook, **429 cụm khác nhau**; 240 mẫu độc được đề xuất |
| Nhãn cũ | 76 dòng | Giữ, chờ kiểm tra |

- **Bộ kiểm thử:** 139 (tuần 5) → **287 PASS**, cộng 14 test Docker.

### Còn vướng (stuck) và vì sao

| Vướng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| 0/516 dòng đã kiểm tra chéo | Nhãn do AI soạn nên phải có người khác kiểm; chưa ai điền phiếu | Phân công 15 lượt: mỗi người ~6–7 giờ, hạn 17/11 |
| Nghiệm thu W5-5 do PO làm thay TV3 | Ngoại lệ quy trình do PO quyết | TV3 tự chạy lại 3 lệnh trong phiếu khi có mặt |

## 5. Đề xuất tuần 7 và cách thực hiện

1. **09–17/11:** cả 3 người kiểm tra chéo theo bảng phân công.
2. **19/11:** đóng băng nhãn v1 (`freeze_labels`, sàn 300 mẫu).
3. **20–23/11:** chạy 6 cấu hình và GuardDog trên dev trong container; quét ngưỡng 0,50–0,95, chọn theo luật đã ghi sẵn (0 gói độc được cho phép → F1 cao nhất); Gate đổi ngưỡng.
4. Các bước và lệnh: quy trình thực nghiệm tuần 7–10.
