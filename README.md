# DA_AgentNPM — AI Agent kiểm tra gói npm

Agent chạy cục bộ (Ollama) đọc install script của gói npm, kết luận **malicious / suspicious / benign** kèm bằng chứng, rồi đề xuất `npm approve-scripts` hoặc `deny-scripts`. Agent không bao giờ chạy mã của gói trên máy thật.

**Thành viên:** TV1 Lê Đặng Thiên Phước (dữ liệu) · TV2 Phạm Minh Triết (lõi agent, PO) · TV3 Nguyễn Đình Thiên (sandbox, đo lường)

## Thư mục

| Thư mục | Nội dung |
| --- | --- |
| [`agent/`](agent/) | Vòng lặp agent, luật quyết định, định dạng kết luận |
| [`tools/`](tools/) | Công cụ chỉ đọc mà agent dùng; `actions.py` lập lệnh approve/deny |
| [`sandbox/`](sandbox/) | Container cách ly mạng để chạy install script của gói thử |
| [`experiments/`](experiments/) | Chạy lô, baseline GuardDog, tính chỉ số, cấu hình 3 model |
| [`data/`](data/) | Bảng nhãn, phiếu kiểm tra chéo, script xử lý dữ liệu |
| [`viewer/`](viewer/) | Trình xem lại từng bước agent đã làm |
| [`tests/`](tests/) | Test pytest, test Node và gói mẫu vô hại |
| [`docs/`](docs/) | Nhật ký tuần, báo cáo tiến độ, ảnh kết quả |

Mỗi thư mục có `README.md` riêng.

**An toàn:** không bao giờ chạy mã của gói npm trên máy thật (không `npm install`, không `node` file của gói). Mẫu độc thật chỉ mở trong container hoặc máy ảo cách ly.

## Bắt đầu nhanh

```powershell
py -3.14 -m pip install -r requirements.txt
py -3.14 -m pytest -q                                          # test Python
node --test tests/js/*.test.mjs                                # test Node
py -3.14 -m agent.run tests/fixtures/packages/benign-package A-SLM   # chạy agent trên gói mẫu
py -3.14 -m viewer --reports reports                           # xem lại, mở http://127.0.0.1:8765/
```

Cần Ollama đang chạy và có model ghi trong `experiments/configs/`. Mọi hành động hiện là chạy thử (dry-run).

## Không đưa lên Git

`data/samples/` (mẫu độc thật), `reports/` (kết quả chạy), file `.tgz`, `sandbox/out/`, `docs/lms/`. Tài liệu nội bộ của nhóm (`docs/ke-hoach/`, `docs/giao-viec/`, `docs/brownfield/`, `docs/ban-giao/`, `archive/`) chỉ giữ trên máy.
