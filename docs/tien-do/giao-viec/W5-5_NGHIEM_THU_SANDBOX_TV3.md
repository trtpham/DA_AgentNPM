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

### Bước 2 — Tự chạy lại (khoảng 3 phút máy chạy)

Làm trên máy của Triết (có sẵn image và Python 3.14). Bật **Docker Desktop**, mở PowerShell tại `D:\DACN\DA_AgentNPM`:

```powershell
docker image inspect agent-npm-sandbox:local --format '{{.Id}}'
```
Phải ra `sha256:b657e0130392664d3bf49d80af7055ab9f5319265839111270e0b11610242b82`.

```powershell
$env:RUN_SANDBOX_TESTS="1"; py -3.14 -m pytest -q tests/test_sandbox_limits.py
```
Phải ra **`8 passed`** (khoảng 80 giây).

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

- **Phương án 1 (đề xuất):** nghiệm thu **có điều kiện**: thêm `--memory-swap 256m` trước khi làm W5-6. Claude sửa 1 dòng, thêm test, chạy lại, rồi TV3 xem kết quả.
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

## Sau khi TV3 ký

- **ĐẠT** hoặc **ĐẠT CÓ ĐIỀU KIỆN:** Triết duyệt Gate B0 riêng cho W5-6. Claude làm điều kiện (nếu có) rồi nối sandbox vào agent.
- **KHÔNG ĐẠT:** Claude sửa theo lý do của TV3; TV3 nghiệm thu lại. W5-6 chờ đến khi đạt.
