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
