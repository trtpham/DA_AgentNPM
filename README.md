# DA_AgentNPM

[Kế hoạch thực hiện 10 tuần](ke-hoach-nhat-ky-tuan/KE_HOACH.md)

[Kế hoạch và nhật ký theo tuần](ke-hoach-nhat-ky-tuan/README.md)

## Cấu trúc

- `agent/`: schema verdict.
- `tools/`: tải tarball và công cụ đọc gói.
- `sandbox/`: chạy install script trong Docker cách ly.
- `data/`: hợp đồng nhãn và xử lý tập dữ liệu.
- Hồ sơ nhãn tuần 2: [`data/REVIEW_WEEK2.md`](data/REVIEW_WEEK2.md). `labels.csv` có 76 nhãn: 20 `benign`, 2 `suspicious`, 54 `malicious`; 71 nhãn mới từ bốn batch đã được Codex kiểm tra tĩnh theo ủy quyền TV2 và chờ Phạm Minh Triết kiểm tra chéo trước khi dùng để đánh giá. Bộ này chưa đủ đại diện để đo độ chính xác agent.
- Đối chiếu 450 ứng viên metadata: [`data/review_450/metadata_review_450.csv`](data/review_450/metadata_review_450.csv) (445 manifest khớp, 5 không còn trên Registry; chưa gán nhãn từ metadata).
- Chạy lại theo 25 batch, mỗi batch 18 gói: `rtk proxy python -m data.review_batches` (kết quả trong [`data/review_450/batches/`](data/review_450/batches/); có thể tiếp tục sau khi gián đoạn).
- Kho 450 ứng viên chỉ có metadata: [`data/review_450/public_candidates_450.csv`](data/review_450/public_candidates_450.csv); cách thu thập và giới hạn ở [`data/README.md`](data/README.md). Các ứng viên chưa phải nhãn thật.
- `tests/`: test và gói mô phỏng vô hại.
- `experiments/configs/`: cấu hình ba model Ollama.
- `reports/`: đầu ra phân tích (JSON bị ignore).

Cài phụ thuộc: `py -3.14 -m pip install -r requirements.txt`. Chạy kiểm tra: `rtk proxy py -3.14 -m pytest -q --basetemp=.pytest_tmp`. Một số test HTTP cần quyền bind loopback. Kiểm tra bảo mật: `rtk semgrep scan --config auto --error`.

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

## Trình xem trace (VIZ-1)

Xem lại hoặc theo dõi trực tiếp các trace JSONL trong `reports/` mà không chạy agent:

```powershell
rtk proxy py -3.14 -m viewer --reports reports --port 8765
```

Mở `http://127.0.0.1:8765/`, chọn run rồi chọn gói. **Phát lại**, **Bước trước**, **Bước tiếp** và tốc độ 1×/2×/4× dùng để xem lại. Với gói đang chạy (chưa có `run_end`), trang tự lấy sự kiện mới mỗi giây. Có thể dán đường dẫn `#run=<run_id>&pkg=<tên@phiên bản>` để mở thẳng một gói. Run `sample_traces` gồm ba trace tổng hợp vô hại để demo, trong đó một trace chứa chuỗi XSS thử nghiệm. Server chỉ lắng nghe `127.0.0.1` và chỉ nhận GET/HEAD. Nội dung trace được đưa vào trang bằng `textContent`; trang không có nút chạy agent.

## Tuần 4: bối cảnh, chạy lô, baseline và chỉ số

- **Bối cảnh (`tools/intel.py`):** `rtk proxy py -3.14 -m tools.intel @swc/core 1.7.36 --output reports/week4-context/@swc__core@1.7.36.json`. Lệnh chỉ gửi `tên@phiên bản` tới `api.osv.dev` và `registry.npmjs.org`. Kết quả gồm advisory OSV (cờ `malicious` khi có mã `MAL-`), phiên bản trước, hook mới và integrity. `diff_versions(old_dir, new_dir)` so tĩnh đường install của hai bản đã giải nén. Agent chỉ đọc file context. Tín hiệu OSV MAL chặn approve (luật R5) nhưng không bao giờ là bằng chứng.
- **Chạy lô (`experiments/run_batch.py`):** `rtk proxy py -3.14 -m experiments.run_batch <run_id> A-SLM --labels data/labels.csv --split dev --name @swc/core --contexts reports/week4-context`. Thêm `--dir` cho gói đã giải nén. Kết quả ghi vào `reports/<run_id>/<gói>.json` cùng `run_meta.json` (commit, phiên bản Python/Ollama, digest model, tham số chat, hash dataset). Chạy lại cùng `run_id` sẽ bỏ qua gói đã xong. Một gói lỗi vẫn có kết quả fallback R2 và lô tiếp tục. Dòng không phải `benign` bị từ chối nếu thiếu `--isolated`; cờ này chỉ dùng trong VM. Nhãn không bao giờ vào prompt.
- **Hành động (`tools/actions.py`):** `apply_decision` chỉ lập lệnh `npm approve-scripts`/`deny-scripts` ở chế độ dry-run. `dry_run=False` bị từ chối cho tới khi có gate riêng.
- **GuardDog (`experiments/baseline_guarddog.py`):** build một lần bằng `docker build -t agent-npm-guarddog:2.6.0 experiments/guarddog`, sau đó `rtk proxy py -3.14 -m experiments.baseline_guarddog <run_id> --labels data/labels.csv --split dev --name @swc/core`. Quét trong container tắt mạng, mount chỉ đọc. Trên Windows, semgrep của GuardDog không chạy native và GuardDog còn bỏ qua đường dẫn chứa `tests`, nên không dùng bản pip trên host.
- **Chỉ số (`experiments/metrics.py`):** `rtk proxy py -3.14 -m experiments.metrics reports/<run_id>` (thêm `--source guarddog` cho `reports/<run_id>/guarddog`). Lệnh in confusion matrix, Precision/Recall/F1/FPR, tỷ lệ review, JSON hợp lệ, lỗi, số bước và thời gian. Lượt chạy lỗi được tính là bỏ sót, không bị loại khỏi mẫu số.

## Kiểm tra chéo nhãn và test phát lại

- **Phiếu:** `rtk proxy py -3.14 -m data.review_sheet build <1-4>` tạo `data/review_rounds/round-N.csv`; `… check data/review_rounds/round-N.csv` kiểm tra phiếu đã điền. Cột `decision`, `reviewer`, `reviewed_at` chỉ do người kiểm tra chéo điền.
- **Bằng chứng cho người kiểm tra:** `rtk proxy py -3.14 -m data.review_evidence <1-4>` chạy trong container `python:3.12-slim` dùng một lần (`--read-only`, `--cap-drop ALL`, chỉ mount script). Container tải tarball/ZIP vào bộ nhớ, kiểm tra integrity và `tên@phiên bản`, rồi trích các dòng được dẫn dưới dạng chữ vào `data/review_rounds/evidence/round-N.md` (Git ignore). Không chạy mã gói.
- **Test phát lại:** `tests/fixtures/replays/*.json` lưu nguyên văn phản hồi Ollama của các lượt chạy ngày 04/11 trên fixture vô hại. `tests/test_replay.py` phát lại chúng và kiểm tra cùng luật cuối, nên lỗi riêng của từng model trở thành test hồi quy không cần Ollama.
