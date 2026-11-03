# Tuần 05 — Hoàn thiện sandbox và công cụ mở rộng

## Kế hoạch

- [ ] Kiểm tra giới hạn mạng, quyền, RAM, PID, thời gian và dữ liệu mồi của sandbox.
- [ ] Chuẩn hóa kết quả tiến trình, file và kết nối thành JSON có thể đối chiếu với mã nguồn.
- [ ] Chỉ nối `run_sandbox` vào agent sau khi chứng minh cách ly bằng mẫu mô phỏng.
- [ ] Bổ sung làm rõ mã bị rối khi cần; không mở rộng quá phạm vi install script.

## Mốc nghiệm thu

Sandbox trả kết quả có thể tái hiện và không chạm secret thật; lỗi sandbox không làm agent tự approve.

## Nhật ký

- **Ngày / người thực hiện / người kiểm tra:** 2026-11-04 / Claude, cải thiện I1 theo [kế hoạch cải thiện](KE_HOACH_CAI_THIEN_2026-11-03.md) và Gate B0 ngày 03/11 / chờ TV2 review.
- **Đã làm (I1 — lý do quyết định cụ thể; không đổi luật approve/deny, không đổi schema):**
  - `extract_indicators` trả thêm `incomplete`: các file `.node` không có trong gói (gộp thành một dòng), file nguồn không đọc được, chạm giới hạn độ sâu require, 30 chỉ báo hoặc 100 file.
  - Chỉ báo mới `external_install` cho lệnh tải mã ngoài nằm trong mã nguồn, ví dụ ``execSync(`npm install …`)``.
  - `R7_review` liệt kê nguyên nhân, kể cả dòng hook trong `package.json` gọi mã ngoài gói.
- **Kiểm chứng:** pytest 99 → **104 PASS**; Semgrep `--config auto --error` exit 0; `git diff --check` PASS.
- **Số đo trước/sau trên 13 gói dev (10 `@swc/core` + 3 fixture):**

| Chỉ số | Trước (`week4-dev-*`) | Sau (`i1b-dev-*`) |
| --- | --- | --- |
| swc ra `review` có lý do nêu `postinstall.js:125` và file `.node` thiếu | 0/10 (chỉ ghi "Install path not fully reviewed") | A-LLM 10/10, A-SLM 10/10 |
| Giữ nguyên nhãn, hành động, luật cuối | — | A-LLM 13/13; A-SLM 12/13 |
| Bước TB / giây trung vị mỗi gói | A-LLM 2.8 / 49.9; A-SLM 3.5 / 15.6 | A-LLM 2.3 / 46.3; A-SLM 3.5 / 28.5 |

- **Ghi chú trung thực:**
  - Ca lệch duy nhất là A-SLM trên fixture no-hook: từ `suspicious/review` (R8) sang `benign/review` (R7_review). Hành động vẫn là `review`. Nhãn đổi vì danh sách chỉ báo gửi cho model nay có thêm trường `incomplete`, nên model đề xuất khác; luật quyết định không đổi.
  - Lý do mới làm lộ thêm một nguyên nhân thật trước đây bị che: `swc.wasi.cjs` không có trong tarball.
  - Thời gian A-SLM tăng chủ yếu do máy đang chạy song song việc khác; chưa kết luận về tốc độ (việc của I3).
  - Lô A-LLM bị ngắt hai lần khi phiên làm việc khởi động lại; chạy lại cùng `run_id` đã bỏ qua 11 gói xong và chỉ chạy 2 gói còn lại, xác nhận cơ chế resume của `run_batch`.
- **Bước tiếp:** I5 (tách lời gọi mạng của npm trong sandbox) hoặc I4 (tách hàm + test phát lại) theo trình tự của kế hoạch; cả hai cần PO duyệt.

## Ảnh kết quả

![Chưa có ảnh kết quả tuần 05](hinh-anh/chua-co-anh.svg)

*Thay ảnh này bằng ảnh kết quả thật khi có bằng chứng.*

### Cập nhật 2026-11-04 — I2, I3, I4 (Claude, Gate B0 ngày 04/11)

- **I4 — tách hàm và test phát lại: PASS.**
  - `analyze()` (khoảng 340 dòng) được tách thành lớp `_Session` với các bước `prepare`, `ask`, `run_tools`, `parse`, `verify`, `finish`, `repair`. Hàm dài nhất trong `agent/run.py` còn 51 dòng; có test chặn hàm trên 80 dòng.
  - `tests/test_replay.py` phát lại nguyên văn 5 bản ghi phản hồi thật của Ollama (3 thành công, 2 thất bại cũ của A-TLM) và ra đúng luật cuối như lượt chạy live.
  - Bộ test: **115/115 PASS**; Semgrep exit 0.
- **I2 — ổn định model nhỏ: PASS.**
  - Schema gửi cho Ollama được thêm giới hạn để decoding có ràng buộc tự dừng: `description` ≤ 75 ký tự; tối đa 3 behavior; `evidence.lines` sinh dưới dạng số nguyên, vì grammar của Ollama không áp `pattern` và trước đó model ghi cả đoạn mã vào ô này.
  - `Verdict` vẫn kiểm tra đủ mọi quy tắc cũ.
  - Lời nhắc sửa liệt kê đúng các file đã đọc.

| Mẫu thử 3 × 3 lần | Mốc (`i2base`) | Sau (`i3b`) |
| --- | --- | --- |
| A-TLM hợp lệ | 2/9 | **9/9** (6,0 giây TB) |
| A-SLM hợp lệ | 9/9 | 9/9 (9,1 giây TB) |
| A-LLM hợp lệ | 9/9 | 9/9 (27,9 giây TB) |

  - Ghi chú: trên fixture canary (đọc khóa SSH, in biến môi trường, không gửi đi đâu), A-SLM và A-TLM nay ra `suspicious/review` thay vì `malicious/deny`. Theo AGENTS §3 (không có đích gửi ra ngoài), nhãn này vẫn hợp lý và hành động cuối vẫn an toàn.
- **I3 — tốc độ: CHƯA ĐẠT với A-LLM (đã đo xong lần 2).**
  - Trace `run_end` giờ có `prompt_tokens`, `output_tokens`, `tokens_per_s`; danh sách chỉ báo trong prompt được rút gọn thành dòng `file:dòng loại: snippet`.
  - Lần đo 1 trên 13 gói dev (`i4-dev-*`), trung vị giây/gói: A-TLM 20,5 → 9,8; A-SLM 17,2 → 13,1; **A-LLM 50,7 → 83,5 (chậm hơn)**. Nguyên nhân: đầu ra tới khoảng 880 token ở tốc độ khoảng 12 token/giây.
  - Đã siết giới hạn đầu ra (tối đa 3 behavior, analysis/impact ≤ 200 ký tự); fixture vẫn 27/27 hợp lệ (`i3b-*`).
  - Lần đo 2 trên 13 gói dev (`i3b-dev-*`), so với mốc tuần 4 (`week4-dev-*`):

| Model | Kết luận hợp lệ | Giây/gói trung vị | Hành động giữ nguyên | swc có lý do `postinstall.js:125` |
| --- | --- | --- | --- | --- |
| A-TLM | 3/13 → **13/13** | 20,5 → 8,4 (**−59%**) | 13/13 | 10/10 |
| A-SLM | 13/13 → 13/13 | 17,2 → 12,0 (**−30%**) | 12/13 | 10/10 |
| A-LLM | 13/13 → 13/13 | 50,7 → 82,2 (**+62%**) | 13/13 | 10/10 |

  - **Kết luận I3:** đạt với A-TLM và A-SLM, **không đạt với A-LLM** (mục tiêu −25%). Siết độ dài đầu ra không làm A-LLM nhanh hơn trên gói thật, nên giả thuyết "chậm do câu trả lời dài" chưa đủ. Bước tiếp: đo riêng từng lượt (token vào/ra, thời gian nạp prompt so với thời gian sinh) và tải GPU khi chạy, rồi mới sửa tiếp. Ca A-SLM đổi hành động là fixture canary: `deny` → `review`, như đã ghi ở I2.
- **Bằng chứng phiếu kiểm tra chéo:** `data/review_evidence.py` đọc tĩnh trong container dùng một lần cho cả 4 lượt; **76/76 dòng không có vấn đề tự động**. File bằng chứng ở `data/review_rounds/evidence/` (Git ignore). Các cột `decision`/`reviewer`/`reviewed_at` chờ người kiểm tra chéo điền.
