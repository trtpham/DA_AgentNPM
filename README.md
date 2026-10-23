# DA_AgentNPM

[Kế hoạch thực hiện 10 tuần](KE_HOACH.md)

[Kế hoạch và nhật ký theo tuần](ke-hoach-nhat-ky-tuan/README.md)

## Cấu trúc

- `agent/`: schema verdict.
- `tools/`: tải tarball và công cụ đọc gói.
- `sandbox/`: chạy install script trong Docker cách ly.
- `data/`: hợp đồng nhãn và xử lý tập dữ liệu.
- `tests/`: test và gói mô phỏng vô hại.
- `experiments/configs/`: cấu hình ba model Ollama.
- `reports/`: đầu ra phân tích (JSON bị ignore).

Chạy kiểm tra: `rtk python -m pytest -q --basetemp=.pytest_tmp`. Docker daemon cần hoạt động để thử sandbox thật; test hiện chỉ kiểm tra lệnh Docker được tạo.
