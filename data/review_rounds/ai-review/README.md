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
- Lượt 10, 11, 14 (120 dòng) làm tiếp sau khi hạn mức mở lại: 82 `verified`, 9 `revise`, 29 `exclude`. Hai dòng không đọc được đầu ra (`dd-actions-languageservices-2.0.9` ở lượt 11) được để `exclude`.
