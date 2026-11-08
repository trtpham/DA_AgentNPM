# Tuần 05 — Hoàn thiện sandbox và công cụ mở rộng

## Kế hoạch

Bốn đầu việc gốc của tuần 5 (theo [kế hoạch tổng thể](KE_HOACH.md)):

- [x] Kiểm tra giới hạn mạng, quyền, RAM, PID, thời gian và dữ liệu mồi của sandbox (W5-1; chạy lại trên image 08/11: 14/14 test Docker PASS; RAM vượt 256 MB do swap — sửa opt-in, chờ TV3).
- [x] Chuẩn hóa kết quả tiến trình, file và kết nối thành JSON có thể đối chiếu với mã nguồn (W5-2, W5-3, `behavior_events` 07/11).
- [x] Chỉ nối `run_sandbox` vào agent sau khi chứng minh cách ly bằng mẫu mô phỏng (`sandbox: true`, chỉ gói thử vô hại; W5-5 nghiệm thu 08/11 — PO nghiệm thu thay TV3, xem [phiếu W5-5](giao-viec/W5-5_NGHIEM_THU_SANDBOX_TV3.md#biên-bản-nghiệm-thu-08112026)).
- [x] Bổ sung làm rõ mã bị rối khi cần; không mở rộng quá phạm vi install script (W5-7; thêm `decode_literal`, `resolve_value` 07/11).

### Kế hoạch chi tiết (lập ngày 04/11/2026)

**Hiện trạng khi bắt đầu tuần 5:**
- Container sandbox đã chạy với các cờ: `--network none`, `--read-only`, `--cap-drop ALL` (chỉ thêm `SYS_PTRACE`), `no-new-privileges`, 256 MB RAM, 64 tiến trình, 1 CPU, user 10001; `/input` chỉ đọc.
- `run_install.sh` chạy `npm install` dưới `timeout 60 strace -f`.
- Đã chạy lại 3 fixture vô hại ngày 03/11 và PASS.
- **Còn thiếu:**
  - chưa có fixture nào *chủ động thử vượt* từng giới hạn;
  - kết quả không phân biệt hết giờ (mã 124), hết RAM (137) hay lỗi thường; tất cả đều thành `sandbox execution failed`;
  - 4 lời gọi `connect()` của chính npm bị lẫn với hành vi của gói;
  - sandbox chưa nối vào agent.

**Nguyên tắc:** chỉ dùng **fixture vô hại** do nhóm viết trong `tests/fixtures/`. Không chạy gói npm thật hay mẫu độc trong sandbox tuần này. Mọi việc chạm `sandbox/` cần TV3 review, và việc nối vào agent cần Gate B0 riêng.

| ID | Việc | Owner / Reviewer | Phụ thuộc | DoD (bằng chứng phải có) |
| --- | --- | --- | --- | --- |
| **W5-1** | **Fixture thử vượt giới hạn**, mỗi cái chỉ làm đúng một việc vô hại trong `postinstall`: (a) gọi mạng ra ngoài (HTTP và DNS); (b) sinh 200 tiến trình con; (c) cấp phát khoảng 512 MB; (d) ngủ 120 giây; (e) ghi vào `/input`, `/etc`, `$HOME` ngoài thư mục gói; (f) đọc cả 3 file canary và biến môi trường canary. | Claude soạn / TV3 | — | 6 fixture mới. Test `tests/test_sandbox_limits.py` (tự bỏ qua khi không có Docker) chứng minh: (a) không kết nối được và có dấu vết; (b) dừng ở trần 64 tiến trình; (c) bị kill vì RAM; (d) bị dừng ở 60 giây; (e) ghi thất bại; (f) `canary_touched` đủ 4 loại. Bảng kết quả ghi vào nhật ký. |
| **W5-2** | **Phân loại kết quả chạy:** thêm trường `outcome` = `ok` / `timeout` / `oom` / `pids_limit` / `failed` dựa trên mã thoát và log, thay cho thông điệp chung. Hợp đồng `{ok, data, error}` giữ nguyên. | Claude / TV3 | W5-1 | Mỗi fixture của W5-1 ra đúng `outcome`; test đơn vị trên đầu ra giả lập. `ok` chỉ đúng khi `outcome = ok` và trace đầy đủ. |
| **W5-3** | **Gắn sự kiện với tiến trình:** dựng cây PID từ `strace -f`; mỗi `execve`/`connect`/`open` ngoài `/work` được gắn `actor` = `npm` hoặc `package` (tiến trình con của lệnh lifecycle). Đây là mục I5 trong kế hoạch cải thiện. | Claude / TV3 | W5-1 | Test trên log strace mẫu lấy từ fixture: `benign` và `no-hook` có **0** kết nối thuộc `package`, mạng của npm (nscd/DNS) vẫn được ghi riêng; fixture (a) có kết nối thuộc `package`. |
| **W5-4** | **Tái hiện và không chạm secret thật:** chạy mỗi fixture 3 lần, so sánh `outcome`, `canary_touched`, `actor`. Kiểm tra trace và stdout không chứa giá trị ngoài chuỗi `CANARY_…`; ghi digest image `agent-npm-sandbox:local`. | Claude / TV3 | W5-2, W5-3 | Bảng 3 lần × 9 fixture giống nhau ở mọi trường so sánh; tìm trong trace không thấy biến môi trường của host. |
| **W5-5** | **TV3 nghiệm thu cách ly** dựa trên W5-1…W5-4. | TV3 | W5-4 | TV3 xác nhận (ghi tên/ngày trong nhật ký). Chưa có xác nhận thì **không làm W5-6**. |
| **W5-6** | **Nối sandbox vào agent (chỉ fixture):** sandbox là bước tất định chạy *trước* model, không phải công cụ model tự gọi. `canary_touched` → R1 (deny). Sandbox lỗi, hết giờ hoặc trace thiếu → luôn `review`, không bao giờ approve. Tóm tắt hành vi đã gắn `actor` được đưa vào prompt dưới dạng dữ liệu không tin cậy. | Claude / TV2 + TV3 | W5-5, **Gate B0 mới** | Test: canary chạm → deny; sandbox lỗi/timeout → `review`; fixture lành vẫn approve. Chạy lại ma trận 3 fixture × 3 model; ghi so sánh trước/sau. |
| **W5-7** | **Làm rõ mã bị rối (chỉ khi cần):** thêm 1 fixture vô hại có mã rút gọn/base64 trên đường install để kiểm tra `deobfuscate` + `#pretty`. Chỉ sửa nếu fixture lộ lỗi. | Claude / TV1 | — | Fixture qua được với ít nhất A-LLM; nếu không cần sửa thì ghi "không thay đổi". |
| **W5-8** | **Đóng I3 (A-LLM chậm):** đo riêng thời gian nạp prompt, thời gian sinh và thời gian nạp model mỗi lượt (`prompt_eval_duration`, `eval_duration`, `load_duration` của Ollama). So `num_ctx` 16384 với 8192 (giá trị trong AGENTS §6.7). | Claude / TV2 | — | Xác định nguyên nhân bằng số đo. Nếu sửa: A-LLM trung vị trên 13 gói dev giảm ≥ 25% so với 50,7 giây, kết luận không đổi; nếu chưa đạt thì ghi FAIL kèm nguyên nhân. |
| **W5-9** | **I7 — cấu hình đúng AGENTS §6.7:** đưa `num_ctx`/`temperature` vào `experiments/configs/*.yaml`; `run_meta.json` đọc từ YAML. | Claude / TV2 | W5-8 (chốt `num_ctx`) | Đổi tham số chỉ bằng YAML; test đọc cấu hình; `run_meta.json` khớp YAML. |
| **W5-10** | **Dữ liệu (song song):** (1) người kiểm tra chéo điền 4 phiếu `data/review_rounds/` từ bằng chứng đã chuẩn bị; (2) chọn ứng viên họ/chiến dịch mới cho tập `test` từ 450 ứng viên và OSV, chuẩn bị bằng chứng trong container dùng một lần. Chưa gán nhãn khi chưa có người duyệt. | Reviewer nhãn (người thật) / TV1 | — | `review_sheet check` trả `complete: True` cho các phiếu đã điền; có danh sách ứng viên test mới kèm nguồn. Không có reviewer thì ghi BLOCKED. |
| **W5-11** | **Báo cáo:** cập nhật nhật ký này và viết `BaoCaoTienDo_Tuan05.md` theo khung LMS. | Claude / PO | tất cả | Có số liệu thật, ảnh thật nếu có, ghi rõ PASS/FAIL/BLOCKED. |

**Thứ tự gợi ý trong tuần:**
1. **Ngày 1–2:** W5-1 → W5-2 → W5-3. Chạy W5-8 song song vì không đụng sandbox.
2. **Ngày 3:** W5-4; gửi TV3 nghiệm thu (W5-5); xin Gate B0 cho W5-6.
3. **Ngày 4:** W5-6 nếu đã có nghiệm thu và Gate; nếu chưa thì làm W5-7, W5-9.
4. **Ngày 5:** đo lại toàn bộ, W5-11.
5. W5-10 chạy song song cả tuần, phụ thuộc người kiểm tra.

**Rủi ro và cách xử lý:**
- **Docker Desktop trên Windows giới hạn RAM/PID khác Linux thật:** ghi rõ môi trường đo. Nếu một giới hạn không áp được thì ghi FAIL, không nới fixture cho PASS.
- **Fixture thử vượt giới hạn có thể làm treo máy:** mọi fixture chỉ chạy trong container có `--memory`/`--pids-limit`, trong thời gian giới hạn, và không bao giờ chạy trên host.
- **Nối sandbox làm agent chậm hơn:** đo thời gian trước/sau ở W5-6. Sandbox chỉ chạy cho gói có hook.
- **Thiếu người kiểm tra nhãn:** W5-10 ghi BLOCKED; không ảnh hưởng mốc sandbox của tuần 5 nhưng chặn tuần 7–8.

## Mốc nghiệm thu

Sandbox trả kết quả có thể tái hiện và không chạm secret thật; lỗi sandbox không làm agent tự approve.

## Nhật ký

### W5-1 — fixture thử vượt giới hạn sandbox (2026-11-04)

- **Ngày / người thực hiện / người kiểm tra:** 2026-11-04 / Claude (Gate B0 W5-1, W5-8 ngày 04/11) / chờ TV3 review.
- **Đã làm:**
  - 6 fixture vô hại trong `tests/fixtures/sandbox-limits/`; mỗi cái có `postinstall: node probe.js` và in dòng `W5RESULT …`.
  - Test `tests/test_sandbox_limits.py`: chỉ chạy khi đặt `RUN_SANDBOX_TESTS=1` và đã build image; mặc định tự bỏ qua.
  - Không sửa `sandbox/`.
- **Kiểm chứng:** chạy `RUN_SANDBOX_TESTS=1 py -3.14 -m pytest tests/test_sandbox_limits.py` với image `agent-npm-sandbox:local` (`sha256:b657e0130392…`), Docker 29.1.3 trên Windows → **PASS 6/6** (khoảng 76 giây).

| Fixture | Script cố làm gì | Kết quả quan sát | Đánh giá |
| --- | --- | --- | --- |
| `network` | HTTPS tới một IP ngoài, tra DNS `example.com` | `https=ENETUNREACH`, `dns=EAI_AGAIN`; 9 lời gọi `connect()` được ghi | PASS: không ra được mạng, vẫn có dấu vết |
| `processes` | sinh 200 tiến trình `sleep` | 158/200 bị từ chối (trần `--pids-limit 64`) | PASS; trace vượt trần 2 MB nên `ok=False` ("trace incomplete") |
| `memory` | cấp phát khoảng 512 MB | dừng ở 192 MB, `Killed`, mã thoát **137** | PASS: trần `--memory 256m` có tác dụng |
| `timeout` | chờ 120 giây | bị dừng, mã thoát **124**, không in `completed` | PASS: `timeout 60` có tác dụng |
| `write-outside` | ghi vào `/input`, `/etc`, `/usr/local`, `$HOME` | ba đường đầu `EROFS`; `$HOME` (tmpfs 1 MB trong container) ghi được và **có trong** `files_outside_package` | PASS: không ghi được vào gói gốc hay hệ thống; ghi trong container được ghi nhận |
| `canary-all` | đọc `.npmrc`, `.ssh/id_rsa`, `.aws/credentials`, in biến môi trường canary | `canary_touched = [npmrc, ssh, aws, environment]` | PASS |

- **Phát hiện chuyển cho W5-2 / W5-3:**
  - Mã 124 (hết giờ) và 137 (hết RAM) hiện chỉ hiện trong `returncode`, thông điệp vẫn chung chung là `sandbox execution failed`. W5-2 sẽ thêm trường `outcome`.
  - Fixture sinh nhiều tiến trình làm trace vượt 2 MB, nên sandbox kết luận "không đầy đủ". Đây là hành vi an toàn đúng, nhưng W5-3 cần tóm tắt trace theo tiến trình để vẫn đọc được.
  - Lời gọi `connect()` của chính npm (nscd/DNS) vẫn lẫn với lời gọi của gói. W5-3 sẽ gắn `actor`.

### W5-2, W5-3 — `outcome` và `actor` trong kết quả sandbox (2026-11-04)

- **Ngày / người thực hiện / người kiểm tra:** 2026-11-04 / Claude (Gate B0 tuần 5 ngày 04/11) / chờ TV3 review.
- **Đã làm (`sandbox/run.py`; hợp đồng `{ok, data, error}` và các trường cũ giữ nguyên):**
  - `outcome` = `timeout` (mã 124) / `oom` (137) / `pids_limit` (`clone`/`fork`/`vfork` trả `EAGAIN` trong trace) / `failed` / `ok`. Mỗi loại có thông điệp lỗi riêng. Thêm `trace_complete`. `ok` chỉ đúng khi `outcome = ok` và trace đầy đủ.
  - `by_actor`: dựng cây PID từ `strace -f` (kể cả luồng và dòng `<... resumed>`). Gắn `execve` thành công, `connect` và `open` ngoài `/work` cho `npm`, `package` (cây con của `sh -c` mà npm chạy cho lifecycle) hoặc `unknown` (cha bị cắt khỏi trace). Gốc `npm` phải là chính lệnh `npm install`; tiến trình mồ côi trong trace bị cắt **không** bị tính là npm.
  - 3 log strace thật (đã lọc, khoảng 15 KB) trong `tests/fixtures/strace/` lấy từ các lần chạy fixture trước đó.
- **Kiểm chứng (chưa có Docker trong phiên này):** test đơn vị trên đầu ra giả lập và trace thật.
  - `benign`, `no-hook`, `canary`: `package` có **0** kết nối; `npm` có 4 (nscd + DNS cổng 53).
  - Canary đọc `/home/agent/.ssh/id_rsa` được gắn cho `package`.
- **Còn thiếu (NOT_RUN):**
  - Chạy 6 fixture W5-1 để xác nhận `outcome` thật và kết nối của fixture `network` thuộc `package`. Cần bật Docker Desktop; làm cùng W5-4.
  - Fixture `processes` vượt trần 2 MB nên đầu trace bị cắt; phần lớn sự kiện sẽ là `unknown`. Hướng này an toàn nhưng chưa đọc được trọn.

### W5-2, W5-3 (chạy thật) và W5-4 — tái hiện, không chạm secret thật (2026-11-05)

- **Môi trường:** Docker 29.1.3 (Docker Desktop, Windows), image `agent-npm-sandbox:local` = `sha256:b657e0130392664d3bf49d80af7055ab9f5319265839111270e0b11610242b82` (giống W5-1). Chỉ chạy fixture vô hại của nhóm.
- **Test Docker:** `RUN_SANDBOX_TESTS=1 py -3.14 -m pytest tests/test_sandbox_limits.py` → **8/8 PASS** (79,5 giây). Test có thêm khẳng định `outcome`, `by_actor` và 2 fixture cũ không có kết nối của gói.
- **9 fixture × 3 lần:** cả 3 lần giống hệt nhau ở mọi trường so sánh (`ok`, `error`, `returncode`, `outcome`, `trace_complete`, `canary_touched`, số kết nối theo `actor`).

| Fixture | `outcome` | `ok` | Mã thoát | Kết nối npm / package / unknown | `canary_touched` |
| --- | --- | --- | --- | --- | --- |
| `network` | ok | ✔ | 0 | 4 / **5** / 0 | — |
| `processes` | **pids_limit** | ✘ | 0 | 0 / 0 / 4 (đầu trace bị cắt) | — |
| `memory` | **oom** | ✘ | 137 | 4 / 0 / 0 | — |
| `timeout` | **timeout** | ✘ | 124 | 6 / 0 / 0 | — |
| `write-outside` | ok | ✔ | 0 | 4 / 0 / 0 | — |
| `canary-all` | ok | ✔ | 0 | 4 / 0 / 0 | npmrc, ssh, aws, environment |
| `benign-package` | ok | ✔ | 0 | 4 / **0** / 0 | — |
| `no-hook-package` | ok | ✔ | 0 | 4 / **0** / 0 | — |
| `canary-package` | ok | ✔ | 0 | 4 / 0 / 0 | ssh, environment |

- **Không chạm secret thật:**
  - So mọi biến môi trường của máy thật (giá trị từ 8 ký tự) với trace, stdout và stderr; script chỉ in tên biến.
  - Chỉ trùng `HEADROOM_HOST`, có giá trị là `127.0.0.1`, vốn có sẵn trong mọi container. Không phải rò rỉ.
  - Chuỗi canary duy nhất xuất hiện là `CANARY_ENV_FAKE_WEEK3` (giả), chỉ ở 2 fixture canary.
- **Đánh giá:**
  - W5-2 **PASS**: mỗi fixture ra đúng `outcome`.
  - W5-3 **PASS**: `benign`/`no-hook` có 0 kết nối thuộc `package`; `network` có 5 kết nối thuộc `package`; mạng của npm được ghi riêng.
  - W5-4 **PASS**.
  - **Giới hạn còn lại:** `processes` làm trace vượt 2 MB nên đầu trace mất, sự kiện thành `unknown`. Kết quả vẫn `ok=False`, không thể thành approve.
- **Bước tiếp:** gửi TV3 nghiệm thu cách ly (W5-5) dựa trên W5-1…W5-4. Chưa có xác nhận thì không làm W5-6.

### W5-7 — fixture mã rút gọn/base64 (2026-11-04)

- Thêm `tests/fixtures/packages/obfuscated-package`: `postinstall` chạy `install.min.js`, một dòng dài 1.706 ký tự (vượt `MAX_LINE_CHARS` 1000). Script giải base64 thành câu ghi chú vô hại rồi ghi file trong thư mục gói.
- Công cụ tĩnh: `extract_indicators` thấy `decode` và `base64`; `deobfuscate` cho 130 dòng `#pretty` và giải được base64 ở `#pretty:124`. Có test hồi quy trong `tests/test_static.py`.
- **Chạy A-LLM (05/11): fixture lộ lỗi thật, đã sửa.**
  - Lần 1 (`w57-obf-a-llm`): A-LLM đọc dòng 1 bị cắt rồi kết luận "nội dung bị cắt nên có payload ẩn" (`suspicious`/`review`); **không gọi `deobfuscate`**.
  - Nguyên nhân 1: kết quả `read_file` chỉ có cờ `truncated`, không nói phải làm gì.
  - Nguyên nhân 2 (chính): một lần đọc, dù bị cắt, đã được tính là "đã đọc nguồn", nên agent chuyển ngay sang lượt kết luận, lúc không còn công cụ nào để gọi.
- **Sửa (`agent/run.py`, không đổi luật approve/deny, không đổi schema):**
  - Khi một file `.js/.cjs/.mjs` bị cắt dòng, kết quả gửi model có thêm `hint`: gọi `deobfuscate`, đọc `file#pretty`, trích `file#pretty:dòng`.
  - File bị cắt chỉ được tính là đã đọc khi bản `#pretty` đã xem đủ, hoặc sau **2 lượt** model kể từ lần đọc bị cắt. Lượt trả lời bằng chữ cũng tính, nên không thể kẹt.
  - Lời nhắc khi model nộp kết luận sớm nêu đúng việc cần làm.
  - Luật cũ giữ nguyên: nguồn bị cắt không được approve.
- **Sau khi sửa (`w57c-obf-a-llm`):**
  - Quy trình: `read_file` → `deobfuscate` → đọc `#pretty:120-130`.
  - Trích `install.min.js#pretty:124` và `:126`; phân tích đúng: giải base64 rồi ghi file trong thư mục gói.
  - Kết luận `suspicious`/`review` (R8), vì bản `#pretty` mới đọc một phần và luật không cho approve nguồn chưa đọc trọn. Thận trọng nhưng đúng thiết kế.
  - Đánh giá: **PASS về quy trình và bằng chứng**. Model chưa tự đọc hết `#pretty` để có thể ra `benign`.
- **Hồi quy 3 model × 13 gói dev (`w57-reg-*`):**

| Model | Nhãn / hành động / luật so với mốc | Trung vị giây/gói (mốc) | Bước TB (mốc) |
| --- | --- | --- | --- |
| A-LLM (mốc `w58-a-llm-gpu99`) | 13/13 giống | 45,7 (47,0) | 3,8 (4,0) |
| A-SLM (mốc `i3b-dev-a-slm-20261104`) | 13/13 giống | 11,5 (12,0) | 2,5 (2,7) |
| A-TLM (mốc `i3b-dev-a-tlm-20261104`) | 12/13; `no-hook` R7_review → **R2** | 8,8 (8,4) | 4,5 (4,4) |

  - Ca A-TLM **không do W5-7**: gói `no-hook` không có lần đọc bị cắt nào. Model lặp 4 lần cùng một verdict trích `package.json:1` mà nó chưa đọc, rồi rơi về R2 (`review`).
  - Lỗi y hệt đã có ở lô `week4-dev-a-tlm-20261103`, tức là độ dao động đã biết của model 0.8b (I2).
- **Kiểm chứng:** `py -3.14 -m pytest` → **138 PASS, 8 SKIP**. Hai test cũ về nguồn bị cắt được cập nhật cho luồng mới; khẳng định "không approve" giữ nguyên.

### W5-8 — nguyên nhân A-LLM chậm (đóng I3) (2026-11-04)

- **Cách đo:** script bọc kết nối Ollama của agent, không sửa code agent. Ghi `load_duration`, `prompt_eval_*`, `eval_*` mỗi lượt và `/api/ps` (`size` so với `size_vram`). Chạy trên 13 gói dev (3 fixture + 10 `@swc/core`). Kết quả trong `reports/w58-*/turns.jsonl`.

| Số đo trên 13 gói (38 lượt) | `num_ctx` 16384 | `num_ctx` 8192 | 16384 + `num_gpu: 99` |
| --- | --- | --- | --- |
| Trung vị giây/gói | 85,1 | 104,5 | **47,0** |
| Tổng nạp model / nạp prompt / sinh (giây) | 20,9 / 107,0 / 843,1 | 13,8 / 110,3 / 967,8 | — |
| Tốc độ sinh trung vị | 12,3 token/s | 10,9 token/s | **27,6 token/s** |
| Model trong VRAM | 3,6 / 6,7 GB | 3,5 / 6,4 GB | 6,0 / 6,0 GB |
| Nhãn, hành động, luật cuối | mốc | giống mốc 13/13 | giống mốc 13/13 |

- **Nguyên nhân:**
  - **86% thời gian là sinh token.** Ollama tự ước tính VRAM và chỉ đưa khoảng 55% model lên GPU 6 GB; phần còn lại chạy trên CPU.
  - Nạp prompt chỉ chiếm khoảng 11%. Đổi `num_ctx` không đổi phần trên GPU, nên 8192 không nhanh hơn. **Giữ 16384.**
- **Sửa (chỉ qua cấu hình, nhờ W5-9):** thêm `num_gpu: 99` vào `experiments/configs/A-LLM.yaml`. Ollama đưa toàn bộ model lên GPU (VRAM 5,9/6,1 GB).
- **Đánh giá DoD:**
  - So với lần đo cùng ngày, cùng code (85,1 s): **−45%**, kết luận giữ nguyên 13/13 → đạt.
  - So với con số cố định 50,7 s trong DoD: chỉ **−7% → FAIL theo chữ của DoD**. Mốc 50,7 s đo ở phiên bản code và điều kiện máy khác; lần đo I3 trước đó cùng code cũ đã ra 82–83 s.
  - **Quyết định của PO (05/11/2026, Phạm Minh Triết): dùng mốc A — lần đo cùng ngày, cùng code (85,1 s).** Lý do: mốc 50,7 s đo trước các thay đổi I1–I4 và không tái hiện được (cùng code đó đo lại ra 82–83 s); so cùng ngày, cùng code mới tách được tác dụng của đúng một dòng cấu hình.
  - **Kết luận W5-8: PASS** (−45%, kết luận giống mốc 13/13). I3 của kế hoạch cải thiện được đóng.
- **Rủi ro:** VRAM sát trần. Nếu ứng dụng khác chiếm GPU, Ollama có thể lỗi; khi đó agent rơi về `review` (R2), không tự approve. Nên tắt ứng dụng nặng GPU (trình duyệt 3D, game) khi chạy lô.

### W5-9 — tham số chat nằm trong YAML (AGENTS §6.7) (2026-11-04)

- `experiments/configs/*.yaml` có khối `options:` (`num_ctx`, `temperature`; A-LLM thêm `num_gpu`). `load_config` đọc khối này và từ chối khóa lạ.
- `run_batch` truyền `options` vào `analyze`. `run_meta.json` ghi `chat_options` đã gộp với YAML. CLI `agent.run` dùng chung `load_config`.
- Kiểm chứng: test đọc cấu hình, khóa sai, `run_meta` khớp YAML, payload gửi Ollama mang đúng giá trị. Lô `w58-a-llm-gpu99` có `run_meta.chat_options.num_gpu = 99`.
- **Kiểm chứng chung:** `py -3.14 -m pytest` → **137 PASS, 6 SKIP** (6 test sandbox cần `RUN_SANDBOX_TESTS=1` và Docker).

### W5-11 — báo cáo và chuẩn bị demo (2026-11-05)

- Viết [BaoCaoTienDo_Tuan05.md](BaoCaoTienDo_Tuan05.md) và [HUONG_DAN_DEMO_TUAN05.md](HUONG_DAN_DEMO_TUAN05.md) (kịch bản 15 phút, phân vai, dự phòng, câu hỏi thường gặp).
- Thêm `experiments/demo_sandbox.py`: chỉ chạy fixture của nhóm qua `run_sandbox` và in một bảng. Có test cho hàm dựng dòng.
- Chạy thử mọi lệnh trong kịch bản:
  - `demo-rehearsal-a-llm`: benign → approve (21,1 s); canary → deny R6 (14,5 s).
  - `demo-rehearsal-a-slm`: canary → **review** (A-SLM chưa nhận ra canary), nên demo ca độc dùng A-LLM.
  - Bảng sandbox đủ 9 fixture.
- **Phát hiện mới, chưa sửa (cần TV3):** lần chạy 05/11, fixture `memory` cấp phát được **448 MB** rồi mới bị kill (W5-1 ngày 04/11 dừng ở 192 MB).
  - Nguyên nhân: `--memory 256m` không kèm `--memory-swap`, nên Docker cho thêm 256 MB swap; trần thật là 512 MB.
  - Vẫn bị chặn (`oom`, mã 137) nhưng rộng gấp đôi thiết kế.
  - Đề xuất thêm `--memory-swap 256m` vào `sandbox/run.py`; chờ TV3 duyệt.
- Kiểm chứng: `py -3.14 -m pytest` → **139 PASS, 8 SKIP**.

### Giao việc W5-5 và W5-10 (2026-11-05)

- **W5-8:** PO chốt mốc A (cùng ngày, cùng code) → **PASS**, xem mục W5-8.
- **W5-5:** đã soạn hướng dẫn và checklist nghiệm thu cho TV3: [giao-viec/W5-5_NGHIEM_THU_SANDBOX_TV3.md](giao-viec/W5-5_NGHIEM_THU_SANDBOX_TV3.md). Trạng thái: **chờ TV3** (hạn đề xuất 07/11). W5-6 vẫn khóa.
- **W5-10:** đã soạn hướng dẫn kiểm tra chéo: [giao-viec/W5-10_KIEM_TRA_CHEO_NHAN.md](giao-viec/W5-10_KIEM_TRA_CHEO_NHAN.md).
  - Phân công đề xuất: TV1 lượt 1 + 4 (40 dòng), TV3 lượt 2 + 3 (36 dòng); TV2 chốt.
  - Hiện trạng: `check` cả 4 phiếu đều `pending` (20/18/18/20). Trạng thái: **chờ người kiểm tra** (hạn đề xuất 09/11).
- Tin nhắn soạn sẵn: [giao-viec/TIN_NHAN_GUI_NHOM.md](../../archive/giao-viec/TIN_NHAN_GUI_NHOM.md). Claude không gửi tin nhắn thay nhóm.

## Ảnh kết quả

Ảnh chụp màn hình thật của trình xem trace ngày 05/11/2026 (chi tiết chú thích trong báo cáo tuần 5):

![Lô 13 gói A-LLM](hinh-anh/tuan-05-viewer-lo-13-goi.jpg)
![Canary bị từ chối](hinh-anh/tuan-05-viewer-canary-deny.jpg)
![swc chuyển người xem](hinh-anh/tuan-05-viewer-swc-review.jpg)
![Mã rút gọn qua #pretty](hinh-anh/tuan-05-viewer-obfuscated-pretty.jpg)

## Chống học vẹt (L1–L4), bộ gói mô phỏng 22 gói, sắp xếp repo (2026-11-05)

Có 2 Gate B0 ngày 05/11 trong `docs/brownfield/TRANSITION_APPROVAL.md`. Owner: Claude. Reviewer: TV2.

### Đã làm

- **L1 — đánh giá mù:**
  - Model chỉ thấy bí danh `package-under-review`.
  - Các dòng `name`, `description`, `keywords`, `author`, `repository`… của `package.json` được thay bằng `"<hidden for blind review>"` trong bản model đọc. Số dòng giữ nguyên.
  - OSV/Registry không còn trong prompt; luật R5 vẫn dùng OSV.
  - Kết luận vẫn ghi tên thật vì code tự điền.
- **Đánh số dòng:** bản `read_file` model đọc có tiền tố `N| `.
  - Model hay trích lệch 1–2 dòng do tự đếm dòng. Trước đây lỗi này không bị phát hiện vì chỉ kiểm dòng có tồn tại.
  - Trace và bước kiểm bằng chứng vẫn dùng văn bản gốc.
- **L2 — từ vựng `technique` cố định (14 từ):** chỉ ràng buộc lúc model sinh câu trả lời; `Verdict` (AGENTS §6.5) không đổi.
  - Từ vựng chỉ tả việc dòng mã làm, không phán xét. Từ trung tính đứng đầu: `print-output`, `read-package-file`, `write-package-file`.
- **L3 — kiểm chứng ngữ nghĩa** (`agent/semantics.py`):
  - Dòng được trích phải chứa dấu hiệu của `technique`. Ví dụ `read-secret-file` cần `.npmrc`, `.ssh`…; `download-code` cần URL, `http.get`, `npm install`…
  - Lần lệch đầu tiên được gửi lại để model sửa. Từ lần sau, dòng đó không được tính là bằng chứng; nếu không còn bằng chứng nào thì R3.
  - Kết luận `malicious` phải có technique cụ thể (không dùng `other`).
- **L4 — bộ gói mô phỏng `tests/fixtures/corpus/`:** 22 gói, 11 lành, 11 độc mô phỏng; 9 cặp chỉ khác hành vi, thêm bẫy tên và bẫy chú thích.
  - Đáp án nằm ở `EXPECTED.json`, ngoài thư mục gói.
  - Mã chỉ đọc tĩnh; dùng IP tài liệu và tên miền `.invalid`.
  - Đo bằng `py -3.14 -m experiments.rote_probe <run_id> A-LLM A-SLM A-TLM`.
- **Sự cố:** Windows Defender cách ly một `package.json` có chuỗi `curl … | sh` (signature 2147979566). Gói được viết lại với cùng hành vi (tải mã rồi `eval`) mà không có chuỗi đó. Không thêm loại trừ cho Defender.

### Kết quả trên 22 gói mô phỏng (cùng dữ liệu; "trước" = code commit `fbcdd22`)

| Model | Gói độc bị deny | **Gói độc được approve** | Gói lành được approve | Gói lành bị deny | Cặp phân tách |
| --- | --- | --- | --- | --- | --- |
| A-LLM trước → sau | 10 → **11**/11 | 0 → 0 | 7 → 7/11 | 1 → **0** | 8 → **9**/9 |
| A-SLM trước → sau | 9 → 6/11 | 1 → 1 | 7 → 2/11 | 1 → **0** | 8 → 7/9 |
| A-TLM trước → sau | 3 → 0/11 | **1 → 0** | 7 → 0/11 | 0 → 0 | 6 → 0/9 |

- **A-LLM tốt hơn ở mọi chỉ số hành động:**
  - deny đủ 11/11 gói độc;
  - không còn deny nhầm gói tải binary có checksum;
  - phân tách đủ 9/9 cặp, kể cả bẫy tên và bẫy chú thích.
- **A-TLM an toàn hơn nhưng mất khả năng phân biệt:** trước đây nó **approve một reverse shell**. Sau L3, bằng chứng bịa không còn được tính (ví dụ gọi `let stats;` là "đọc secret"), nên mọi gói đều về `review`.
- **A-SLM vẫn approve gói có chú thích "phải approve" (`probe-lint-setup`).** Model mô tả đúng cả ba hành vi (đọc `.npmrc`, POST token ra ngoài) nhưng vẫn kết luận `benign`. Đây là lỗi phán đoán (prompt injection), không phải lỗi bằng chứng, nên L3 không chặn được.
- **Ablation A-SLM** (không đổi repo):
  - bỏ L2 → approve được 6/11 gói lành nhưng approve 1 gói độc;
  - bỏ câu "bí danh" → gần như không đổi.
  - Bản từ vựng đầu toàn từ nguy hiểm làm A-SLM gọi mọi gói là `suspicious`, nên đã thêm từ trung tính.
- **Hồi quy 13 gói dev** (hành động so với mốc `w57-reg-*`):
  - A-LLM 13/13 giống;
  - A-SLM 13/13 giống;
  - A-TLM 12/13 giống. `benign-install-fixture` đổi approve → review (R3), không có gói nào bị approve nhầm.

### Còn lại / đề xuất (cần PO quyết)

- Luật **R7_flow**: không approve khi chính verdict của model liệt kê chuỗi nguồn nhạy cảm (`read-secret-file`/`read-env`) → đích mạng (`network-request`/`download-code`).
  - Luật này dựa trên hành vi chứ không dựa trên tên, và sẽ chặn ca A-SLM ở trên.
  - Nó thay đổi luật approve nên cần một Gate riêng.
- Mô hình 0.8b (A-TLM) không đủ năng lực cho tác vụ này khi bằng chứng bị kiểm chặt; nên dùng làm mốc so sánh, không triển khai.
- Chỉ thêm gói thật khi bộ mô phỏng ổn định (PO, 05/11).

### Sắp xếp repo (Gate B0 05/11)

- `ke-hoach-nhat-ky-tuan/` → `docs/tien-do/`; tài liệu bàn giao → `docs/ban-giao/`.
- Script dữ liệu → `data/scripts/`. Lệnh mới: `py -3.14 -m data.scripts.<tên>`.
- Fixture cơ bản → `tests/fixtures/packages/`; test Node → `tests/js/`.
- Xóa file tạm; `.gitignore` thêm `.claude/`, `.vscode/`, `.idea/` và file LMS.
- **Kiểm chứng:**
  - `py -3.14 -m pytest -q` → **159 PASS, 8 SKIP**;
  - `node --test tests/js/*.test.mjs` → **19/19 PASS**;
  - test Docker trên fixture cơ bản PASS;
  - 0 liên kết Markdown hỏng;
  - `data.scripts.review_sheet check` chạy đúng.

### W5-5 — Nghiệm thu cách ly (08/11/2026)

- Phạm Minh Triết nghiệm thu thay Nguyễn Đình Thiên, dựa trên lần chạy ngày 08/11 (ngoại lệ quy trình do PO quyết; TV3 chưa tự chạy lại).
- Căn cứ: test Docker `14 passed`; `repro_sandbox --runs 3`: `all_same: true`, `no_host_leak: true`; bảng 9 fixture trong [phiếu W5-5](giao-viec/W5-5_NGHIEM_THU_SANDBOX_TV3.md).
- Swap: phương án 1 — `--memory-swap 256m` là mặc định; fixture `memory` dừng ở 192 MB (trước 448 MB); test Docker chạy lại sau khi đổi: `14 passed`.
- Kết luận: **ĐẠT**. W5-6 mở cho gói thử vô hại; gói thật và corpus mô phỏng vẫn không chạy trong container.
