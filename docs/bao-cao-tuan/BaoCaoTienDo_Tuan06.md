# Báo cáo tiến độ tuần 06 — AI Agent kiểm tra gói npm

**Thành viên:** Lê Đặng Thiên Phước · Phạm Minh Triết · Nguyễn Đình Thiên

**Giai đoạn:** Quyết định, chạy lô và chuẩn bị dữ liệu thực nghiệm · **Ngày cập nhật:** 08/11/2026; bổ sung **tiến độ 16–22/11/2026** (mục 6) · **Nghiệm thu:** TV2 Phạm Minh Triết (PO)

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

*Tình trạng 22/11:* bộ nhãn đã chốt thành labels-v1 (500 dòng, đóng băng 15/11); tập dev đã chạy xong (mục 6).

## 5. Đề xuất tuần 7 và cách thực hiện

1. **09–17/11:** cả 3 người kiểm tra chéo theo bảng phân công.
2. **19/11:** đóng băng nhãn v1 (`freeze_labels`, sàn 300 mẫu).
3. **20–23/11:** chạy 6 cấu hình và GuardDog trên dev trong container; quét ngưỡng 0,50–0,95, chọn theo luật đã ghi sẵn (0 gói độc được cho phép → F1 cao nhất); Gate đổi ngưỡng.
4. Các bước và lệnh: quy trình thực nghiệm tuần 7–10.

## 6. Tiến độ 16–22/11/2026

Ngày ghi là **ngày làm thật**. Bộ nhãn labels-v1 (500 dòng) đã đóng băng ngày 15/11 (xem mục 6 báo cáo tuần 5); bước 1–2 của mục 5 vì vậy đã xong. Mục này ghi bước 3 và các việc tồn đọng.

### Agent và GuardDog trên tập dev (20–21/11)

- 6 cấu hình (A-LLM, A-SLM, A-TLM và bản -X) chạy trên 200 gói dev (94 lành, 94 độc, 12 đáng ngờ) qua `experiments.run_isolated`: gói chỉ được giải nén và đọc trong container dùng một lần, Ollama cục bộ, quyết định dry-run, không dùng sandbox, không đụng tập test.
- GuardDog 2.6.0 chấm đủ 200/200 dòng dev (quét bù 181 dòng ngày 21/11, `reports/guarddog-v1`). Lớp dương = độc hoặc đáng ngờ, như với agent.

| Cấu hình | Precision | Recall | F1 | FPR | Chờ người xem | Giây/gói |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A-LLM (9B) | 0,750 | 0,991 | 0,854 | 0,372 | 38,5% | 27,1 |
| A-LLM-X (9B) | 0,734 | 0,991 | 0,843 | 0,404 | 38,0% | 27,3 |
| A-SLM (4B) | 0,593 | 0,991 | 0,742 | 0,766 | 71,0% | 14,6 |
| A-SLM-X (4B) | 0,607 | 0,991 | 0,753 | 0,723 | 69,0% | 14,6 |
| A-TLM (0.8B) | 0,549 | 1,000 | 0,709 | 0,926 | 92,5% | 13,4 |
| A-TLM-X (0.8B) | 0,531 | 0,877 | 0,662 | 0,872 | 94,0% | 10,5 |
| GuardDog 2.6.0 | 0,989 | 0,868 | 0,925 | 0,011 | — | — |

Nhận xét:
- Agent bắt gần đủ gói độc (Recall 0,991 ở cỡ 9B và 4B) nhưng báo nhầm nhiều gói lành (FPR 0,372 ở A-LLM). Gói lành bị báo nhầm phần lớn được **chuyển người xem**, không bị chặn: A-LLM không chặn gói lành nào.
- GuardDog chính xác hơn hẳn (FPR 0,011) nhưng bỏ sót 14 gói độc hoặc đáng ngờ.
- Không cấu hình 9B/4B nào cho phép gói độc. A-TLM-X cho phép 1 gói độc. Gói đáng ngờ `@inosx/agent-memory@0.4.0` được cho phép ở cả 4 cấu hình 9B/4B.
- Bộ công cụ mở rộng (-X) không giúp mô hình 9B trên dev (F1 0,854 → 0,843).

**Hình 3.** F1 và FPR trên tập dev labels-v1 (ngưỡng 0,8). Xanh: 6 cấu hình agent; xám: GuardDog.

![Kết quả tập dev labels-v1](../hinh-anh/tuan-06-them-ket-qua-dev.png)

### Chọn ngưỡng (21/11, Gate B0 "Khóa ngưỡng quyết định")

- Quét ngưỡng 0,50–0,95 bằng `experiments.threshold_sweep`, theo luật chọn đã ghi từ tuần 6: (1) 0 gói độc được cho phép; (2) F1 cao nhất; (3) hòa thì lấy ngưỡng cao hơn.
- F1 **không đổi** trên cả dải ngưỡng ở mọi cấu hình. Nhãn cuối chủ yếu do các luật R3, R7, R8 quyết định, không do ngưỡng tin cậy.
- Kết quả: khóa ngưỡng **0,95** cho A-LLM, A-LLM-X, A-SLM, A-SLM-X, A-TLM (commit `8398f4c`). 0,95 được chọn chỉ do luật hòa; tỉ lệ chuyển người xem tăng 1,5–3 điểm %.
- A-TLM-X cho phép 1 gói độc ở mọi ngưỡng, nên không có ngưỡng nào đạt luật. A-TLM-X **không chạy tập test**; cỡ 0.8B dùng A-TLM.

### Tập test (bắt đầu 22/11)

- GuardDog trên 300 dòng test (141 lành, 141 độc, 18 đáng ngờ), cùng cách quy đổi như dev: Precision 0,970, Recall 0,811, F1 0,884, FPR 0,028. 13/300 dòng quét lỗi, đều là gói lành.
- Agent A-LLM trên tập test đang chạy (`reports/test-v1-a-llm`), **chưa có số**.

### An toàn khi chạy lô (20–21/11)

- Windows Defender cách ly 1 file kết quả (20/11): chữ do mô hình viết trong kết luận trích lại mã độc. Sửa: trong container, mọi chữ tự do (đoạn mã gói, suy nghĩ, kết luận, lý do) được mã hóa base64 trước khi ghi về máy (commit `8ccca9c`, `5d2b7c6`; 2 Gate B0 ngày 20–21/11). Từ 21/11 không còn file nào trong `reports/` bị cách ly.
- Trình xem giải mã khi hiển thị và vẫn đọc được trace cũ (`f1f5a88`).
- Không thêm ngoại lệ Defender.

### Sandbox (20–21/11)

- Sửa phương pháp theo chẩn đoán 15/11 (`e96b9b0`, `df34fee`): gói được cài vào một dự án rỗng giống người dùng thật; bước chuẩn bị có mạng chỉ chạy `npm install --ignore-scripts`; `/tmp` thành tmpfs 64 MB không chạy được file; trace quá dài giữ cả đầu và cuối. Giữ nguyên các lớp cách ly (mạng tắt, chỉ đọc, 256 MB, 64 PID, 60 giây, canary).
- Chạy thử trên 3 gói lành dùng để chẩn đoán (`sbx-fix-benign3-1120`): 3/3 có trace đầy đủ, không chạm canary; 1/3 cài xong, 2/3 script thoát mã lỗi 1. Nguyên nhân 2 lỗi này chưa phân tích.
- Chống lỗi khi chạy lô lớn (`19c7359`, Gate 21/11): kiểm tra Docker, image và dung lượng trước khi chạy; phân loại lỗi (`fail_reason`); dọn container và volume sót; thử lại lỗi hạ tầng.
- **Pha A (sandbox trên tập dữ liệu) chưa chạy lại. Chưa có số liệu sandbox cho tập dữ liệu.**

### Trình xem và văn phòng 3D (20/11)

- Đo FPS văn phòng 3D trên 12 tình huống demo, Chrome dùng GPU tích hợp: mọi tình huống ở cả giao diện sáng và tối đều trên 30 FPS (trung bình 61–71 FPS, p5 36–48 FPS); tải xong trong 0,75–1,15 giây (`f15cb50`, `viewer/docs/do-fps-van-phong-3d.md`).
- Trình xem dễ đọc hơn: thẻ kết luận tô màu theo hành động, chữ đủ tương phản và nút đủ lớn ở cả hai giao diện (`8a6b609`, `bd3d1ec`, `fe75705`).

### Báo cáo cuối và slide (22/11)

- Điền số tập dev vào Chương 4 (bảng ngưỡng, độ chính xác, ma trận nhầm lẫn, hiệu năng, so sánh mốc với -X, FPS) và slide; các bảng tập test, OSV và sandbox còn để trống chờ số.
- Báo cáo nháp hiện 50 trang; slide 21 trang.

### Kiểm thử (22/11)

- `py -3.14 -m pytest -q`: **339 passed, 18 skipped, 1 failed**. Bài lỗi: `tests/test_trace.py::test_synthetic_samples_are_valid_and_bounded` đếm 3 trace mẫu, nhưng commit `f1f5a88` đã thêm trace mẫu thứ 4 (`assert 4 == 3`). Chưa sửa.

### Kế hoạch tuần tới

1. Chạy xong tập test: A-LLM, A-LLM-X, A-SLM, A-SLM-X, A-TLM ở ngưỡng 0,95; chấm cùng GuardDog.
2. Chạy lại sandbox pha A trên máy ảo, rồi so sánh có và không có sandbox.
3. Chạy bản có OSV và bài thử học vẹt trên tập test.
4. Điền số tập test vào Chương 4 và slide; viết Kết luận.
5. Sửa bài test trace mẫu bị lỗi.

### Còn chờ

- MSSV của Lê Đặng Thiên Phước.
- Phản hồi của giảng viên cho tuần 5 và tuần 6.
