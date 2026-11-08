# agent/ — lõi agent

| File | Việc |
| --- | --- |
| `run.py` | Vòng lặp agent: gọi Ollama cục bộ, gọi công cụ, nhận kết luận (gộp `loop.py`, `llm.py`, `prompts.py` trong AGENTS.md mục 5) |
| `schema.py` | Định dạng kết luận và luật kiểm tra (AGENTS.md mục 6.5) |
| `decide.py` | Luật quyết định cuối: cho phép, chặn hay chuyển người xem (R1–R7) |
| `semantics.py` | Che tên gói bằng bí danh, nhóm kỹ thuật, chống kết luận theo tên |
| `trace.py` | Ghi từng bước chạy ra file để trình xem trace mở lại |

Chạy một gói: `py -3.14 -m agent.run --help`.
