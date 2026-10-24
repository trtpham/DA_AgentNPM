# Bàn giao sửa 5 vấn đề nghiêm trọng — 2026-10-24

## Quyết định PO và kiểm tra cuối đợt

- Gói không có lifecycle hook và không có `binding.gyp`: nếu mô hình đề xuất `benign/approve`, luật R7_review giữ nhãn `benign` nhưng hành động cuối là `review`. Test tích hợp đọc `index.js`, đối chiếu bằng chứng, rồi xác nhận trace ghi `review` và `dry_run=true`.
- Mọi quyết định hiện chỉ là dry-run. Không gọi `npm approve-scripts`/`deny-scripts`, không sửa `package.json`.
- `rtk proxy python -m pytest -q --basetemp D:\DACN\.pytest-v2-all-escalated-1024`: **44 PASS** ngoài sandbox; 5 test HTTP của viewer không kết nối được loopback trong sandbox (`WinError 10013`). `rtk git diff --check`: PASS. `rtk semgrep scan --error --quiet`: PASS ngoài sandbox; trong sandbox bị chặn `socketpair` (`Unix.EACCES`).

## Cập nhật sau yêu cầu tiếp tục

| Vấn đề | Trạng thái hiện tại | Đã bổ sung | Còn chặn |
| --- | --- | --- | --- |
| 1. Dữ liệu | Một phần | `data/filter_datadog.py` đọc ZIP/tarball trong bộ nhớ, lọc hook/`binding.gyp`, băm SHA-256, khử trùng lặp theo cụm; test dùng archive tổng hợp vô hại. | Chưa có VM và bộ Datadog thật để chạy; `labels.csv` vẫn trống, chưa có nhãn TV1/TV2 xác nhận. |
| 2. Script inline | Một phần | `binding.gyp` được mô tả rõ là install ngầm `node-gyp rebuild`; test xác nhận agent đọc file trước verdict. Inline script và đích script đã được hỗ trợ từ đợt trước. | Quy tắc tự `approve` mọi gói không có lifecycle hook bị auto-review từ chối vì có thể duyệt gói chưa được kiểm tra; agent vẫn dùng luồng kiểm tra hiện tại. |
| 3. Mã minify | Một phần | `deobfuscate` tạo bản `#pretty` chỉ trong bộ nhớ, xem trước base64/hex, entropy; `extract_indicators` tìm file:dòng; agent có thể viện dẫn `#pretty`. Test 50 KB và đường viện dẫn qua. | Bộ làm đẹp hiện dùng bộ tách dòng thư viện chuẩn, chưa có `jsbeautifier` hoặc khả năng giải rối mã đầy đủ. Không chạy `eval`. |
| 4. Manifest dài | Đã sửa ở mức code/test | Giữ thay đổi đọc đủ `package.json` đến 256 KB và test script ở dòng 350. | Chưa thử bộ gói thật. |
| 5. Quyết định | Một phần | `agent/decide.py` áp luật ưu tiên, ngưỡng trong ba cấu hình, trace chứa luật/lý do; SQLite ghi quyết định khi dùng `TraceWriter`. Lệnh npm thực tế không được gọi. | Chưa nối tín hiệu OSV/canary thật, chưa có module thực thi approve/deny; trường `action` được giữ để không phá hợp đồng verdict, còn trace phân biệt đề xuất mô hình và hành động cuối. |

Phạm vi mới được ghi tại `docs/brownfield/TRANSITION_APPROVAL.md`. Chỉ có test trên fixture vô hại; **chưa có số liệu accuracy/FPR trên gói thật**. Bộ lọc Datadog phải được chạy trong VM cách ly theo README. Người tiếp tục cần chuyển tài liệu AGENTS.md gốc vì repo chưa chứa file này.

Kiểm tra sau đợt tiếp tục: `rtk proxy python -m pytest -q` **43 PASS**; `rtk git diff --check` PASS; `rtk semgrep scan --error --quiet` PASS khi chạy ngoài sandbox. Chưa chạy lại Ollama hoặc sandbox với gói thật.

## Ảnh chụp tại commit `88fa00f` trước đợt tiếp tục

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
3. Thử `data/filter_datadog.py` trên bộ Datadog **trong VM**, xác nhận định dạng archive thật và số lượng trước/sau lọc; không chuyển mẫu sang host hoặc Git. TV1 gán nhãn, TV2 kiểm tra chéo.
4. Review `agent/decide.py` theo hợp đồng mục 6 của AGENTS.md gốc, rồi nối OSV/canary khi có nguồn dữ liệu tin cậy. Không tuyên bố có khả năng `approve`/`deny` thực tế: code hiện chỉ ghi quyết định dry-run.
5. Chạy lại `rtk proxy python -m pytest -q`, `rtk git diff --check` và `rtk semgrep scan --error --quiet` sau mỗi đợt sửa. Phân biệt test tổng hợp với đánh giá trên tập nhãn thật.

## Rủi ro còn lại

Các giới hạn chính là thiếu dữ liệu nhãn thật, bao phủ cú pháp npm chưa đầy đủ, nguồn minify vẫn bị cắt và pipeline quyết định chưa hoàn chỉnh. Cần TV2 hoặc người kiểm tra độc lập xác minh bằng chứng trước khi dùng nhãn để đánh giá mô hình.
