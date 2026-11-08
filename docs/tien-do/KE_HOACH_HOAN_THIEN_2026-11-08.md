# Kế hoạch hoàn thiện việc còn dở tuần 2–5 (08/11/2026)

> Người lập: Claude · PO: Phạm Minh Triết · Phạm vi: chỉ fixture vô hại trong `tests/fixtures/` và gói lành `@swc/core` của tập dev (tải bằng `npm pack`, chỉ đọc). Không chạy gói thật trong container, không mở `data/samples/`.

## 1. Việc còn dở (rà từ `tuan-02.md` … `tuan-05.md`)

| Tuần | Việc | Trạng thái trước | Ai làm được |
| --- | --- | --- | --- |
| 2 | Dữ liệu v1: nhãn `malicious`/`suspicious` có kiểm tra chéo | BLOCKED (thiếu người kiểm tra) | Người thật (W5-10) |
| 5 | W5-1: chạy lại 6 fixture giới hạn trên image mới (canary C2) | Image cũ, chưa có canary mới | Claude |
| 5 | W5-4: tái hiện 3 lần × 9 fixture, không lộ biến môi trường host, ghi digest image | Chưa chạy | Claude |
| 5 | Lỗi RAM: fixture `memory` cấp phát được 448 MB dù `--memory 256m` (do swap) | Chờ TV3 | Claude đo + đề xuất, TV3 quyết |
| 5 | C6 `hardening=True` chưa từng chạy trong Docker | NOT_RUN | Claude |
| 5 | W5-5: TV3 nghiệm thu cách ly | Chờ TV3 | TV3 |
| 5 | W5-6 / C7: sandbox trong agent, chạy thật trên fixture | Chỉ có test giả | Claude |
| 6 | Hồi quy 13 gói dev với config `-X` | NOT_RUN | Claude |
| 2–5 | Checkbox kế hoạch tuần 5 chưa đánh; AGENTS §6.4 còn ghi "chưa nối sandbox" | Tài liệu cũ | Claude |

## 2. Thứ tự làm

1. **Build lại image:** `docker build -t agent-npm-sandbox:local sandbox`; kiểm tra đủ 8 file canary trong `/opt/canary`.
2. **Test Docker:** `RUN_SANDBOX_TESTS=1 py -3.14 -m pytest -q tests/test_sandbox_limits.py`.
3. **W5-4:** script `experiments/repro_sandbox.py` chạy mỗi fixture 3 lần, so `outcome`, `canary_touched`, `actor`; quét trace và stdout tìm giá trị biến môi trường của host; in digest image.
4. **RAM + C6:** thêm `--memory-swap 256m` vào bộ `HARDENING` (vẫn opt-in). Chạy fixture `memory` có và không có `hardening`, ghi số MB cấp phát được. Chạy 3 fixture lành với `hardening=True` để chắc npm vẫn cài được.
5. **C7 thật:** agent với `sandbox: true` trên 3 fixture gói (`benign`, `canary`, `no-hook`) bằng A-LLM-X.
6. **Hồi quy dev:** lệnh hồi quy 13 gói với A-LLM-X, A-SLM-X, A-TLM-X; so với `rote-reg-a-*`.
7. **Tài liệu:** nhật ký tuần 5/6, checkbox, AGENTS §6.4, phiếu W5-5 (ghi image mới cần TV3 kiểm lại).

## 3. Nghiệm thu

- Test Docker PASS hoặc ghi FAIL kèm nguyên nhân, không nới fixture cho PASS.
- W5-4: 3 lần giống nhau ở mọi trường so sánh; 0 giá trị biến môi trường host trong trace.
- Hồi quy dev: không có approve nhầm hay deny nhầm mới so với `rote-reg-a-*`.
- Mặc định `docker run` và config `A-*` không đổi; mọi thay đổi chặt hơn là opt-in.
- Việc cần người thật (W5-5, W5-10, dữ liệu v1) ghi BLOCKED, không tự điền thay.
