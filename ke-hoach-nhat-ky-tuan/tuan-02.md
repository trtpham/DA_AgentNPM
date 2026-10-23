# Tuần 02 — Dữ liệu và hợp đồng công cụ

## Kế hoạch

- [ ] Lập `labels.csv`, lọc mẫu trùng, tách tập phát triển/kiểm tra và nhãn hành vi (TV1-2).
- [x] Tạo schema verdict và kiểm tra các quy tắc JSON (TV2-3).
- [x] Làm `fetch_package` bằng `npm pack`, giải nén an toàn, không chạy script trên máy thật (TV1-3).
- [ ] Dựng sandbox cách ly cơ bản với mẫu mô phỏng vô hại (TV3-1).

## Mốc nghiệm thu

Dữ liệu v1 có nguồn và nhãn kiểm tra chéo; các test với dữ liệu giả chứng minh công cụ đọc không thực thi install script.

## Nhật ký

- Ngày / người thực hiện / người kiểm tra: 2026-10-23 / Codex / chưa có người kiểm tra chéo.
- Đã làm: tạo cấu trúc dự án, schema verdict bằng Pydantic, `fetch_package` dùng `npm pack --ignore-scripts` và giải nén có giới hạn, bộ chuẩn hóa nhãn với chống trùng và chia dev/test ổn định, lệnh sandbox Docker với mạng tắt và mount chỉ đọc; chỉ dùng fixture vô hại.
- Kiểm chứng: `rtk python -m pytest -q --tb=line --basetemp=.pytest_tmp` — PASS (8 test); test xác nhận lệnh `npm pack` không chạy script, chặn traversal/symlink và lệnh Docker có `--network none`.
- NOT_RUN: tải gói npm thật và chạy sandbox thật; Docker Linux daemon không kết nối được tại `npipe:////./pipe/dockerDesktopLinuxEngine`.
- BLOCKED: `rtk semgrep scan` lỗi `Unix.EACCES: socketpair` trong môi trường hiện tại; chưa có kết quả quét tĩnh Semgrep.
- Bổ sung 2026-10-23: ghi 3 ứng viên gói có `postinstall` từ GitHub Advisory/OpenSSF vào `data/candidates.csv` (chỉ metadata, không tải gói). Các nhãn nguồn chưa được kiểm tra độc lập và chưa nhập vào `labels.csv`.
- Vướng mắc / bước tiếp: `data/labels.csv` chỉ có header vì chưa có mẫu nguồn và người kiểm tra chéo; mốc dữ liệu v1 chưa đạt. Chạy fixture trong Docker khi daemon sẵn sàng, thu nguồn nhãn và kiểm tra chéo trước khi đánh dấu hoàn tất.

## Ảnh kết quả

![Tổng hợp kết quả kiểm thử tuần 02](hinh-anh/tuan-02-ket-qua.svg)

*Ảnh SVG tổng hợp kết quả lệnh test và trạng thái Docker quan sát ngày 2026-10-23; không phải ảnh chụp sandbox đang chạy.*
