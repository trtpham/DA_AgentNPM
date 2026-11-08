# tools/ — công cụ của agent

Mọi công cụ chỉ đọc, trừ `actions.py`. Không công cụ nào chạy mã của gói.

| File | Việc |
| --- | --- |
| `fetch.py` | Tải tarball bằng `npm pack`, không chạy script |
| `static.py` | Giải nén an toàn, `read_manifest`, `read_file`, `extract_indicators`, `deobfuscate` |
| `explore.py` | 10 công cụ đọc thêm: `list_files`, `search_code`, `trace_flow`, `inspect_scripts`… (bật theo config) |
| `intel.py` | Tra OSV và npm Registry trước khi chạy agent; chỉ dùng cho luật R5 |
| `actions.py` | File duy nhất được ghi `package.json`: lập lệnh `npm approve-scripts` / `deny-scripts`, mặc định chạy thử |

Mọi công cụ trả `{"ok": ..., "data": ..., "error": ...}` và không ném lỗi ra vòng lặp agent. Nội dung lấy từ gói luôn bọc `{"untrusted": true, ...}`.
