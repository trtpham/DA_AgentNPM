# Gate B0 — agent A-TLM / A-SLM

DECISION: APPROVED
PO: Phạm Minh Triết
APPROVED_AT: 2026-10-23 19:45 Asia/Saigon
EVIDENCE_REFERENCES: Trả lời trực tiếp trong chat ngày 2026-10-23: “Phê duyệt phạm vi này” cho vòng lặp agent đọc gói an toàn, gọi Ollama A-TLM/A-SLM và test; không chạy install script hoặc đưa mẫu độc lên Git.

## B0.1 — AS-IS và kiểm tra

REVIEW_STATUS: REVIEWED
REVIEWED_BY: Codex (owner), Phạm Minh Triết (PO phê duyệt phạm vi)
REVIEWED_AT: 2026-10-23
EVIDENCE_REFERENCES: `agent/schema.py`, `tools/static.py`, `tools/fetch.py`, `sandbox/run.py`, `experiments/configs/`, `data/candidates.csv`, `data/labels.csv`, `tests/`.

- Feature inventory: schema verdict, công cụ đọc gói giới hạn đường dẫn/kích thước, fetch tarball không chạy script, sandbox Docker, ba cấu hình Ollama. Chưa có runtime agent hoặc báo cáo verdict tự động.
- Technical audit / gap: `read_manifest` và `read_file` đã có; thiếu client Ollama, vòng lặp tool calling, giới hạn bước và kiểm tra verdict đầu ra.
- Security audit: nội dung package là dữ liệu không tin cậy. Không thực thi lifecycle script trên host. Chỉ thử với `tests/fixtures/benign-package` trong phạm vi này.
- Test baseline: `rtk python -m pytest -q` → 8 passed; `rtk semgrep scan --error --quiet` → exit 0. Cả hai chạy cục bộ ngày 2026-10-23.
- Technical debt: `data/labels.csv` mới có header; ba dòng `data/candidates.csv` là metadata advisory chưa được kiểm tra mã độc lập. UNKNOWN: hiệu năng và độ chính xác trên gói thật.

## B0.2 — Baseline

REVIEW_STATUS: REVIEWED
REVIEWED_BY: Codex
REVIEWED_AT: 2026-10-23
EVIDENCE_REFERENCES: `git status --short --branch` sạch; `git rev-parse HEAD` = `2f8efa5fba031b13d11b4601cd862b28fca38c27`; nhánh `main` theo `origin/main`.

Không có dữ liệu người dùng cần backup cho thay đổi code này; không sửa `data/labels.csv` hoặc mẫu package. Không xóa dữ liệu.

## B0.3 — Rủi ro

REVIEW_STATUS: REVIEWED
REVIEWED_BY: Codex
REVIEWED_AT: 2026-10-23
EVIDENCE_REFERENCES: `tools/static.py`, `agent/schema.py`, advisory trong `data/candidates.csv`.

- P1: model có thể bịa bằng chứng hoặc làm theo chỉ dẫn trong file package. Chặn bằng prompt coi file là dữ liệu không tin cậy, tool allowlist, ràng buộc package path và xác thực schema/evidence.
- P1: chạy install script của mẫu độc trên host. Phạm vi này chỉ đọc fixture vô hại; không gọi npm install hoặc sandbox với ứng viên độc.
- UNKNOWN: độ chính xác trên dữ liệu thật; cần bộ nhãn kiểm tra chéo trước benchmark.

## B0.4 — Phạm vi chuyển đổi

REVIEW_STATUS: REVIEWED
REVIEWED_BY: Codex
REVIEWED_AT: 2026-10-23
EVIDENCE_REFERENCES: yêu cầu và phê duyệt trong chat ngày 2026-10-23; `ke-hoach-nhat-ky-tuan/tuan-03.md`.

- Owner: Codex. Reviewer/PO: Phạm Minh Triết.
- Được phép sửa: runtime trong `agent/`, test trong `tests/`, hướng dẫn chạy ở `README.md`, nhật ký tuần 3. Tái sử dụng `tools/static.py` và `agent/schema.py`.
- Acceptance: A-TLM và A-SLM gọi công cụ đọc fixture, xuất verdict hợp schema có bằng chứng; có giới hạn tối đa 15 bước, timeout và lỗi rõ ràng; test offline của vòng lặp PASS.
- Trạng thái DoD ngày 2026-10-23: CHƯA ĐẠT; A-SLM PASS, A-TLM chưa tạo được verdict hợp schema trong 15 bước. Kết quả chi tiết ở nhật ký tuần 3.
- Non-goals: nhãn dữ liệu thật, tải/chạy gói độc, benchmark độ chính xác, A-LLM.
- Regression: 8 test hiện có tiếp tục PASS; Semgrep không finding.
- Rollback: revert commit triển khai; không có migration hoặc dữ liệu cần khôi phục.
- Dừng nếu tool yêu cầu đường dẫn ngoài gói, model không trả verdict hợp lệ, hoặc Ollama không sẵn sàng.

## B0.5 — Trực quan hóa quy trình agent

DECISION: APPROVED
PO: Phạm Minh Triết
APPROVED_AT: 2026-10-23 Asia/Saigon
EVIDENCE_REFERENCES: Yêu cầu trực tiếp trong chat: “làm thêm 1 tool để trực quan hóa quy trình hoạt động của agent”.

- Owner: Codex. Reviewer/PO: Phạm Minh Triết.
- Phạm vi: ghi trace tóm tắt các bước thực thi thật trong `agent/run.py`; thêm công cụ tạo trang HTML độc lập, test offline và hướng dẫn demo.
- Trace không lưu nội dung file gói, prompt hoặc nội dung trả lời thô của model; giao diện chỉ hiển thị lệnh đọc, kết quả kiểm tra và verdict đã xác thực.
- Không chạy script cài đặt npm, không thêm mẫu độc, không thay đổi schema verdict hoặc hợp đồng trả về của `analyze`.

## B0.6 — Cập nhật trực tiếp khi model chạy

DECISION: APPROVED
PO: Phạm Minh Triết
APPROVED_AT: 2026-10-23 Asia/Saigon
EVIDENCE_REFERENCES: Người dùng làm rõ trong chat: “ý tôi là tool realtime trong trình chạy các mô hình cơ mà”.

- Owner: Codex. Reviewer/PO: Phạm Minh Triết.
- Phạm vi: thay báo cáo chỉ có sau khi chạy bằng dashboard HTTP chỉ lắng nghe `127.0.0.1`, cập nhật trace và verdict theo thời gian thực trong lúc A-TLM/A-SLM chạy; giữ bản HTML cuối để xem lại.
- Không mở server ra LAN, không chạy mã npm, không chuyển nội dung file/prompt/phản hồi thô qua dashboard.

## B0.7 — Chạy A-TLM và A-LLM

DECISION: APPROVED
PO: Phạm Minh Triết
APPROVED_AT: 2026-10-23 Asia/Saigon
EVIDENCE_REFERENCES: Yêu cầu trực tiếp trong chat: “TLM với LLM chạy giúp tôi”.

- Owner: Codex. Reviewer/PO: Phạm Minh Triết.
- Phạm vi: mở lựa chọn A-LLM từ cấu hình `qwen3.5:9b` đã có; chạy A-TLM và A-LLM trên fixture vô hại qua dashboard localhost, ghi kết quả và giới hạn thật.
- Không chạy install script npm, không dùng mẫu độc hoặc nhận kết quả model làm nhãn dữ liệu.
- Kết quả kiểm chứng: A-TLM (`qwen3.5:0.8b`) FAIL sau 15 bước vì verdict không hợp schema; A-LLM (`qwen3.5:9b`) PASS sau 3 bước với verdict `benign`, `approve`, bằng chứng `postinstall.js:2` trên fixture vô hại.

## Gate B0 — VIZ-1 (2026-10-23)

DECISION: APPROVED
PO: Phạm Minh Triết
EVIDENCE_REFERENCES: Yêu cầu VIZ-1 và trả lời trực tiếp trong chat cho phép nối trace vào `agent/run.py`, tạo/cập nhật `AGENTS.md` và `README.md`, và ghi mục phê duyệt này.

- Owner: Codex. Reviewer/PO: Phạm Minh Triết; duyệt riêng sau mỗi giai đoạn G1–G4.
- Phạm vi: trace JSONL, server localhost chỉ đọc, giao diện replay/live và test; chỉ dùng trace tổng hợp vô hại để phát triển.
- Giới hạn: không đọc `data/samples/`, không chạy mã gói npm, không sửa `package.json`, không phát lệnh từ viewer, không tải thư viện ngoài.
- Cơ sở: repo sạch trước khi sửa; `agent/run.py` có trace dạng danh sách cho test; chưa có `agent/loop.py`, `tools/actions.py`, `AGENTS.md` hoặc chỉ mục CodeGraph.

## Gate B0 — bổ sung phạm vi dữ liệu tuần 2

DECISION: APPROVED FOR IMPLEMENTATION
PO: Phạm Minh Triết
APPROVED_AT: 2026-10-24 Asia/Saigon
EVIDENCE_REFERENCES: yêu cầu trực tiếp trong chat “Hoàn thiện công việc tuần 2”.

- AS-IS: `labels.csv` chỉ có header 7 cột, lệch hợp đồng 11 cột của AGENTS gốc; `prepare_labels.py` chưa có bộ đọc `experiments/dataset.py`; ba ứng viên malware chưa được TV2 kiểm tra. Các thay đổi VIZ-1 đang uncommitted được giữ nguyên.
- Phạm vi: đồng bộ hợp đồng CSV và test, bổ sung metadata ứng viên lành cùng hồ sơ kiểm tra; sửa đường gọi `npm.cmd` để `fetch_package` chạy trên Windows. Không thực thi install hook, không tải gói độc, không tự nhận đã kiểm tra chéo.
- Owner: Codex. Reviewer nhãn/PO: Phạm Minh Triết. Mốc dữ liệu v1 chỉ đạt sau khi TV2 xác nhận từng nhãn và bằng chứng file:dòng.
- Rollback: hoàn tác các thay đổi dữ liệu/code tuần 2; không có dữ liệu nhãn thật để di trú.

## Gate B0 — Dashboard giải thích từng bước (2026-10-24)

DECISION: APPROVED FOR IMPLEMENTATION
PO: Phạm Minh Triết
EVIDENCE_REFERENCES: yêu cầu trực tiếp trong chat về hiển thị việc agent đang làm, cách đọc từng đoạn mã và kiểm chứng ở mỗi bước.

- Phạm vi: bổ sung thông tin giải thích và đoạn mã đã được `read_file` đọc vào trace phục vụ dashboard cục bộ; hiển thị số dòng, file, kết quả, giới hạn hiển thị rõ ràng trong replay/live.
- Giới hạn: chỉ hiển thị văn bản đã đọc từ fixture/gói được chọn, không chạy mã npm, không đọc `data/samples/`, không gửi trace ra mạng ngoài. Mã gói và lời mô hình là dữ liệu không tin cậy, phải escape hoặc dùng `textContent`.
- Owner: Codex. Reviewer agent: TV2; Reviewer/PO giao diện: Phạm Minh Triết.

## Gate B0 — sửa các lỗi điều tra gói theo tài liệu 5 vấn đề (2026-10-24)

DECISION: APPROVED FOR INCREMENTAL IMPLEMENTATION
PO: Phạm Minh Triết
EVIDENCE_REFERENCES: Yêu cầu trực tiếp trong chat “fix từng cái, ko cần sửa hết đâu, sửa được bao nhiêu thì cứ sửa”; tài liệu đính kèm “Hướng dẫn xử lý 5 vấn đề nghiêm trọng của DA_AgentNPM”.

- AS-IS: `main` sạch tại `ff9873d`; `read_manifest` đọc đủ file nhưng `agent/run.py` đọc lại 150 dòng đầu, bỏ qua manifest dài; vòng lặp buộc đọc file ngoài `package.json` cả khi script viết thẳng; dòng minify có thể vượt giới hạn kết quả; `labels.csv` chưa có nhãn kiểm tra chéo.
- Phạm vi được làm từng phần: sửa đọc manifest, xác định script/file đích, xử lý dòng dài ở công cụ đọc, chia dev/test theo nhãn và cụm, thêm kiểm soát quyết định nếu có đủ dữ liệu đầu vào; thêm fixture vô hại và test tương ứng.
- Giới hạn: không chạy install script, không tải/giải nén gói độc trên host, không tự gán nhãn thật, không tự duyệt gói chỉ vì thiếu lifecycle script, không ghi `package.json` hoặc gọi lệnh approve/deny thật. Các mục cần VM, dữ liệu nhãn và tích hợp OSV/canary được báo chưa hoàn tất.
- Owner: Codex. Reviewer agent/dữ liệu: TV2 (Phạm Minh Triết); kiểm tra chéo code và nhãn trước khi công bố kết quả thực nghiệm.
- Regression: giữ hợp đồng `Verdict` và đầu ra công cụ đang dùng; chạy pytest, semgrep và `git diff --check`. Rollback bằng hoàn tác commit sửa lỗi; không có migration dữ liệu.

## Gate B0 — tiếp tục xử lý an toàn 5 vấn đề (2026-10-24)

DECISION: APPROVED FOR SAFE CONTINUATION
PO: Phạm Minh Triết
EVIDENCE_REFERENCES: Yêu cầu trực tiếp trong chat “tiếp tục fix nốt các vấn đề”.

- Phạm vi: bổ sung script lọc dữ liệu để **chạy trong VM**, công cụ đọc và phân tích tĩnh, fixture vô hại, luật quyết định với ngưỡng và nhật ký dry-run; bảo toàn hợp đồng verdict hiện tại.
- Giới hạn an toàn tiếp tục áp dụng: không tải/giải nén mẫu độc trên host, không chạy install script, không ghi `package.json`, không gọi npm approve/deny thật và không tự gán nhãn.
- Owner: Codex; Reviewer: TV2/Phạm Minh Triết trước khi dùng kết quả thực nghiệm.

## Gate B0 — hoàn thiện tuần 1–3 và phần đầu tuần 4 (2026-10-25)

DECISION: APPROVED FOR SAFE IMPLEMENTATION
PO: Phạm Minh Triết
EVIDENCE_REFERENCES: yêu cầu trực tiếp trong chat ngày 2026-10-25 “hoàn thiện tất cả công việc còn tồn đọng ở tuần 1 - 2 - 3 và 1 nửa việc cho tuần 4”.

- Phạm vi: hoàn thiện probe model, hợp đồng công cụ và kiểm thử dữ liệu tuần 1–2; giới hạn quét tĩnh theo đường install, dấu vết sandbox và canary giả tuần 3; tích hợp công cụ tĩnh vào agent và phần bối cảnh chỉ đọc của tuần 4.
- Giới hạn: chỉ dùng fixture vô hại để test; không đọc `data/samples/`, không chạy gói npm thật trên host, không tự gán nhãn chưa kiểm tra, không cho agent gọi mạng ngoài, không gọi approve/deny thật. Nếu Ollama/Docker không sẵn sàng, báo NOT_RUN với bằng chứng.
- Owner: Codex. Reviewer agent/dữ liệu: Phạm Minh Triết (TV2). Reviewer sandbox: TV3/TV1 trước khi dùng với mẫu thật.
- Acceptance: test offline cho chức năng mới, pytest và Semgrep PASS; mốc nào cần bộ nhãn thật hoặc VM được ghi BLOCKED, không đánh dấu hoàn tất. Rollback bằng revert commit của đợt này; không có migration dữ liệu.

## Gate B0 — mở rộng kho ứng viên metadata (2026-10-25)

DECISION: APPROVED FOR METADATA-ONLY COLLECTION
PO: Phạm Minh Triết
EVIDENCE_REFERENCES: yêu cầu trong chat “enrich data, quá ít data, tôi cần 400-500 gói/mẫu (chỉ tìm, tổng hợp và thêm vào, ko chạy test tất cả các gói)”.

- Phạm vi: thu thập tên, phiên bản, lifecycle hook và URL nguồn công khai cho 400–500 ứng viên npm; ghi nguồn/phương pháp và kiểm tra cấu trúc, trùng lặp của CSV.
- Giới hạn: không tải tarball, không chạy gói, không đọc `data/samples/`, không chuyển `source_label` thành nhãn ground truth trong `labels.csv`; các dòng chưa có kiểm tra chéo giữ trạng thái ứng viên.
- Owner: Codex. Reviewer nhãn và tính đại diện: Phạm Minh Triết (TV2) trước khi dùng cho thực nghiệm.

## Gate B0 — duyệt bằng chứng nhãn tuần 2 (2026-10-29)

DECISION: APPROVED FOR STATIC LABEL REVIEW
PO: Phạm Minh Triết
EVIDENCE_REFERENCES: yêu cầu trực tiếp trong chat “duyệt tất cả 450 ứng viên metadata giúp tôi” và “hoàn thiện stuck tuần 2 luôn đi, ko dừng lại cho đến khi xong”.

- Phạm vi: kiểm tra tĩnh manifest và mã đúng phiên bản của ứng viên trong Docker dùng một lần; ghi `file:dòng`, nguồn và quyết định nhãn vào hồ sơ tuần 2; chỉ đưa gói có bằng chứng rõ vào `labels.csv`.
- Giới hạn: không chạy install script, không AI scan hàng loạt, không đưa tarball hay mã gói nghi vấn vào repo/host, không suy nhãn lành từ metadata; các gói thiếu bằng chứng giữ `needs_code_review`.
- Owner thực hiện: Codex theo ủy quyền TV2. Reviewer sử dụng dữ liệu cho thí nghiệm: Phạm Minh Triết.
