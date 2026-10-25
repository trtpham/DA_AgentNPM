# Tuần 01 — Chốt nền tảng

## Kế hoạch

- [x] Chọn và tải ba model `qwen3.5:9b`, `qwen3.5:4b`, `qwen3.5:0.8b` qua Ollama.
- [x] Dựng khung repo và `.gitignore` chặn mẫu độc, tarball và đầu ra sandbox (TV1-1).
- [x] Chốt hợp đồng JSON, quyền ghi và phiên bản công cụ.
- [x] Probe tool calling 20 lượt/model bằng công cụ giả (TV2-1).

## Nhật ký

- Ngày: 23/10/2026.
- Kết quả đã xác minh: `ollama list` hiển thị đủ ba tag; 9B 6.6 GB, 4B 3.3 GB, 0.8B 1.3 GB.
- Chưa kiểm tra: chất lượng suy luận, tool calling và các mốc còn lại của tuần.
- Người thực hiện / người kiểm tra: chưa phân công.

## Ảnh kết quả

![Kết quả xác minh ba model trong Ollama](hinh-anh/tuan-01-ollama-list.svg)

*Hình tái hiện từ đầu ra `ollama list` đã xác minh, không phải ảnh chụp màn hình.*

## Cập nhật 2026-10-25

- **PASS — nền tảng:** Repo có cấu trúc, hợp đồng verdict và phân quyền dry-run. Python 3.14.2, Node 24.13.0, npm 11.6.2, Ollama 0.40.11; `ollama list` có đủ ba tag.
- **PASS — probe giả lập:** `experiments/model_probe.py` gọi công cụ giả 20 lượt/model. A-LLM, A-SLM, A-TLM đều đạt 20/20 tool call và 20/20 JSON. Tốc độ quan sát lần lượt 15.2, 48.24, 145.97 token/s; đây là phép đo đầu ra của probe, không phải benchmark chất lượng phân tích gói.
- **Quan sát tài nguyên:** `ollama ps` hiển thị 9B 6.3 GB, 4B 3.1 GB, 0.8B 570 MB; các số này không phải RAM đỉnh.
- **Còn thiếu:** Chưa có reviewer độc lập ký nghiệm thu tuần 1. Probe công cụ giả chưa chứng minh độ ổn định của agent trên gói thật.
