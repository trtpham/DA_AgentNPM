# Lượt kiểm do AI (Claude), không phải kiểm tra chéo

Ngày 11/11/2026, theo yêu cầu của PO, Claude đọc bằng chứng của 220 dòng **gói lành nháp** (lượt 1, 5, 6, 7, 8, 9) và ghi quyết định ở đây. Phiếu `../round-N.csv` của người kiểm **không bị sửa**.

- `reviewer` = `Claude (AI)`. Claude cũng là bên đề xuất các nhãn này, nên đây **không độc lập** và không thay được kiểm tra chéo của người. Báo cáo phải ghi rõ "nhãn do AI kiểm" nếu dùng.
- Cách làm: 6 agent đọc song song theo cùng một tiêu chí (hook có chạy đúng file không; nguồn → hành động → đích; mọi hành động rủi ro có giải thích được bằng mục đích gói không; không chắc thì không `verified`). Claude rà lại mọi ca biên, đổi 3 dòng sang `exclude` (ghi "Rà lại (main)" trong `ai_note`), và tự đọc 6 dòng `verified` chọn ngẫu nhiên: 6/6 khớp.
- `revise` = nhãn "lành" nháp bị sai; `ai_note` ghi nhãn đề xuất (`suspicious` hoặc `malicious`). Các dòng này cần quyết định của PO.
- `exclude` chủ yếu vì đoạn trích không chứa phần làm việc chính (file khác hoặc sau dòng 150).

## Gói độc (11/11/2026)

- Lượt 2, 3, 4, 12, 13, 15 đã kiểm. Mã độc chỉ được giải mã trong bộ nhớ để đọc (không ghi ra đĩa, không giải nén, không chạy). Tiêu chí `verified`: hook chạy đúng file và đoạn trích cho thấy hành vi độc trên đường cài đặt.
- Lượt 3 (Shai-Hulud 2.0): cả 18 dòng `exclude` vì đoạn trích chỉ thấy `setup_bun.js` chạy ngầm `bun_environment.js`; phần đánh cắp nằm ở file không được trích.
- Rà lại (main): 4 gói `*-tg-api` ở lượt 4 đổi `exclude` → `verified` (chạy EXE từ ZIP có mật khẩu lúc cài).
- Lượt 10, 11, 14 (120 dòng) làm tiếp sau khi hạn mức mở lại: 82 `verified`, 9 `revise`, 29 `exclude`. Một dòng không đọc được đầu ra (`dd-actions-languageservices-2.0.9`, lượt 11) được để `exclude`; hai dòng ở lượt 14 đọc được bằng cách chèn ký tự vào đầu ra trong bộ nhớ.

## Bổ sung lượt 16, 17, 18, 20 (11/11/2026)

- Soạn thêm 100 nháp lành (lượt 16: hết nhóm A; 17–18: hết nhóm B "nhẹ") và 40 nháp độc Datadog (lượt 20); bằng chứng lập trong container dùng một lần (`review_evidence`).
- Kết quả: 57 `verified`, 4 `revise`, 79 `exclude`. Nháp lành nhóm B có tỉ lệ `exclude` cao vì phần tải/chạy nằm sau dòng 150 hoặc ở file khác.
- Rà lại (main): `cand-nono-postinstall-test` → `revise` (ghi file vào home); `dd-strapi-plugin-guardarian-ext` → `exclude` (chưa thấy lời gọi lúc cài).
- Ba dòng ở lượt 20 không đọc được đầu ra (`show.py`) nên để `exclude`.

## Bộ ứng viên thứ hai b2 và lượt 21–26 (11/11/2026)

- Theo Gate B0 11/11 (bộ ứng viên lành thứ hai): thu thêm 300 gói có install hook (`data/review_b2/`, chỉ metadata), phân loại tĩnh trong container dùng một lần (A 193, B 79, C 28). Soạn 189 nháp lành (lượt 22–24 nhóm A, 25–26 nhóm B) và 40 nháp độc Datadog (lượt 21).
- Lượt 21: 24 `verified`, 9 `revise`, 7 `exclude` (Rà lại (main): `lowerx-package` → `exclude`).
- Lượt 22–26: 113 `verified`, 0 `revise`, 56 `exclude`. Năm agent đọc song song theo cùng tiêu chí như trên.
- Rà lại (main), đổi `verified` → `exclude` vì chưa đủ bằng chứng: 4 gói họ `node-pty-prebuilt-multiarch` và `baja-lite-xlsx` (chưa xem postinstall), `libsamplerate` (chưa thấy `binding-options.js`), `@aleworm/usb2` (tải binary darwin-x64 cố định cho mọi nền tảng), `jsmeow` (tự mô tả là công cụ hack game).

## Lượt 27: sửa nhãn 42 dòng `revise` rồi kiểm lại (11/11/2026)

- Theo Gate B0 11/11: 42 dòng `revise` được đổi nhãn nháp sang nhãn AI đề xuất (nhãn cũ/mới, lý do: `../relabel-27.csv`), rồi kiểm lại ở lượt 27 bằng bằng chứng lập lại. Hai agent đọc song song.
- Kết quả: 38 `verified`, 4 `exclude`. Rà lại (main): 3 dòng vẫn bị đề xuất đổi nhãn lần hai (`amrahulmail-ctf-lab-evil`, `ddddddd1d`, `test-thegenetic-module-2.2.6`) → `exclude`, không sửa nhãn lần hai.
