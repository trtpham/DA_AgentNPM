# Giao việc W5-10 — Kiểm tra chéo bộ nhãn v1 (76 dòng)

**Người giao:** TV2 Phạm Minh Triết (PO, chốt nhãn sau cùng) · **Ngày giao:** 05/11/2026 · **Hạn đề xuất:** 09/11/2026

## Vì sao việc này quan trọng

Bộ nhãn là "đáp án" để chấm agent. Nhãn sai thì mọi con số Precision, Recall, F1 cuối kỳ đều sai. Nhãn v1 do Codex/Claude soạn, nên **phải có một người thật khác kiểm tra lại**. Việc này đang **chặn mốc thực nghiệm tuần 7–8**.

## Bắt đầu nhanh (cập nhật 08/11/2026)

Trạng thái hiện tại: cả 4 phiếu đều trống (`check` ra `pending` 20/18/18/20). Claude **không** điền phiếu: người kiểm tra phải là người thật, khác người soạn nhãn.

1. Ngồi ở máy của Triết, mở thư mục `D:\DACN\DA_AgentNPM` bằng VS Code.
2. Mở song song 2 file của lượt mình: phiếu `data/review_rounds/round-N.csv` (để điền) và bằng chứng `data/review_rounds/evidence/round-N.md` (để đọc).
   - **Phước:** lượt 1 (20 gói lành) rồi lượt 4 (20 gói độc).
   - **Thiên:** lượt 2 và lượt 3 (mỗi lượt 18 gói của một chiến dịch).
3. Với từng dòng: tìm cùng `id` trong file bằng chứng, trả lời 3 câu ở mục "Cách kiểm tra một dòng", rồi điền 5 cột cuối (`decision`, `reviewer` = họ tên thật, `reviewed_at` = `2026-11-DD`, `observed_behavior`, `note`).
4. Lưu, rồi chạy `py -3.14 -m data.scripts.review_sheet check data/review_rounds/round-N.csv` cho tới khi ra `'complete': True, 'problems': []`.
5. Báo Triết. Triết chạy `check` cho cả 4 phiếu và commit.

## Lượt mới (từ 08/11/2026)

Toàn bộ 15 lượt, người và hạn: [PHAN_CONG_KIEM_TRA_CHEO.md](PHAN_CONG_KIEM_TRA_CHEO.md).

| Lượt | Nội dung | Người | Số dòng |
| --- | --- | --- | --- |
| `round-5.csv` | 40 gói lành **nháp** từ phân loại tĩnh nhóm A (D-2); bằng chứng `evidence/round-5.md` | TV3 Nguyễn Đình Thiên | 40 |

Với lượt 5, cột `label` = `benign` chỉ là đề xuất của Claude. Đọc đoạn trích; nếu thấy hành vi khác (gọi mạng, đọc secret…) hoặc đoạn trích không đủ, chọn `revise`/`exclude` và ghi `note`.

## Phân công

| Người | Phiếu | Nội dung | Số dòng | Ước tính |
| --- | --- | --- | --- | --- |
| **TV1 Lê Đặng Thiên Phước** | `round-1.csv` | Gói lành (esbuild, swc…) | 20 | ~1 giờ |
| **TV1 Lê Đặng Thiên Phước** | `round-4.csv` | Gói độc thuộc các họ khác | 20 | ~1,5 giờ |
| **TV3 Nguyễn Đình Thiên** | `round-2.csv` | Chiến dịch `npm-token-worm-2026-03` | 18 | ~1 giờ |
| **TV3 Nguyễn Đình Thiên** | `round-3.csv` | Chiến dịch `shai-hulud-2-2025-11` | 18 | ~1 giờ |
| **TV2 Triết** | — | Chạy lệnh `check`, chốt nhãn, commit | — | ~20 phút |

Hai lượt 2 và 3 mỗi lượt là một chiến dịch, các gói có mã gần giống nhau, nên làm nhanh hơn. TV3 nhận ít dòng hơn vì còn nghiệm thu sandbox (W5-5).

## Tài liệu mỗi người nhận

Với mỗi lượt `N` được giao, có 2 file:

| File | Nằm ở | Ghi chú |
| --- | --- | --- |
| `data/review_rounds/round-N.csv` | Có trong Git | Phiếu để **điền** |
| `data/review_rounds/evidence/round-N.md` | **Chỉ có trên máy Triết** (không đưa lên Git) | Bằng chứng để **đọc** |

File bằng chứng chứa **đoạn mã độc dưới dạng chữ**. Đọc thì vô hại, nhưng:
- Cách tốt nhất là làm ngay trên máy của Triết.
- Nếu gửi file, chỉ gửi riêng qua Drive hoặc tin nhắn cá nhân. **Không** đăng nhóm lớp, **không** đưa lên Git. Một số phần mềm diệt virus có thể cảnh báo file này.
- **Không** tải hay giải nén các link `.zip`/`.tgz` ghi trong bằng chứng trên máy Windows.

## Cách kiểm tra một dòng

Mỗi gói trong file bằng chứng có: tên@phiên bản, nhãn đề xuất, nguồn tải, SHA-256, hook cài đặt (ví dụ `"postinstall": "node index.js"`), các dòng mã được trích kèm số dòng, và mục "vấn đề tự động phát hiện". Cả 76 dòng đều ghi "không có", tức file và số dòng đã khớp với gói thật.

Với mỗi dòng, tự trả lời 3 câu:

1. **Hook có thật sự chạy file này không?** So `hook` với cột `file`.
2. **Đoạn mã trích làm gì?** Mô tả theo bộ ba **nguồn → hành động → đích**. Ví dụ: đọc `~/.npmrc` → gom token → gửi cho tiến trình con / máy chủ ngoài. Hoặc: đọc tên nền tảng → tải file nhị phân từ npm Registry → ghi vào thư mục gói.
3. **Mô tả và nhãn có khớp không?** Cột `behavior_main`, `technique`, `label` có đúng với điều bạn vừa thấy không?

## Cách điền 5 cột cuối

| Cột | Điền | Ví dụ |
| --- | --- | --- |
| `decision` | `verified` = nhãn và mô tả đúng · `revise` = cần sửa · `exclude` = loại khỏi tập | `verified` |
| `reviewer` | **Họ tên thật** của bạn. Không ghi `codex` hay `claude`, script sẽ báo lỗi | `Nguyễn Văn A` |
| `reviewed_at` | Ngày kiểm tra, dạng `YYYY-MM-DD` | `2026-11-06` |
| `observed_behavior` | 1 câu **bằng lời của bạn** về hành vi đã thấy | `đọc ~/.npmrc, gom token rồi truyền cho tiến trình con chạy script khác` |
| `note` | **Bắt buộc** khi `revise` hoặc `exclude`: sửa gì, vì sao | `bằng chứng đúng nhưng technique nên là token_exfiltration` |

**Khi nào chọn gì:**
- `verified`: đoạn mã cho thấy rõ hành vi đúng như mô tả, và nhãn hợp lý.
- `revise`: hành vi có thật nhưng mô tả, kỹ thuật, dòng hoặc nhãn chưa đúng. Ví dụ: nhãn `malicious` nhưng chỉ thấy hành vi đáng ngờ, chưa thấy gửi dữ liệu đi.
- `exclude`: không xác định được (đoạn trích không đủ, file không phải đường cài đặt), hoặc gói trùng lặp. Nếu cần xem thêm mã mới quyết được, ghi `note: cần xem thêm trong VM`.
- **Không chắc thì đừng ghi `verified`.** Một nhãn sai nguy hiểm hơn một nhãn bị loại.

## Mở và lưu file CSV đúng cách

- **Nên dùng VS Code** (sửa trực tiếp, giữ nguyên dấu phẩy), hoặc **LibreOffice Calc**: khi mở chọn UTF-8 và dấu phẩy; khi lưu chọn *Giữ định dạng hiện tại* (CSV).
- **Không mở bằng Excel rồi lưu đè.** Excel hay làm hỏng tiếng Việt và tự đổi cột `lines` (ví dụ `66,186,235,269-273`) thành số hoặc ngày, làm hỏng bằng chứng.
- Nếu `observed_behavior` hoặc `note` có dấu phẩy, đặt cả ô trong ngoặc kép `"..."`. LibreOffice tự làm việc này.
- Không sửa 11 cột đầu (`id` … `technique`). Muốn sửa thì ghi đề xuất vào `note`.

## Tự kiểm tra trước khi nộp

Trên máy Triết, PowerShell tại `D:\DACN\DA_AgentNPM`:

```powershell
py -3.14 -m data.scripts.review_sheet check data/review_rounds/round-1.csv
```

- Còn dòng chưa điền: `'complete': False` và `'pending': <số dòng>`.
- Xong và hợp lệ: **`'complete': True, 'problems': []`**.
- Có lỗi: `problems` liệt kê theo `id` (thiếu tên, thiếu ngày, thiếu `note`…). Sửa rồi chạy lại.

## Sau khi nộp

1. Triết chạy `check` cho cả 4 phiếu, rồi commit phiếu đã điền.
2. Dòng `revise`: Triết và người kiểm tra thống nhất sửa `data/labels.csv`. Dòng `exclude`: loại khỏi tập tính chỉ số.
3. Claude cập nhật nhật ký tuần, chốt **nhãn v1**, chuẩn bị chạy Recall/F1 trong VM ở tuần 7–8.
