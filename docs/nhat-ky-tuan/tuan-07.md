# Tuần 07 — Hiệu chỉnh trên tập phát triển

## Kế hoạch

- [ ] Tính confusion matrix, Precision, Recall, F1, FPR và tỉ lệ suspicious (TV3-5).
- [ ] Quét ngưỡng 0,50–0,95 riêng cho từng model trên tập phát triển.
- [ ] Kiểm tra độ tin cậy, chọn ngưỡng và đóng băng cấu hình trước khi mở tập kiểm tra.
- [ ] **Báo cáo 2 cấu hình tách biệt** (PO chốt 05/11/2026):
  - **Chỉ agent:** tắt hoàn toàn tín hiệu OSV/Registry. Mô phỏng khoảng trống zero-day, khi danh sách đen chưa biết gói; đây là con số chính của đồ án.
  - **Agent + OSV:** hiệu quả cả hệ thống.
  - Thêm chỉ số: trong các gói OSV đã biết là độc, agent tự bắt được bao nhiêu khi **không** được biết trước.
  - Lý do: phần lớn mẫu độc lấy từ Datadog/OSV. Nếu để OSV chặn sớm, Recall sẽ là thành tích của danh sách đen chứ không phải của agent (rò rỉ nhãn, AGENTS §3).
- [ ] Nguyên tắc sản phẩm **"chặn trước, phân tích sau"**: OSV báo độc thì chặn giao gói ngay, nhưng agent vẫn phân tích bản cách ly để làm phiếu báo cáo có bằng chứng và đối chiếu với OSV. Agent không được thấy kết quả OSV khi phân tích.

## Mốc nghiệm thu

Có bảng ngưỡng, lý do chọn ngưỡng và script tái hiện; không dùng tập kiểm tra để điều chỉnh.

## Nhật ký

- **28/11/2026 — Hoàn thành T1 (Frontend 2D + sửa `run_id` và `"undefined"`):**
  - Hoàn thiện sửa `run_id = "run"` trong `viewer/server.py` (`_same_run`), thêm test nhận `run_id = "run"` và từ chối `run_id` khác; tăng tốc `_packages` trên lượt 300 gói (`test-v1-a-llm-x`: 0,168 s API, tải trang một gói 393 ms, tải trang tổng hợp 230 ms).
  - Thêm `GET /api/runs/<run>/summary` dùng lại `experiments.metrics.load_results` và `score` (tự nhận split, đối chiếu GuardDog, phân bố luật R1–R8, danh sách ca sai) và `GET /api/package-extra` (OSV, Registry, sandbox từ `reports/`). Mặc định đọc `data/labels-v1.csv`.
  - Sửa chữ `"undefined"` cạnh nhãn quyết định trong `viewer/static/office/main.mjs` và `explain.mjs` khi trace cũ thiếu trường `rule`.
  - Thiết kế lại giao diện 2D (`viewer/static/index.html`, `app.js`, `summary.mjs`, `style.css`): trang một gói 10 giây (thẻ kết luận, luật quyết định, hành vi theo bộ ba Nguồn → Hành động → Đích kèm tô dòng mã `read_file`, sandbox/OSV nếu có, đề xuất mô hình vs luật, nhật ký bước thu gọn) và trang tổng hợp lượt chạy (ma trận nhầm lẫn, P/R/F1/FPR, so GuardDog, phân bố luật, lọc ca sai). Giữ nguyên an toàn: `127.0.0.1`, GET/HEAD, `textContent`, giải mã base64 trong bộ nhớ, không có nút chạy agent.
- **Kiểm chứng (28/11/2026):**
  - `py -3.14 -m pytest -q`: **359 passed, 18 skipped, 0 failed** (18 test Docker giữ skip khi chưa đặt `RUN_SANDBOX_TESTS=1`).
  - `node --test tests/js/*.test.mjs`: **34 passed, 0 failed**.
  - Kiểm tra trình duyệt (`playwright-cli`): XSS trên `comment-injection-demo@1.0.0` hiện `<img src=x onerror=alert(1)>` dạng chữ (0 `<img>`, 0 dialog); WCAG 2.2 chế độ sáng/tối/375px có 0 nút nhỏ hơn 24 px, 0 lỗi tương phản < 4,5, `scrollWidth == clientWidth == 375`; văn phòng 3D không còn chữ `"undefined"`.
- **28/11/2026 — Hoàn thiện phần dở T2 (bước 1–2) và khảo sát khả thi QLoRA (T5 bước 1):**
  - Kiểm lại commit mới nhất của kho Datadog (`DataDog/malicious-software-packages-dataset`, `main`): vẫn là `72c723be547033c558244520524b117c8d71663b`.
  - Rà soát phần sửa dở trong `data/scripts/datadog_container.py` (`--since`, `--tag`, `sample_date`, `inspected_tag`) và `data/scripts/collect_public_candidates.py` (`--popular`, `--include-seen`, `popular_candidates`, `collect_popular`); kiểm định dạng `data/datadog/candidates-v2-batch-001.jsonl` (100 dòng, cùng lược đồ metadata triage như `candidates-batch-001..008.jsonl`, không chứa mã nguồn thô). Viết thêm unit test trong `tests/test_datadog_container.py` và `tests/test_collect_public_candidates.py` (11/11 test PASS).
  - Đo hiện trạng phục vụ khảo sát khả thi QLoRA `Qwen3.5-4B` trên RTX 3050 6 GB (`docs/ke-hoach/KHA_THI_QLORA_4B.md`, chưa cài thư viện): GPU trống `6001/6144 MiB`, RAM `16 GB`, `D:` trống `109,5 GB`, máy mới có Python `3.14`/`3.13` (chưa có `3.11`/`3.12`), WSL2 đã bật; đo từ 289 trace `test-v1-a-llm-x` cho thấy trung vị `1.973` token/bước (p95 `3.367`). Kết luận khả thi có điều kiện ở ngữ cảnh `2.048–3.072` (tối đa `4.096` với Unsloth/WSL2), cần Gate riêng để chọn môi trường và đo thật 10 bước.
- **28/11/2026 — Hoàn thành nháp `labels-v2` (T2 bước 2–7, pha 1), script trích mẫu SFT (T5 bước 3) và Báo cáo tuần 7 (T8):**
  - Quét `1.300` ZIP Datadog 2025–2026 trong container (`candidates-v2-batch-001..013.jsonl`; lô `005` bị Windows Defender khóa đọc trên host nên `load_datadog_v2` bỏ qua có cảnh báo, 12 lô còn lại cho **727** mẫu sạch có hook → đủ **600** mẫu độc sau lọc trùng `labels-v1` và giới hạn `<= 12`/cụm).
  - Thu thập và kiểm tĩnh trong container hai lượt gói lành phổ biến (`v2` `>= 20.000`/tháng: **386** gói, A=158/B=157/C=71; `v2b` `>= 3.000`/tháng: **167** gói, A=57/B=82/C=28) kết hợp các gói nhóm A/B chưa dùng từ `review_450` + `review_b2`, đối chiếu OSV theo `name@version` vào `data/osv-v2-cache.json`.
  - Dựng [labels-v2-draft.csv](file:///d:/DACN/DA_AgentNPM/data/labels-v2-draft.csv) và [README-v2-draft.md](file:///d:/DACN/DA_AgentNPM/data/README-v2-draft.md) bằng `data/scripts/build_labels_v2.py`: **1.411** dòng (`malicious`: **600** [2025: 340, 2026: 260, OSV `MAL-`: 547/600], `benign`: **781** [`npm-popular`: 406, `npm-search`: 375], `suspicious`: **30**); chia cụm `train`: **702** / `dev`: **281** / `test`: **428** (`0` cụm cắt đôi, `0` tên/cụm `test` v1 vào `train` v2); `time_split` (mốc `2026-03-02`): `after` **175** (`test & after`: **50**), `before` **425**, `unknown` **811**. Chưa đóng băng `data/labels-v2.csv` (chờ Gate riêng).
  - Tạo script trích mẫu hội thoại SFT cho tập `train` (`experiments/extract_sft.py` + `tests/test_extract_sft.py`, commit `1183da2`): lọc chỉ `split == "train"`, kiểm `final_label == nhãn thật` và mọi bằng chứng `exists == true`, loại kiểm chứng nội bộ `Evidence check` và làm mù tên gói (`BLIND_ALIAS`).
  - Soạn `docs/bao-cao-tuan/BaoCaoTienDo_Tuan07.md` (không nhắc AI, đủ số liệu thật và 6 ảnh T1 trước/sau).
  - Thêm cờ `--package` vào `experiments/run_isolated.py` (`resolve_npm_package`, Gate B0 28/11/2026) kèm test đơn vị (`tests/test_run_isolated.py`: 15/15 PASS) để quét live gói npm công khai bất kỳ trong container dùng một lần; chạy thử thành công `demo-live-tuan07` (2 fixture: benign approve R7, canary deny R6) và `demo-live-npm` (`@abc54d/postinstall-hello-world@1.0.0`, 10,7s, benign approve R7).
  - Bổ sung `viewer/benchmarks.py` (`GET /api/benchmarks`) và tab **Bảng & Ma trận** gọn, trực quan (thanh 4 KPI, tab lọc từng phần, so sánh 6 cấu hình & GuardDog, đối chiếu OSV luật R5, độ phủ sandbox VM `433/500 = 86,6%` kèm 67 ca thiếu A–F, quét ngưỡng dev `0,50–0,95`, thẻ thống kê `labels-v1` / `labels-v2-draft`); chuyển mặc định sang `test-v1-a-llm` để hiển thị đủ 3 cỡ `A-LLM`, `A-SLM`, `A-TLM` và thêm nút chuyển nhanh từ các run `-x` thiếu `A-TLM-X`.
- **Vướng mắc / bước tiếp:** chờ PO mở Gate đóng băng `labels-v2` (bước 8), Gate `sandbox/` (T3 — sửa `/tmp` nhóm A và log mã lỗi nhóm F rồi chạy lại trong VM), xác nhận chạy lô GPU `A-LLM-XS` (T4), duyệt Gate cài môi trường QLoRA 4B để đo 10 bước thật (T5 bước 2), và phiếu kiểm chéo mù từ 3 thành viên (T7).

## Ảnh kết quả

![Giao diện 2D trang một gói sau thiết kế lại](../hinh-anh/tuan-07-viewer-sau-goi.png)

![Trang tổng hợp lượt test-v1-a-llm-x](../hinh-anh/tuan-07-viewer-sau-tong-hop.png)

![Chế độ sáng và kiểm tra đáp ứng 375px](../hinh-anh/tuan-07-viewer-sau-375px.png)
