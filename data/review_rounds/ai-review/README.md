# Lượt kiểm do AI (Claude), không phải kiểm tra chéo

Ngày 11/11/2026, theo yêu cầu của PO, Claude đọc bằng chứng của 220 dòng **gói lành nháp** (lượt 1, 5, 6, 7, 8, 9) và ghi quyết định ở đây. Phiếu `../round-N.csv` của người kiểm **không bị sửa**.

- `reviewer` = `Claude (AI)`. Claude cũng là bên đề xuất các nhãn này, nên đây **không độc lập** và không thay được kiểm tra chéo của người. Báo cáo phải ghi rõ "nhãn do AI kiểm" nếu dùng.
- Cách làm: 6 agent đọc song song theo cùng một tiêu chí (hook có chạy đúng file không; nguồn → hành động → đích; mọi hành động rủi ro có giải thích được bằng mục đích gói không; không chắc thì không `verified`). Claude rà lại mọi ca biên, đổi 3 dòng sang `exclude` (ghi "Rà lại (main)" trong `ai_note`), và tự đọc 6 dòng `verified` chọn ngẫu nhiên: 6/6 khớp.
- `revise` = nhãn "lành" nháp bị sai; `ai_note` ghi nhãn đề xuất (`suspicious` hoặc `malicious`). Các dòng này cần quyết định của PO.
- `exclude` chủ yếu vì đoạn trích không chứa phần làm việc chính (file khác hoặc sau dòng 150).
