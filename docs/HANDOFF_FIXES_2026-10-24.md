# Bàn giao sửa 5 vấn đề nghiêm trọng — 2026-10-24

## Trạng thái khi tạm dừng

- Repo: `D:\DACN\DA_AgentNPM`, nhánh `main`, remote `origin` là `https://github.com/trtpham/DA_AgentNPM.git`.
- Trước đợt sửa, cây làm việc sạch tại `ff9873d`. Phạm vi sửa từng phần đã được ghi trong `docs/brownfield/TRANSITION_APPROVAL.md` theo Gate B0.
- Đây là các sửa đổi cục bộ có test, **chưa phải** bằng chứng về độ chính xác phát hiện gói độc. `data/labels.csv` vẫn chỉ có dòng tiêu đề; chưa có tập nhãn thật để đo accuracy, precision hoặc recall.
- Không tải, giải nén, cài đặt hoặc chạy mẫu npm độc trên máy host trong đợt sửa này.

## Đã sửa đến đâu

| Vấn đề | Trạng thái | Thay đổi đã làm | Còn thiếu |
| --- | --- | --- | --- |
| 1. Thiếu dữ liệu | Một phần | `data/prepare_labels.py` chia dev/test theo nhãn và giữ nguyên cụm liên quan; từ chối cụm có nhãn mâu thuẫn. | Chưa thu thập/gán nhãn mẫu thật, chưa có script lọc dữ liệu Datadog hay đánh giá bằng số liệu. |
| 2. Script inline và đường dẫn script | Một phần | Agent có thể viện dẫn `package.json:<dòng>`. Phát hiện file đích của `node`, `sh`/`bash`, `./...`, `npm run` và `binding.gyp`; yêu cầu đọc file trước khi kết luận. | Chưa chứng minh bao phủ mọi cú pháp script npm. Không tự `approve` chỉ vì thiếu install script. |
| 3. Dòng mã minify | Một phần | Dòng dài hơn 1.000 ký tự được cắt và đánh dấu. Agent không được kết luận `benign`/`approve` khi nguồn đã đọc bị cắt. | Chưa có công cụ giải rối mã (`deobfuscate`) hay `extract_indicators`. |
| 4. Manifest dài hơn 150 dòng | Đã sửa ở mức code và test | `read_manifest` đọc toàn bộ `package.json` trong giới hạn 256 KB; agent không parse bản xem trước 150 dòng. Test tạo manifest với script ở dòng 350 và kiểm tra khả năng viện dẫn. | Chưa có phép đo với bộ gói thật. Giới hạn 256 KB vẫn áp dụng. |
| 5. Quyết định cuối | Một phần | `agent/schema.py` từ chối các cặp nhãn/hành động mâu thuẫn. | Chưa có `decide.py`, ngưỡng quyết định, OSV/canary, SQLite hoặc thao tác `approve`/`deny` thực tế. |

## File của đợt sửa

Code: `agent/run.py`, `agent/schema.py`, `tools/static.py`, `data/prepare_labels.py`.

Test: `tests/test_agent.py`, `tests/test_schema.py`, `tests/test_static.py`, `tests/test_labels.py`.

Quản trị: `docs/brownfield/TRANSITION_APPROVAL.md` và báo cáo này.

## Bằng chứng kiểm tra tại thời điểm bàn giao

| Lệnh | Kết quả |
| --- | --- |
| `rtk proxy python -m pytest -q` | PASS: 36 test, 3.73 giây. |
| `rtk git diff --check` | PASS: không có lỗi whitespace. |
| `rtk semgrep scan --error --quiet` | PASS: exit code 0 khi chạy ngoài sandbox. Trong sandbox lệnh bị `Unix.EACCES` ở `socketpair`, không phải phát hiện từ Semgrep. |

Chưa chạy lại thử nghiệm với Ollama hoặc gói npm thật trong đợt sửa này. Không suy ra rằng agent đã phát hiện đúng mẫu độc thật từ các unit test trên.

## Gợi ý để Claude tiếp tục

1. Xin người dùng chuyển tài liệu `AGENTS.md` gốc (repo hiện không có file này), đặc biệt mục 2 về an toàn và mục 6 về hợp đồng; kiểm tra Gate B0 và diff hiện tại trước khi sửa tiếp. Giữ nguyên dữ liệu và thay đổi đã có.
2. Ưu tiên hoàn thành vấn đề 1 bằng dữ liệu có nguồn gốc, nhãn, phiên bản, bằng chứng file:dòng và người kiểm tra chéo. Không chạy lifecycle script của gói nghi vấn trên host.
3. Tiếp tục vấn đề 2 và 3 bằng fixture tổng hợp vô hại cho cú pháp script và mã minify; kiểm tra đủ đường đọc/viện dẫn trước khi thay đổi chính sách kết luận.
4. Thiết kế vấn đề 5 theo schema mục 6 của `AGENTS.md`, rồi bổ sung test cho quyết định và bằng chứng. Không tuyên bố có khả năng `approve`/`deny` thực tế khi chưa có triển khai và kiểm tra.
5. Chạy lại `rtk proxy python -m pytest -q`, `rtk git diff --check` và `rtk semgrep scan --error --quiet` sau mỗi đợt sửa. Phân biệt test tổng hợp với đánh giá trên tập nhãn thật.

## Rủi ro còn lại

Các giới hạn chính là thiếu dữ liệu nhãn thật, bao phủ cú pháp npm chưa đầy đủ, nguồn minify vẫn bị cắt và pipeline quyết định chưa hoàn chỉnh. Cần TV2 hoặc người kiểm tra độc lập xác minh bằng chứng trước khi dùng nhãn để đánh giá mô hình.
