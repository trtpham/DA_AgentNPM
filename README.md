# DA_AgentNPM

[Kế hoạch thực hiện 10 tuần](KE_HOACH.md)

[Kế hoạch và nhật ký theo tuần](ke-hoach-nhat-ky-tuan/README.md)

## Cấu trúc

- `agent/`: schema verdict.
- `tools/`: tải tarball và công cụ đọc gói.
- `sandbox/`: chạy install script trong Docker cách ly.
- `data/`: hợp đồng nhãn và xử lý tập dữ liệu.
- Hồ sơ nhãn tuần 2: [`data/REVIEW_WEEK2.md`](data/REVIEW_WEEK2.md). `labels.csv` đang chờ TV2 kiểm tra chéo từng gói trước khi dùng làm ground truth.
- Kho 450 ứng viên chỉ có metadata: [`data/public_candidates_450.csv`](data/public_candidates_450.csv); cách thu thập và giới hạn ở [`data/README.md`](data/README.md). Các ứng viên chưa phải nhãn thật.
- `tests/`: test và gói mô phỏng vô hại.
- `experiments/configs/`: cấu hình ba model Ollama.
- `reports/`: đầu ra phân tích (JSON bị ignore).

Chạy kiểm tra: `rtk proxy python -m pytest -q --basetemp=.pytest_tmp`. Một số test HTTP cần quyền bind loopback. Kiểm tra bảo mật: `rtk semgrep scan --config auto --error`.

Probe 20 lượt với công cụ giả, không dùng mã gói: `rtk proxy python -m experiments.model_probe --attempts 20`. Kết quả probe không thay thế phép đo accuracy trên nhãn thật.

Sandbox Docker chỉ dùng fixture vô hại: xem [hướng dẫn sandbox](sandbox/README.md). Lệnh build và ba lệnh chạy mẫu nằm trong đó; không thực thi install script trên host. Quyết định agent hiện là dry-run.

Chạy agent đọc gói mẫu, không thực thi `postinstall`:

```powershell
rtk proxy python -m agent.run tests/fixtures/benign-package A-TLM
rtk proxy python -m agent.run tests/fixtures/benign-package A-SLM
```

Agent gọi Ollama cục bộ, dùng `read_manifest`, `read_file`, `deobfuscate` và `extract_indicators`, giới hạn 15 bước. Mã gói chỉ được đọc; `#pretty` là bản xem theo dòng ảo, không chạy JavaScript. Luật trong `agent/decide.py` kiểm tra bằng chứng và ngưỡng 0.8 trước khi trả hành động cuối; gói không có lifecycle hook hoặc `binding.gyp` vẫn cần `review`. Mọi hành động hiện là **dry-run**, không gọi `npm approve-scripts` hoặc `deny-scripts`. Nếu model không đạt, lệnh trả lỗi; đó là kết quả FAIL của model, không phải nhãn dữ liệu.

Bộ lọc Datadog chỉ chạy **trong VM cách ly** sau khi bộ dữ liệu được clone tại đó. Không clone hoặc giải nén mẫu trên máy host. Lệnh trong VM:

```bash
python -m data.filter_datadog /path/to/datadog-dataset /path/to/candidates.csv
```

Script chỉ đọc ZIP/tarball, giữ gói có lifecycle hook hoặc `binding.gyp`, khử trùng lặp theo cụm và xuất SHA-256 cùng số mẫu trước/sau lọc. CSV này là **ứng viên**, chưa phải nhãn đã kiểm tra chéo. Hiện chưa chạy script trên bộ Datadog thật.

## Trực quan hóa quy trình agent

Chạy Ollama rồi khởi động bảng theo dõi trong lúc agent phân tích fixture vô hại:

```powershell
rtk proxy python -X utf8 -m tools.visualize_agent tests/fixtures/benign-package A-SLM
```

Dashboard hiển thị bốn giai đoạn, bước đang xử lý và bằng chứng file:dòng. Sau khi chạy xong, dùng **Phát lại**, **Bước trước**, **Bước tiếp** và chọn tốc độ 1×/2×/4× để trình bày từng bước.

Mở URL `http://127.0.0.1:<port>/` mà lệnh in ra ngay khi bắt đầu; các bước cập nhật trong lúc model chạy. Sau khi xem xong, nhấn Ctrl+C để dừng server. Bản HTML cuối được lưu ở `reports/agent-flow.html`. Có thể thay `A-SLM` bằng `A-TLM` hoặc `A-LLM`; dùng `--output reports/A-LLM-agent-flow.html` nếu muốn giữ báo cáo từng model. Nếu model không tạo được verdict hợp lệ, trang vẫn ghi các bước và lý do lỗi. Trang hiển thị cục bộ những dòng mã đã đọc dưới nhãn dữ liệu không tin cậy, dưới dạng văn bản; không chạy mã gói. File HTML sinh ra được Git ignore.

Chạy lần lượt hai biến thể TLM và LLM, mỗi lệnh mở một URL dashboard riêng:

```powershell
rtk proxy python -X utf8 -m tools.visualize_agent tests/fixtures/benign-package A-TLM --output reports/A-TLM-agent-flow.html
rtk proxy python -X utf8 -m tools.visualize_agent tests/fixtures/benign-package A-LLM --output reports/A-LLM-agent-flow.html
```
