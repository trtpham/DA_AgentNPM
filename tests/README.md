# tests/

```powershell
py -3.14 -m pytest -q                       # test Python (test_*.py)
node --test tests/js/*.test.mjs             # test Node của văn phòng 3D
$env:RUN_SANDBOX_TESTS=1; py -3.14 -m pytest -q tests/test_sandbox_limits.py   # test Docker, cần image sandbox
```

## Gói mẫu (`fixtures/`)

| Thư mục | Nội dung |
| --- | --- |
| `packages/` | 4 gói vô hại cơ bản: lành, đọc canary, không có hook, mã làm rối |
| `corpus/` | 22 gói **mô phỏng** (11 lành, 11 độc) đi theo cặp gần giống nhau, chỉ khác hành vi; đáp án ở `EXPECTED.json` |
| `replays/` | Câu trả lời thật của Ollama ghi lại, để test hồi quy không cần model |
| `sandbox-limits/`, `strace/` | Dữ liệu cho test sandbox |

Gói mô phỏng độc **chỉ được đọc tĩnh, không bao giờ chạy**. Chúng chỉ dùng dải IP tài liệu (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24) và tên miền `.invalid`. Không viết `curl … | sh` trong `package.json`, vì Windows Defender sẽ cách ly file.

Đo agent có kết luận theo tên gói không: `py -3.14 -m experiments.rote_probe <run_id> A-LLM A-SLM A-TLM`.
