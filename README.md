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

Chạy agent đọc gói mẫu, không thực thi `postinstall`:

```powershell
rtk python -m agent.run tests/fixtures/benign-package A-TLM
rtk python -m agent.run tests/fixtures/benign-package A-SLM
```

Agent gọi Ollama cục bộ, dùng `read_manifest`/`read_file`, giới hạn 15 bước và chỉ in verdict JSON khi schema cùng dòng bằng chứng hợp lệ. Nếu model không đạt, lệnh trả lỗi; đó là kết quả FAIL của model, không phải nhãn dữ liệu.

## Trực quan hóa quy trình agent

Chạy Ollama và tạo trang HTML từ các bước agent thực sự thực hiện trên fixture vô hại:

```powershell
rtk python -m tools.visualize_agent tests/fixtures/benign-package A-SLM
```

Mở `reports/agent-flow.html` bằng trình duyệt để trình chiếu. Có thể thay `A-SLM` bằng `A-TLM`. Nếu model không tạo được verdict hợp lệ, trang vẫn ghi các bước và lý do lỗi; lệnh trả mã 1. Trang không chứa mã nguồn gói, prompt hay phản hồi thô của model. File HTML sinh ra được Git ignore.
