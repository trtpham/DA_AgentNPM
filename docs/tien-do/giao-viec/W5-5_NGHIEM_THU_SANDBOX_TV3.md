# Giao việc W5-5 — TV3 nghiệm thu cách ly sandbox

**Người nhận:** TV3 (phụ trách sandbox) · **Người giao:** TV2 Phạm Minh Triết (PO) · **Ngày giao:** 05/11/2026
**Thời lượng ước tính:** 30–45 phút · **Hạn đề xuất:** 07/11/2026

## Vì sao cần TV3 làm việc này

Bước tiếp theo (W5-6) sẽ cho agent **chạy thật** script cài đặt của gói trong sandbox trước khi kết luận. Nếu cách ly có lỗ hổng, mã độc có thể thoát ra máy. Vì vậy quy trình bắt buộc người phụ trách sandbox **tự kiểm tra lại và ký nghiệm thu**. Người viết code (Claude) và PO không được ký thay.

## Việc cần làm

### Bước 1 — Đọc (10 phút)

- Mục **"W5-1"** và **"W5-2, W5-3 (chạy thật) và W5-4"** trong [`../tuan-05.md`](../tuan-05.md): bảng 9 fixture × 3 lần.
- Mục **"W5-11"**: phát hiện trần RAM thực tế là 512 MB do swap.
- File [`../../sandbox/run.py`](../../../sandbox/run.py), đoạn lệnh `docker run` (các cờ `--network none`, `--read-only`, `--cap-drop ALL`, `--pids-limit 64`, `--memory 256m`…).

### Bước 2 — Tự chạy lại (khoảng 5 phút máy chạy)

> **Cập nhật 08/11/2026:** image đã được build lại để có 5 file canary mới (C2). Nếu máy chưa có image mới, build lại trước (khoảng 1 phút, cần mạng để tải `node:22-bookworm-slim` lần đầu):
>
> ```powershell
> docker build -t agent-npm-sandbox:local sandbox
> ```

Làm trên máy của Triết (có sẵn Python 3.14). Bật **Docker Desktop**, mở PowerShell tại `D:\DACN\DA_AgentNPM`:

```powershell
docker image inspect agent-npm-sandbox:local --format '{{.Id}}'
```
Bản build 08/11 ra `sha256:ac8579db8b8071c53019b82784d34ba24fd326caf0d489a6847279394a7d54e0`. Build lại trên máy khác có thể ra digest khác (image gốc `node:22` thay đổi); khi đó ghi digest mới vào nhật ký.

```powershell
$env:RUN_SANDBOX_TESTS="1"; py -3.14 -m pytest -q tests/test_sandbox_limits.py
```
Phải ra **`14 passed`** (khoảng 2 phút; 8 test cũ + 6 test C2/C6).

```powershell
py -3.14 -m experiments.repro_sandbox --runs 3
```
Chạy 9 fixture × 3 lần (khoảng 6 phút), in `all_same` và `no_host_leak`; kết quả lưu ở `reports/repro-sandbox.json`.

```powershell
py -3.14 -m experiments.demo_sandbox
```
In bảng 9 dòng (khoảng 90 giây). So với bảng trong `tuan-05.md`.

> **An toàn:** các lệnh trên chỉ chạy gói thử vô hại do nhóm viết trong `tests/fixtures/`, và chỉ chạy bên trong container. **Không** chạy `node` hay `npm install` trực tiếp trên các thư mục fixture.

### Bước 3 — Đánh dấu checklist

| # | Tiêu chí | Bằng chứng trong bảng | Đạt? |
| --- | --- | --- | --- |
| 1 | Không ra được mạng | `network`: `https=ENETUNREACH dns=EAI_AGAIN` | ☐ |
| 2 | Không ghi được vào gói gốc và hệ thống | `write-outside`: `/input`, `/etc`, `/usr/local` = `EROFS` | ☐ |
| 3 | Giới hạn số tiến trình | `processes`: `refused` > 0, outcome `pids_limit` | ☐ |
| 4 | Giới hạn RAM | `memory`: outcome `oom`, mã 137 (lưu ý swap, xem bước 4) | ☐ |
| 5 | Giới hạn thời gian | `timeout`: outcome `timeout`, mã 124 | ☐ |
| 6 | Phát hiện đọc secret mồi | `canary-all`: `npmrc, ssh, aws, environment` | ☐ |
| 7 | Không lộ biến môi trường máy thật | nhật ký W5-4 (chỉ trùng `127.0.0.1`) | ☐ |
| 8 | Tách hành vi npm và gói | `benign`/`no-hook`: mạng `4/0/0`; `network`: `4/5/0` | ☐ |
| 9 | Tái hiện được | 3 lần trong nhật ký giống nhau; lần TV3 chạy cũng giống | ☐ |
| 10 | Lỗi sandbox không thể thành "cho phép" | `processes`, `memory`, `timeout` đều `ok = ✘` | ☐ |

### Bước 4 — Quyết định về swap (chỉ TV3 quyết)

`--memory 256m` không kèm `--memory-swap`, nên Docker cho thêm 256 MB swap. Script thử cấp phát được 448 MB rồi mới bị kill.

- **Phương án 1 (đề xuất):** nghiệm thu **có điều kiện**: thêm `--memory-swap 256m` trước khi làm W5-6. **Đã chuẩn bị 08/11:** cờ này nằm trong `run_sandbox(..., hardening=True)`; đo được 448 MB khi tắt, 192 MB khi bật (test `test_hardening_removes_swap_so_memory_stays_under_the_limit`). Nếu TV3 chọn phương án 1, chỉ cần đổi mặc định `hardening` thành `True`.
- **Phương án 2:** chấp nhận trần 512 MB và ghi rõ trong báo cáo.

### Bước 5 — Ký nghiệm thu

TV3 tự dán đoạn dưới vào cuối mục W5-4 trong [`../tuan-05.md`](../tuan-05.md), hoặc nhắn nguyên văn cho Triết để dán và chụp tin nhắn làm bằng chứng:

```markdown
### W5-5 — TV3 nghiệm thu cách ly
- Người nghiệm thu: <họ tên TV3> · Ngày: <dd/mm/yyyy>
- Đã tự chạy: test_sandbox_limits (<x>/8) và demo_sandbox trên máy <tên máy>.
- Checklist: đạt <n>/10; mục chưa đạt: <liệt kê hoặc "không có">.
- Swap: phương án <1/2>.
- Kết luận: ĐẠT / ĐẠT CÓ ĐIỀU KIỆN (<điều kiện>) / KHÔNG ĐẠT (<lý do>).
```

## Kết quả chạy lại ngày 08/11/2026 (Claude chạy, để TV3 đối chiếu — chưa phải nghiệm thu)

Claude đã chạy đúng các lệnh ở bước 2 trên máy của Triết lúc 09:45 ngày 08/11/2026 (Docker 29.1.3, linux; image `sha256:ac8579db8b8071c53019b82784d34ba24fd326caf0d489a6847279394a7d54e0`). Log đầy đủ: `reports/w5-5-rerun-1108.log` (chỉ có trên máy, không lên Git). Theo quy trình, **Claude và PO không ký thay**: TV3 tự chạy lại, tự đánh dấu cột "Đạt?" ở bước 3, chọn phương án swap ở bước 4 và ký ở bước 5.

| # | Tiêu chí | Kết quả Claude đo được ngày 08/11 |
| --- | --- | --- |
| 1 | Không ra được mạng | `network`: `https=ENETUNREACH dns=EAI_AGAIN`, outcome `ok` |
| 2 | Không ghi được vào gói gốc và hệ thống | `write-outside`: `/input`, `/etc`, `/usr/local` = `EROFS`; `$HOME` ghi được (tmpfs 1 MB trong container); lần ghi `/etc` có trong `persistence_writes` |
| 3 | Giới hạn số tiến trình | `processes`: `spawned=200 refused=158`, outcome `pids_limit`, `ok=✘` |
| 4 | Giới hạn RAM | `memory`: outcome `oom`, mã 137, cấp phát được **448 MB** với lệnh mặc định; **192 MB** khi `hardening=True` (có `--memory-swap 256m`) |
| 5 | Giới hạn thời gian | `timeout`: outcome `timeout`, mã 124 |
| 6 | Phát hiện đọc secret mồi | `canary-all`: đủ 8 file (`npmrc, ssh, aws, git_credentials, docker, kube, gh, solana`) + `environment` + `env:NPM_TOKEN` |
| 7 | Không lộ biến môi trường máy thật | `repro_sandbox`: `no_host_leak: true` (59 giá trị đã kiểm; `127.0.0.1` được loại vì có sẵn trong trace npm) |
| 8 | Tách hành vi npm và gói | `benign`/`no-hook`: mạng `4/0/0`; `network`: `4/5/0` |
| 9 | Tái hiện được | `repro_sandbox --runs 3`: 9 fixture × 3 lần giống nhau (`all_same: true`) |
| 10 | Lỗi sandbox không thể thành "cho phép" | `processes`, `memory`, `timeout` đều `ok = ✘`; agent: sandbox lỗi → luật `R7_review` (test `test_failed_sandbox_blocks_approval_and_runner_error_is_contained`) |

- Test Docker: `14 passed` (98,8 giây).
- **Đề xuất của Claude cho bước 4 (TV3 quyết):** phương án 1. Lý do: 448 MB gần gấp đôi trần thiết kế 256 MB; cờ đã có sẵn và đo được 192 MB; 3 gói thử lành vẫn cài bình thường khi bật (`test_hardening_keeps_harmless_installs_working`).

## Sau khi TV3 ký

- **ĐẠT** hoặc **ĐẠT CÓ ĐIỀU KIỆN:** Triết duyệt Gate B0 riêng cho W5-6. Claude làm điều kiện (nếu có) rồi nối sandbox vào agent.
- **KHÔNG ĐẠT:** Claude sửa theo lý do của TV3; TV3 nghiệm thu lại. W5-6 chờ đến khi đạt.

## Biên bản nghiệm thu (08/11/2026)

### W5-5 — Nghiệm thu cách ly
- **Người nghiệm thu:** Phạm Minh Triết (TV2, PO) nghiệm thu thay Nguyễn Đình Thiên (TV3), dựa trên lần chạy ngày 08/11. Đây là **ngoại lệ quy trình do PO quyết** (quy trình gốc yêu cầu TV3 tự chạy và ký); TV3 chưa tự chạy lại.
- **Ngày:** 08/11/2026.
- **Lần chạy làm căn cứ:** Claude chạy các lệnh ở bước 2 lúc 09:45 ngày 08/11 trên máy của Triết (Docker 29.1.3, image `sha256:ac8579db…`): `14 passed`, `all_same: true`, `no_host_leak: true`; bảng "Kết quả chạy lại ngày 08/11" ở trên.
- **Swap:** phương án 1. `--memory-swap 256m` đã thành mặc định trong `sandbox/run.py`. Chạy lại sau khi đổi: test Docker `14 passed`; fixture `memory` dừng ở **192 MB** (trước: 448 MB), outcome `oom`, mã 137.
- **Kết luận:** ĐẠT.
- **Phạm vi được mở:** W5-6 (sandbox trong agent) cho gói thử vô hại `tests/fixtures/packages` và `tests/fixtures/sandbox-limits`. Gói thật và corpus mô phỏng vẫn **không** chạy trong container khi chưa có Gate riêng.
