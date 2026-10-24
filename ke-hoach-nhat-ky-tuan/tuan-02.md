# Tuần 02 — Dữ liệu và hợp đồng công cụ

## Kế hoạch

- [ ] Lập `labels.csv`, lọc mẫu trùng, tách tập phát triển/kiểm tra và nhãn hành vi (TV1-2).
- [x] Tạo schema verdict và kiểm tra các quy tắc JSON (TV2-3).
- [x] Làm `fetch_package` bằng `npm pack`, giải nén an toàn, không chạy script trên máy thật (TV1-3).
- [x] Dựng sandbox cách ly cơ bản với mẫu mô phỏng vô hại (TV3-1).

## Mốc nghiệm thu

Dữ liệu v1 có nguồn và nhãn kiểm tra chéo; các test với dữ liệu giả chứng minh công cụ đọc không thực thi install script.

## Nhật ký

- Ngày / người thực hiện / người kiểm tra: 2026-10-23 / Codex / Phạm Minh Triết nhận vai trò TV2 kiểm tra chéo nhãn, TV1 kiểm tra chéo sandbox; chưa có kết quả review của thành viên.
- Đã làm: tạo cấu trúc dự án, schema verdict bằng Pydantic, `fetch_package` dùng `npm pack --ignore-scripts` và giải nén có giới hạn, bộ chuẩn hóa nhãn với chống trùng và chia dev/test ổn định, lệnh sandbox Docker với mạng tắt và mount chỉ đọc; chỉ dùng fixture vô hại.
- Kiểm chứng: `rtk python -m pytest -q --tb=line --basetemp=.pytest_tmp` — PASS (8 test); test xác nhận lệnh `npm pack` không chạy script, chặn traversal/symlink và lệnh Docker có `--network none`.
- PASS: Docker Engine 29.1.3; chạy `run_sandbox(Path('tests/fixtures/benign-package'))` trong Docker, returncode 0. Log có `benign-install-fixture@1.0.0 postinstall` và `node postinstall.js`; lệnh chạy với `--network none`, mount đầu vào chỉ đọc và giới hạn quyền/tài nguyên.
- Image dùng khi thử: `node@sha256:fe4f6d74e20370acb04ad889077d14d0f64a9c8ea6a42bc60cddf1e844699914`.
- NOT_RUN: không tải hoặc chạy gói npm thật; fixture chỉ mô phỏng vô hại. Chưa đo dấu vết `strace` (việc tuần 3).
- PASS: `rtk semgrep scan` chạy 324 quy tắc trên 34 file Git tracked, 0 findings (sau khi cấp quyền chạy ngoài sandbox công cụ).
- Bổ sung 2026-10-23: ghi 3 ứng viên gói có `postinstall` từ GitHub Advisory/OpenSSF vào `data/candidates.csv` (chỉ metadata, không tải gói). Các nhãn nguồn chưa được kiểm tra độc lập và chưa nhập vào `labels.csv`.
- Vướng mắc / bước tiếp: `data/labels.csv` chỉ có header; 3 ứng viên advisory chưa được TV2 kiểm tra độc lập và chưa có ứng viên benign đã đánh giá. Mốc dữ liệu v1 chưa đạt.

### Bổ sung ngày 2026-10-24

- Đã đồng bộ `labels.csv` và `experiments/dataset.py` với hợp đồng 11 cột ở AGENTS gốc; `prepare_labels` kiểm tra nhãn, bằng chứng, bản trùng rồi gán split ổn định theo tên gói. Test dùng dữ liệu giả; bảng nhãn thật vẫn chỉ có header.
- Đã thêm hai ứng viên lành có install hook (`esbuild@0.24.0`, `@swc/core@1.7.36`) và [hồ sơ bằng chứng cần TV2 kiểm tra](../data/REVIEW_WEEK2.md). Chỉ `npm pack --ignore-scripts` và đọc tĩnh; hai tarball khớp integrity của npm. Ba gói nghi vấn đã bị gỡ khỏi registry, nên chỉ có báo cáo nguồn và chưa có bằng chứng file:dòng được kiểm tra độc lập.
- Sửa `fetch_package` để gọi đúng `npm.cmd` trên Windows. PASS: `fetch_package('esbuild', '0.24.0')` đọc 7 file và `read_manifest` thấy `postinstall: node install.js`; không chạy hook.
- PASS: 9 test trọng tâm tuần 2; PASS: toàn bộ 23 test khi cho phép kết nối loopback cục bộ; PASS: `git diff --check`; PASS: `rtk semgrep scan --error --quiet` (exit 0). Lần pytest thường bị WinError 10013 do sandbox chặn socket loopback của test viewer, không phải lỗi code tuần 2.
- Mốc còn thiếu: Phạm Minh Triết (TV2) xác nhận từng nhãn, nguồn độc lập, `file:lines` và ngày kiểm tra trong hồ sơ. Chưa đưa ứng viên vào `labels.csv` và chưa đánh dấu TV1-2 hoàn tất về dữ liệu.

## Ảnh kết quả

![Tổng hợp kết quả kiểm thử tuần 02](hinh-anh/tuan-02-ket-qua.svg)

*Ảnh SVG tổng hợp kết quả lệnh test và lần chạy fixture trong Docker ngày 2026-10-23; không phải ảnh chụp màn hình container.*
