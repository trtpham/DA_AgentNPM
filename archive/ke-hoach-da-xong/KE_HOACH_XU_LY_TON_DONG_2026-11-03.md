# Kế hoạch xử lý tồn đọng — Claude tiếp nhận ngày 03/11/2026

Kế hoạch này bổ sung cho [bàn giao](../ban-giao/BAN_GIAO_CHO_CLAUDE_2026-11-03.md) (H0–H4). Thứ tự làm như sau: **đóng tồn đọng và vá lỗi đã xác minh trước**, sau đó mới cải thiện dần. Mỗi mục ghi Owner, Reviewer, điều kiện bắt đầu, DoD và việc cần PO quyết. Chưa có mục nào được đánh dấu xong.

## 0. Cơ sở của kế hoạch (đã kiểm ngày 03/11)

| Kiểm tra | Kết quả |
| --- | --- |
| `py -3.14 -m pytest -q` | PASS 72/72 |
| `git diff --check` | PASS |
| `main` so với `origin/main` | Trùng tại `cbdbcc2`; 5 mục untracked giữ nguyên |
| Ollama, Docker, Semgrep | NOT_RUN trong phiên này |
| Trace A-TLM `reports/week3-final-tlm-*` | Đã đọc. Nguyên nhân chạm 15 bước nêu ở mục B3 |

**Nguyên nhân A-TLM thất bại, đọc từ trace thật** (giả thuyết trước đó về `x.js` và kiểu `start`/`end` không phải nguyên nhân của hai ca này):

- `canary-package`: 13 lượt verdict chỉ cho 2 lỗi khác nhau. Model sinh khoảng 12.000 ký tự lặp ("(403-404)…") đến khi hết `num_predict`, nên JSON bị cắt (`EOF while parsing`).
- `no-hook-package`: 13 lượt cho đúng **1** lỗi lặp lại: `package` thiếu `@version` (`no-hook-fixture`) và `description` sai số từ.
- Lỗi gốc của vòng lặp: [run.py:194](../../agent/run.py) xóa lượt trả lời sai cùng lời nhắc sửa trước mỗi lượt kế tiếp. Với `temperature=0`, model thấy cùng ngữ cảnh nên sinh lại cùng câu trả lời; 12/15 bước bị lãng phí.

## Giai đoạn A — Dọn nền và khóa baseline (H0)

Chỉ sửa tài liệu/cấu hình, không đổi logic, nên nằm trong phạm vi được phép hiện có.

| ID | Việc | Owner / Reviewer | DoD |
| --- | --- | --- | --- |
| A1 | Đưa bản `AGENTS.md` gốc vào repo, ở `AGENTS.md` gốc hoặc `docs/AGENTS.md` | Claude / PO | Cần PO cung cấp file (bản gốc chỉ có trên máy, trong thư mục đính kèm Codex). File commit nguyên văn, ghi nguồn và ngày |
| A2 | Tạo `requirements.txt` ghi phiên bản thật đang dùng (pydantic, pytest…) và ghi "Python 3.14" trong README | Claude / TV2 | `py -3.14 -m pip freeze` đối chiếu import trong repo; trên môi trường sạch, pytest vẫn PASS 72/72 |
| A3 | Sửa `.gitignore` đang chứa `data/candidates.csv` dù file được theo dõi | Claude / TV1 | Bỏ dòng ignore hoặc ghi chú lý do; `git status` không đổi |
| A4 | Xử lý 5 mục untracked (`.week2_benign_audit_tmp.py`, `reports/.week3_fixture_runner.tmp.py`, `.pytest_week3_fix_tmp/`, DOCX/PDF LMS tuần 2) | PO quyết / Claude làm | PO chọn với từng mục: commit, chuyển vào `scripts/` có test, hoặc xóa. **Không xóa khi chưa được đồng ý** |
| A5 | Bảng môi trường: Python, pytest, Semgrep, Ollama (3 model), Docker | Claude / PO | Mỗi dòng ghi PASS/FAIL/NOT_RUN/BLOCKED, lệnh, ngày. Nếu sandbox công cụ chặn socket, nhờ PO chạy `ollama list`, `docker version`, `semgrep` rồi dán kết quả |

**Mốc A:** commit `chore: baseline after handoff` chỉ gồm A1–A3 cùng các file PO đã duyệt ở A4.

## Giai đoạn B — Vá lỗi agent đã xác minh (H2, phần sửa code)

**Cần PO phê duyệt Gate B0 mới trước khi làm** (mẫu ở mục 5). Lý do: B1–B2 thay đổi luật quyết định trong `agent/decide.py`/`agent/run.py`, B3 thay đổi cách sửa verdict. Mỗi mục làm theo trình tự: viết test thể hiện lỗi (FAIL) → sửa tối thiểu → test PASS → toàn bộ pytest → `git diff --check` → Semgrep khi chạy được.

### B1. Chặn approve tự động khi có chỉ báo rủi ro (ưu tiên cao nhất)

- **Vấn đề:** chỉ cần model trả `benign` với độ tin cậy ≥ 0,8 là gói được approve, kể cả khi `extract_indicators` đã thấy `child_process`, lệnh gọi mạng hoặc đường dẫn `.npmrc/.ssh/.aws` trên đường cài đặt. Một gói độc có thể chèn chỉ dẫn vào mã để dụ model trả `benign`.
- **Sửa:** thêm tham số `risk_indicators` vào `decide()`. Nếu có chỉ báo thuộc nhóm rủi ro (`child_process`, `network_api`, `sensitive_path`, `home_secret`, `eval`, `new_function`, `decode`) trên đường install thì kết quả là `review` theo luật mới `R7_risk`. Luật này chỉ chặn approve, **không** tự đổi nhãn thành `malicious`.
- **Test:** fixture vô hại có `postinstall` gọi `child_process.exec("echo ok")` cùng model giả trả `benign 0.95` phải ra `review/R7_risk`. Fixture `benign-package` hiện có vẫn được approve (dry-run).
- **DoD:** test mới PASS; 72 test cũ PASS; trace có `rule=R7_risk`.

### B2. Đường cài đặt gọi mã ngoài gói phải tính là chưa phân tích đủ

- **Vấn đề:** `"install": "node-gyp rebuild"`, `prebuild-install`, `npx …`, `curl … | sh` hoặc các lệnh tải mã khác không sinh file đích cần đọc, nên `auto_approve_allowed` vẫn bật. `binding.gyp` chỉ được đưa vào khi gói *không có* script `install`.
- **Sửa:**
  1. Đưa `binding.gyp` vào danh sách cần đọc khi bất kỳ hook nào gọi `node-gyp`, kể cả qua `||` hoặc `&&`.
  2. Hook có lệnh trong danh sách "mã ngoài gói" (`npx`, `curl`, `wget`, `prebuild-install`, `node-pre-gyp`, `npm install|i`…) thì đặt `analysis_incomplete=True`.
  3. Với `node scripts/x`, phân giải đích theo quy tắc của Node (`x`, `x.js`, `x/index.js`) để agent không kẹt khi model đọc `x.js`.
- **Test:** tham số hóa `test_script_targets…` cho từng mẫu lệnh, cùng một test agent cho thấy lệnh `npx` cho ra `review/R7_review`.
- **DoD:** như B1.

### B3. Vòng sửa verdict không được lặp y hệt (gỡ kẹt A-TLM)

- **Sửa trong code, không nới lỏng schema:**
  1. **Code tự điền `package`.** Agent đã biết `package_id` từ manifest, nên trước khi validate, ghi đè trường `package` bằng giá trị đúng. Đây là định danh chứ không phải phán đoán của model. Kiểm tra `package mismatch` giữ cho trường hợp model nhắc sai gói trong bằng chứng.
  2. **Phát hiện lặp.** Nếu nội dung hoặc lỗi validate trùng lượt trước, không gửi lại cùng ngữ cảnh. Lần đầu: giữ lại lượt sai để model thấy lỗi của chính nó (thay cơ chế xóa ở [run.py:194](../../agent/run.py)). Lần thứ hai vẫn trùng: dừng sớm, ghi `error kind=repeated_invalid`, trả về luật R2 `suspicious/review`.
  3. **Phát hiện bị cắt.** Đọc `done_reason == "length"` từ phản hồi Ollama; ghi `error kind=truncated_output` thay vì báo chung là `json_invalid`.
  4. Lời nhắc sửa ghi số từ thực tế của `description` (ví dụ "description có 19 từ, cần 5–15").
- **Test:** model giả trả cùng một verdict sai 3 lần thì dừng ở lượt 3 với `repeated_invalid` và không tốn đủ 15 bước. Model giả trả thiếu `@version` thì verdict vẫn hợp lệ.
- **Cập nhật test cũ:** `test_invalid_verdicts_do_not_accumulate_in_model_context` (giữ ý định "không tích lũy vô hạn", đổi thành "tối đa 1 lượt sai trong ngữ cảnh").
- **DoD:** offline PASS. Khi có Ollama: chạy lại ma trận 3 fixture × 3 model (B5).

### B4. Lỗi nhỏ đi kèm

- `read_manifest`: tìm dòng script bằng cách lần theo cấu trúc JSON ở cấp gốc, không regex trên toàn file. Test với manifest có `"config": {"scripts": {...}}` đặt trước `scripts` thật.
- `decide`: luật R4 không bao giờ chạy tới. Giữ lại kèm chú thích "phòng thủ", hoặc xóa (PO chọn); cập nhật test.
- `agent/run.py main()`: đọc YAML bằng `encoding="utf-8"`. Không thêm thư viện YAML nếu chưa duyệt `requirements.txt`.

### B5. Đo lại sau khi vá (cần Ollama)

- Ma trận cố định: 3 fixture (`benign`, `canary`, `no-hook`) × 3 model × **3 lần** mỗi ô, cùng commit và cấu hình. Ghi ở mỗi ô: verdict hợp lệ không, số bước, thời gian, `rule` cuối, loại lỗi.
- Lưu vào **chính** `docs/nhat-ky-tuan/tuan-03.md`, kèm `run_id` để viewer mở lại được.
- **DoD:** bảng đủ 27 lượt. A-TLM được phép FAIL, miễn kết thúc bằng fallback an toàn và **không còn** 15 bước lặp vô ích. Không suy rộng ra độ chính xác trên npm.

## Giai đoạn C — Đóng tồn đọng dữ liệu tuần 2 (H1)

Claude chuẩn bị, **người thật kiểm tra chéo**. Phạm vi "duyệt bằng chứng nhãn tuần 2" (29/10) đã có Gate B0.

| ID | Việc | Ghi chú |
| --- | --- | --- |
| C1 | Viết `data/scripts/review_sheet.py`: sinh phiếu kiểm tra cho từng lượt (ID, gói@phiên bản, nguồn, hash, `file:dòng`, trích đoạn mã, ô trống cho người kiểm tra/ngày/kết luận `verified/revise/exclude`) | Phiếu Markdown/CSV ngoài Git hoặc trong `data/review_rounds/`. Có test với dữ liệu giả |
| C2 | Lượt 1: 20 nhãn lành. Đã đối chiếu tự động nguồn và dòng; còn phải đọc ngữ nghĩa đường install | Claude điền phần tóm tắt hành vi; reviewer xác nhận |
| C3 | Lượt 2–4: 18 `npm-token-worm`, 18 `shai-hulud`, 17 `mut-4831` + `exnesss` + 2 nghi vấn | **Bị chặn** cho đến khi biết ZIP Datadog nằm ở đâu và có VM/container dùng một lần. Không đưa ZIP lên host hay Git |
| C4 | Sau mỗi lượt: `prepare_labels` ra file mới, kiểm tra không rò cụm, đủ 3 lớp ở 2 split | Chỉ sửa `labels.csv` khi đổi nhãn hoặc loại dòng |
| C5 | Ghi rõ giới hạn đại diện: test chỉ có 1 họ lành (esbuild), 1 chiến dịch độc chính (mut-4831), 1 gói nghi vấn | Ghi vào `data/REVIEW_WEEK2.md` và báo cáo; cân nhắc bổ sung họ/chiến dịch thay vì đổi split sau khi đã thấy kết quả |

**DoD C:** như mục H1 của bàn giao. Nếu chưa có reviewer, trạng thái là `BLOCKED — kiểm tra chéo`.

## Giai đoạn D — Viewer VIZ-1 G3–G4 (H3)

Đã có Gate B0 VIZ-1. Làm sau B vì B3 thêm loại lỗi mới vào trace.

1. **G3 replay:** `viewer/static/app.js` + `style.css` bằng tiếng Việt: danh sách run, bảng gói, dòng thời gian sự kiện, khung verdict và quyết định. Chỉ dùng `textContent`/`createElement`; không `innerHTML`, không `eval`, không thư viện ngoài (CSP `default-src 'self'` đã có).
2. **G4 live:** polling `/api/trace?after=seq` khoảng 1 giây cho run đang `running`; dừng polling khi gặp `run_end`.
3. **Test:** HEAD/GET, traversal, XSS với `<img src=x onerror=alert(1)>` trong `data_preview`; kiểm tra tay trên trình duyệt với 3 trace mẫu.
4. **DoD:** PO xem demo; `tools/visualize_agent.py` giữ nguyên đến khi viewer được nghiệm thu.

## Giai đoạn E — Cải thiện dần (sau A–D)

Làm theo thứ tự, mỗi bước cần một Gate B0 riêng nếu đổi hợp đồng.

1. **Bộ chạy lô có resume** cùng `run_meta.json` (commit, phiên bản Python/Ollama/model, cấu hình, hash dataset). Mỗi gói lỗi không làm dừng cả lô. Chỉ chạy trên tập đã duyệt.
2. **Tín hiệu bối cảnh tuần 4:** OSV `MAL-` (đã có tham số `osv_malicious` trong `decide`, chưa nối vào agent), metadata và diff phiên bản. Tín hiệu bối cảnh chỉ chặn approve, không thay thế bằng chứng mã.
3. **GuardDog baseline** trên đúng tập đã duyệt, ghi phiên bản, lệnh và đầu ra.
4. **Chốt ngưỡng trên dev, rồi chạy test một lần:** confusion matrix, Precision/Recall/F1/FPR kèm cỡ mẫu và số cụm; so sánh 3 model với GuardDog.
5. **Nối sandbox vào agent** (canary → R1) chỉ sau khi TV3 nghiệm thu riêng.
6. **Kiểm tra ngữ nghĩa bằng chứng:** đối chiếu nhận định của model với chỉ báo tĩnh trên cùng dòng, giảm rủi ro bằng chứng "có thật nhưng không liên quan".

## Trạng thái thực hiện (cập nhật 03/11)

- **A1 PASS:** `AGENTS.md` gốc (177 dòng) được chép nguyên văn từ tệp đính kèm Codex vào gốc repo.
- **A2 PASS:** `requirements.txt` (pydantic 2.13.2, pytest 9.1.1; Python 3.14.2); README ghi lệnh cài và lệnh test.
- **A3 PASS:** giữ dòng ignore `data/candidates.csv`, thêm chú thích: đây là đầu ra của `filter_datadog.py` trong VM, còn bản 5 dòng cũ được track có chủ đích.
- **A4 CHỜ PO:** 5 mục untracked giữ nguyên.
- **A5 PASS:** `ollama list` có `qwen3.5:9b/4b/0.8b`; Docker server 29.1.3; Node 24.13.0, npm 11.6.2; Semgrep `--config auto --error` trên `agent`, `tools` và test sửa đổi exit 0.
- **Gate B0 giai đoạn B:** PO duyệt trong chat ngày 03/11 và đã ghi vào `docs/brownfield/TRANSITION_APPROVAL.md`.
- **B1–B4 PASS offline:** pytest 82/82 (thêm 10 test); `git diff --check` PASS. Chênh lệch so với thiết kế ban đầu:
  - B1 không chặn mọi chỉ báo rủi ro. Theo AGENTS §3, verdict `benign` phải **dẫn đúng dòng** của từng chỉ báo rủi ro trên đường install; thiếu dòng nào thì ra `review/R7_risk` (lý do liệt kê `file:dòng` chưa giải thích).
  - B3: lần đọc trace cho thấy model *có* thấy lượt sai của nó, nhưng ngữ cảnh giống hệt nên ở nhiệt độ 0 nó lặp lại. Vì vậy khi lỗi lặp, lượt sau dùng `temperature=0.4` và `seed` cố định (tái hiện được). Lỗi giống nhau 4 lần liên tiếp thì dừng với `repeated_invalid` và trả R2.
- **B3 bổ sung:** trace live cho thấy A-SLM bọc verdict trong khối ```` ```json ```` khi lượt gọi không ràng buộc định dạng. Agent giờ bóc khối này trước khi parse; có test.
- **B5 PASS (FAIL có kiểm soát với A-TLM):** 27 lượt trên code cuối: A-LLM 9/9, A-SLM 9/9, A-TLM 1/9 verdict hợp lệ. Các lượt A-TLM thất bại dừng ở bước 6–8 với R2. Chi tiết ở nhật ký tuần 3.
- **Tuần 4 PASS (Gate B0 ngày 03/11):** `tools/intel.py`, `tools/actions.py`, `experiments/run_batch.py`, `experiments/baseline_guarddog.py`, `experiments/metrics.py`; chạy 3 model và GuardDog trên 10 bản swc thuộc dev cùng 3 fixture. Chi tiết ở nhật ký tuần 4.

### Việc chỉ người thật làm được (không phải nợ kỹ thuật)

1. **TV2 Phạm Minh Triết:** review diff `agent/run.py`, `agent/decide.py`, `tools/static.py` và ký nghiệm thu tuần 1–4.
2. **Reviewer nhãn khác người gán:** điền 4 phiếu `data/review_rounds/round-*.csv`. Lượt 2–4 đọc ZIP Datadog trong VM. Sau đó chạy `py -3.14 -m data.scripts.review_sheet check …` cho từng phiếu.
3. **PO:** nghiệm thu demo viewer G3–G4; quyết định 5 mục untracked (A4); quyết định có tách CSS dùng chung giữa `tools/visualize_agent.py` và viewer hay không.
- **C1 PASS:** `data/scripts/review_sheet.py` (`build`/`check`) có 2 test. Đã sinh `data/review_rounds/round-1..4.csv`: 20 + 18 + 18 + 20 = 76 dòng, cột kiểm tra để trống. **C2–C4 BLOCKED:** cần reviewer là người thật, cùng ZIP Datadog/VM cho lượt 2–4.
- **C5 PASS:** giới hạn đại diện của dev/test đã ghi vào `data/REVIEW_WEEK2.md`.
- **D PASS cục bộ:** `viewer/static/index.html`, `style.css`, `app.js` theo mẫu dashboard `tools/visualize_agent.py`. Đã kiểm tra trên trình duyệt:
  - replay chạy hết 8/8 sự kiện;
  - live tự nối sự kiện của run B5 đang chạy;
  - chuỗi `<img src=x onerror=alert(1)>` hiện dưới dạng chữ, không tạo phần tử `img`;
  - console không có lỗi;
  - khổ 375px không cuộn ngang.

  Test mới chặn `innerHTML`/`eval` trong `app.js`. Chờ PO nghiệm thu demo. `tools/visualize_agent.py` giữ nguyên.

## 4. Thứ tự và phụ thuộc

```
A (dọn nền) ──► B1, B2, B3, B4 (song song được, cùng đợt duyệt) ──► B5 (cần Ollama) ──► D (viewer)
C1 ──► C2 ──► C3 (chờ ZIP + VM + reviewer) ──► C4/C5 ──► E1…E4
```

Ước lượng công sức, chưa tính thời gian chờ người duyệt: A khoảng 0,5 ngày; B1–B4 khoảng 1,5–2 ngày; B5 khoảng 0,5 ngày máy chạy; C1–C2 khoảng 1 ngày; D khoảng 1,5 ngày.

## 5. Việc cần PO quyết trước khi bắt đầu

1. **Duyệt Gate B0 cho giai đoạn B.** Mẫu đề xuất (chỉ ghi vào `TRANSITION_APPROVAL.md` sau khi PO đồng ý):
   > Gate B0 — vá luật quyết định và vòng sửa verdict (2026-11-xx). Phạm vi: `agent/run.py`, `agent/decide.py`, `tools/static.py`, test và fixture vô hại liên quan. Thêm luật chặn approve `R7_risk`; coi lệnh gọi mã ngoài gói là phân tích chưa đủ; code tự điền định danh gói; dừng sớm khi verdict lặp. Không nới schema, không bật hành động thật, không chạy mã gói. Owner: Claude. Reviewer: TV2. Rollback: revert commit.
2. Gửi file `AGENTS.md` gốc (A1) và quyết định cho 5 mục untracked (A4).
3. Cho biết ZIP Datadog và VM/container để đối chiếu lượt 2–4 nằm ở đâu, ai là reviewer kiểm tra chéo cho từng lượt (C3).
4. Có cho Claude chạy Ollama/Docker trên fixture vô hại cho B5 không, hay PO tự chạy và gửi kết quả.
