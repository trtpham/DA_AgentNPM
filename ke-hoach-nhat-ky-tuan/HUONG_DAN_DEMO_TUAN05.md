# Hướng dẫn demo tuần 5 cho giảng viên

> **Mục tiêu:** trong khoảng 15 phút, chứng minh bằng chạy thật rằng hệ thống **chạy ổn định, tái hiện được và an toàn**, và nói rõ đang vướng ở đâu, vì sao.
>
> Mọi lệnh dưới đây đã được chạy thử ngày 05/11/2026 trên máy của Triết. Thời gian ghi kèm là thời gian thật đo được.

## 0. Thông điệp chính (cả nhóm phải nói được)

1. **Agent tự điều tra và kết luận có bằng chứng `file:dòng`**, nhưng **quyết định cuối do luật cứng** (`agent/decide.py`), không do model. Model đề xuất "Cho phép 95%" vẫn có thể bị luật chuyển sang người xem (Hình 3 trong báo cáo).
2. **Không bao giờ chạy mã gói trên máy thật.** Mã gói chỉ chạy trong container: tắt mạng, chỉ đọc, giới hạn RAM, số tiến trình và thời gian. Tuần này nhóm đã thử vượt từng giới hạn và đều bị chặn.
3. **Kết quả tái hiện được:** 9 gói thử × 3 lần cho kết quả giống hệt nhau; mọi lần chạy lưu `run_meta.json` (commit, model, tham số).
4. **Vướng ở đâu và vì sao (nói thẳng, không né):**
   - nối sandbox vào agent đang chờ TV3 nghiệm thu cách ly;
   - Recall/F1 trên mẫu độc chờ người kiểm tra chéo nhãn.

   Cả hai là **cổng kiểm soát chất lượng có chủ đích**, không phải lỗi kỹ thuật.

## 1. Phân vai

| Người | Phần trình bày | Thời lượng |
| --- | --- | --- |
| **TV2 — Phạm Minh Triết** (agent) | Mở đầu, kiến trúc, demo agent chạy trực tiếp (bước 3–5), tốc độ A-LLM (bước 7) | ~7 phút |
| **TV3** (sandbox) | Demo sandbox (bước 6), giải thích cách ly, phần vướng nghiệm thu | ~4 phút |
| **TV1** (dữ liệu và công cụ) | Bộ nhãn, test tự động (bước 8), phần vướng kiểm tra chéo, kế hoạch tuần 6 | ~3 phút |

Một người lái máy (đề xuất Triết), hai người còn lại nói theo phần của mình. Người không nói thì cầm checklist ở mục 6 và theo dõi giờ.

## 2. Chuẩn bị

### Tối hôm trước (khoảng 30 phút)

1. **Dùng đúng máy đã chạy thử.** Thư mục `reports/` không có trên Git, các lượt chạy dự phòng chỉ nằm trên máy này.
2. Kéo code mới nhất và chạy test:
   ```powershell
   cd D:\DACN\DA_AgentNPM
   git log --oneline -3
   py -3.14 -m pytest -q
   ```
   Phải thấy **`139 passed, 8 skipped`**.
3. Bật **Docker Desktop**, kiểm tra image sandbox:
   ```powershell
   docker image inspect agent-npm-sandbox:local --format '{{.Id}}'
   ```
   Phải ra `sha256:b657e0130392…`. Nếu không có: `docker build -t agent-npm-sandbox:local sandbox`.
4. Bật **Ollama**, kiểm tra 3 model: `ollama list` phải có `qwen3.5:9b`, `qwen3.5:4b`, `qwen3.5:0.8b`.
5. **Chạy tổng duyệt** (đây cũng là bản dự phòng nếu hôm demo có sự cố):
   ```powershell
   py -3.14 -m experiments.run_batch demo-tongduyet-a-llm A-LLM --dir tests/fixtures/benign-package --dir tests/fixtures/canary-package
   py -3.14 -m experiments.demo_sandbox
   ```
   Kết quả mong đợi:
   - `benign` → `approve`, khoảng 21 giây;
   - `canary` → `deny`, luật R6, khoảng 15 giây;
   - bảng sandbox đủ 9 dòng như mục 2 của báo cáo, khoảng 90 giây.

### 30 phút trước giờ demo

1. **Tắt ứng dụng nặng GPU** (game, trình duyệt có nhiều tab video, phần mềm dựng 3D). A-LLM dùng gần hết 6 GB VRAM; nếu bị chiếm, Ollama có thể lỗi và agent rơi về "chuyển người xem".
2. Cắm sạc và tắt chế độ tiết kiệm pin, vì GPU bị hạ xung khi chạy pin.
3. Làm nóng model để lần chạy đầu không mất 20 giây nạp model trước mặt giảng viên:
   ```powershell
   ollama run qwen3.5:9b "ok" --keepalive 30m
   ```
4. Mở sẵn 3 cửa sổ:
   - **Terminal A:** trình xem trace
     ```powershell
     py -3.14 -m viewer --reports reports --port 8765
     ```
   - **Trình duyệt:** `http://127.0.0.1:8765/`, phóng to chữ (Ctrl +) cho máy chiếu.
   - **Terminal B:** để chạy lệnh demo. Phóng to font tới cỡ 18 trở lên.
5. Mở sẵn [BaoCaoTienDo_Tuan05.md](BaoCaoTienDo_Tuan05.md) ở chế độ xem trước Markdown để chiếu bảng và ảnh khi cần.

## 3. Kịch bản demo từng bước

> Mỗi bước gồm: **lời nói** (ý chính, nói bằng lời của mình), **thao tác**, **trên màn hình phải thấy**, **nếu hỏng thì làm gì**.

### Bước 1 — Mở đầu (TV2, 1 phút)

**Lời nói:**
- Đề tài: agent AI chạy cục bộ, kiểm tra gói npm có script tự chạy lúc cài (`preinstall`/`install`/`postinstall`).
- Agent kết luận lành / nghi vấn / độc hại, kèm bằng chứng, rồi đề xuất `npm approve-scripts` hoặc `deny-scripts`.
- Chạy bằng Ollama trên máy, so 3 cỡ model 9B, 4B, 0.8B.
- Tuần này tập trung vào sandbox: chứng minh mã gói bị nhốt chặt trước khi cho agent dùng.

**Thao tác:** chiếu mục 1 của báo cáo tuần 5.

### Bước 2 — Kiến trúc trong 30 giây (TV2)

**Lời nói:** luồng 4 bước, dùng đúng thuật ngữ trong đề cương:
1. **Nhận diện** hành vi nhạy cảm.
2. **Phân tích** theo bộ ba nguồn – hành động – đích.
3. **Kiểm chứng** bằng chứng: file và dòng phải có thật.
4. **Quyết định** bằng luật cứng R1–R8, luôn ở chế độ chạy thử.

**Thao tác:** chỉ vào panel "Quyết định" trên trình xem trace. Dòng chữ "Quyết định cuối do luật trong `agent/decide.py` đưa ra, luôn ở chế độ dry-run" là điểm then chốt.

### Bước 3 — Agent chạy trực tiếp: gói lành → Cho phép (TV2, 1,5 phút)

**Thao tác (Terminal B):**
```powershell
py -3.14 -m experiments.run_batch demo-live-a-llm A-LLM --dir tests/fixtures/benign-package --dir tests/fixtures/canary-package
```
Ngay sau khi chạy lệnh, chuyển sang trình duyệt, nhấn **F5**, chọn run **`demo-live-a-llm`**, rồi chọn gói **`benign-install-fixture@1.0.0`**. Trang tự cập nhật mỗi giây khi gói đang chạy.

**Trên màn hình phải thấy:** các bước lần lượt hiện ra: `read_manifest` → `extract_indicators` → `read_file postinstall.js` → kết luận **Lành tính · Cho phép · luật R7**. Toàn bộ mất khoảng 20 giây.

**Lời nói:**
- Script chỉ ghi một file đánh dấu trong thư mục gói.
- Agent đã đọc đúng dòng đó và luật cho phép vì bằng chứng đã được kiểm.
- Lệnh `npm approve-scripts` chỉ được *lập*, không chạy thật.

**Nếu hỏng** (Ollama lỗi hoặc quá chậm): chọn run **`demo-tongduyet-a-llm`** hoặc **`demo-rehearsal-a-llm`** đã chạy sẵn, nhấn **Phát lại**, và nói thẳng "đây là lượt chạy tổng duyệt tối qua".

### Bước 4 — Gói đọc khóa SSH → Từ chối (TV2, 1,5 phút)

**Thao tác:** cùng lượt chạy ở bước 3, chọn **`canary-fixture@1.0.0`**. Cuộn tới panel Quyết định.

**Trên màn hình phải thấy** (giống Hình 2 trong báo cáo):
- **Độc hại · malicious → Từ chối · luật R6**;
- bằng chứng `inspect.js:2`: đọc `/home/agent/.ssh/id_rsa`;
- bằng chứng `inspect.js:3`: in biến môi trường `CANARY_ENV`.

**Lời nói:**
- Khóa SSH ở đây là **giả**, chứa chuỗi `CANARY_…`. Nhóm không đưa secret thật vào bất cứ đâu.
- Bấm vào một bằng chứng để thấy mỗi kết luận đều chỉ ra được file và dòng.

### Bước 5 — Gói thật `@swc/core`: vì sao không tự động cho phép (TV2, 1 phút)

**Thao tác:** chọn run **`w57-reg-a-llm`** rồi gói **`@swc/core@1.7.36`**, hoặc chiếu Hình 3.

**Trên màn hình phải thấy:**
- "Mô hình đề xuất": **Lành tính · Cho phép · tin cậy 95%**;
- nhưng "Quyết định": **Chuyển kiểm tra thủ công · luật R7_review**, với lý do: script tải mã ngoài gói ở `postinstall.js:125`, thiếu 18 file `.node`, không đọc được `swc.wasi.cjs`.

**Lời nói:**
- Đây là điểm thiết kế quan trọng nhất: **model tự tin không có nghĩa là được cho phép.**
- Phần mã agent không nhìn thấy được thì luật buộc chuyển cho người xem.

**Mở rộng (nếu còn giờ):** chọn run **`w57c-obf-a-llm`**, gói mã rút gọn (Hình 4). Agent gọi `deobfuscate` và trích `install.min.js#pretty:124`. Đây là lỗi nhóm tự phát hiện và sửa trong tuần 5.

### Bước 6 — Sandbox: thử vượt từng giới hạn (TV3, 3 phút)

**Thao tác (Terminal B):** chạy 3 ca nhanh, khoảng 15 giây:
```powershell
py -3.14 -m experiments.demo_sandbox network canary-all write-outside
```
Trong lúc chờ, nói phần dưới. Sau đó chiếu **bảng đủ 9 dòng** (chạy sẵn từ tối hôm trước, hoặc bảng ở mục 2 báo cáo). Bảng đủ có ca `timeout` mất 60 giây nên không chạy trực tiếp.

**Lời nói:**
- Container chạy với `--network none`, hệ thống file chỉ đọc, bỏ mọi quyền đặc biệt (`--cap-drop ALL`), tối đa 256 MB RAM, 64 tiến trình, 60 giây. `strace` ghi mọi lời gọi hệ thống.
- Mỗi gói thử **cố tình phá một giới hạn**:
  - gọi mạng → `ENETUNREACH`;
  - 200 tiến trình → 158 bị từ chối;
  - hết RAM → bị kill, mã 137;
  - chạy quá lâu → bị dừng, mã 124;
  - ghi vào `/input` và `/etc` → `EROFS` (chỉ đọc).
- Cột **mạng npm/gói**: npm luôn tự tra DNS 4 lần; nhóm đã tách riêng. Gói lành có **0** kết nối của gói, gói thử gọi mạng có **5**. Trước tuần 5, hai loại này bị lẫn vào nhau.
- Chạy 3 lần thì kết quả giống hệt nhau, và không biến môi trường nào của máy thật lọt vào log.

**Trên màn hình phải thấy:**
- `network`: `https=ENETUNREACH dns=EAI_AGAIN`, mạng `4/5/0`;
- `canary-all`: canary chạm `npmrc, ssh, aws, environment`;
- `write-outside`: `/input=EROFS /etc=EROFS`.

**Nếu Docker hỏng:** chiếu bảng ở mục 2 báo cáo và chạy test không cần Docker, `py -3.14 -m pytest -q tests/test_sandbox.py` (21 PASS, có test trên trace thật).

### Bước 7 — Ổn định và tốc độ (TV2, 1 phút)

**Lời nói và chiếu bảng** "hồi quy 3 mô hình" ở mục 2 báo cáo:
- 13 gói × 3 mô hình chạy lại sau mỗi thay đổi; A-LLM và A-SLM giữ nguyên 13/13 kết luận.
- A-LLM chậm vì Ollama chỉ đưa 55% model lên GPU. Thêm **một dòng cấu hình** thì từ 85 giây xuống 47 giây mỗi gói, kết luận không đổi.
- Mọi tham số nằm trong `experiments/configs/*.yaml` và được ghi vào `run_meta.json` của từng lượt chạy, nên tái hiện được.

**Thao tác (tùy chọn):** mở `reports/w57-reg-a-llm/run_meta.json` để thấy commit, digest model và `chat_options`.

### Bước 8 — Test tự động (TV1, 30 giây)

**Thao tác:**
```powershell
py -3.14 -m pytest -q
```
**Phải thấy:** `139 passed, 8 skipped` trong khoảng 7 giây.

**Lời nói:**
- 8 test bị bỏ qua là test sandbox, chỉ chạy khi bật Docker. Bật Docker thì 8/8 PASS (khoảng 80 giây).
- Có test chặn path traversal, test chặn bằng chứng giả, test phát lại câu trả lời thật của model.

### Bước 9 — Đang vướng ở đâu (TV3 và TV1, 2 phút)

Chiếu bảng **"Còn vướng"** ở mục 4 báo cáo. Nói ngắn gọn từng dòng theo khung **vướng gì → vì sao → đã làm gì → khi nào xong**:
- **TV3:**
  - Nối sandbox vào agent đang chờ chính TV3 nghiệm thu cách ly. Bằng chứng nghiệm thu là bảng ở bước 6.
  - Nhóm tự phát hiện trần RAM thực tế là 512 MB do swap, và đã đề xuất cách sửa.
- **TV1:**
  - Chưa có Recall/F1 trên mẫu độc, vì nhãn phải được người thứ hai kiểm tra chéo; bằng chứng đã chuẩn bị sẵn cho 76 dòng.
  - Kế hoạch tuần 6: hoàn tất kiểm tra chéo rồi chạy thực nghiệm trong môi trường cách ly.

**Lưu ý:** **không nói "sắp xong" nếu chưa có ngày cụ thể.** Nói rõ việc nào cần người, việc nào cần máy.

### Bước 10 — Kết (TV2, 30 giây)

Tóm 3 ý: chạy ổn định (bằng chứng: bước 3, 4, 7, 8), an toàn (bước 6), trung thực về phần còn thiếu (bước 9). Mời giảng viên đặt câu hỏi.

### Bước phụ — Văn phòng 3D: kịch bản "Xe hàng" (TV2, 2–3 phút, nếu còn giờ)

**Thao tác:**
1. Mở `http://127.0.0.1:8765/office` bằng Chrome, nhấn **F11** cho toàn màn hình.
2. Để nguyên "Máy quay tự động", tốc độ 16×.
3. Chọn lần lượt 3 kịch bản, mỗi lần nhấn **phím cách**.

| Kịch bản | Thông điệp |
| --- | --- |
| **2. Gói độc ẩn trong cây phụ thuộc** | Một gói con độc thì cả xe bị giữ, gói vào cách ly, phiếu bay về máy người dùng |
| **5. swc → người xem cho qua** | Agent không tự quyết khi không thấy hết mã; con người là chốt cuối |
| **3. OSV: chặn trước, phân tích sau** | An toàn tức thì, nhưng vẫn có bằng chứng và không mất số liệu đánh giá |

**Lời nói:**
- Nhãn THẬT / MÔ PHỎNG / THIẾT KẾ trên mỗi thùng cho biết phần nào là kết quả thật của agent, phần nào là minh họa thiết kế sản phẩm.
- Xe tải và việc giao hàng là minh họa. Kết luận của từng thùng THẬT lấy đúng từ trace.

**Nếu máy yếu:** tắt "Máy quay tự động" và kéo thanh tiến trình. Cảnh vẫn đúng ở mọi thời điểm.

## 4. Câu hỏi giảng viên có thể hỏi và cách trả lời

| Câu hỏi | Ý trả lời | Bằng chứng mở ra ngay |
| --- | --- | --- |
| "Model bịa bằng chứng thì sao?" | Mọi `file:dòng` được kiểm có tồn tại và đã được đọc. Sai thì hạ xuống nghi vấn, không bao giờ cho phép | `tests/test_agent.py` (test bằng chứng giả); panel Quyết định → mục kiểm tra bằng chứng |
| "Sao không nhận diện theo tên gói/danh sách đen?" | Đề cương cấm học vẹt. Agent phân tích hành vi; tín hiệu OSV chỉ chặn tự cho phép, không bao giờ là bằng chứng | AGENTS.md §3; luật R5 trong `agent/decide.py` |
| "Gói độc chèn câu lệnh lừa agent?" | Nội dung gói luôn bọc `untrusted`; luật cứng không đọc lời của gói | Nhãn "Dữ liệu mã gói không tin cậy" trên trình xem |
| "Có chạy mã độc trên máy không?" | Không. Máy thật chỉ `npm pack` và đọc file; mã chạy duy nhất trong container tắt mạng; mẫu độc chỉ đọc trong VM | Bước 6; `sandbox/run.py` (các cờ Docker) |
| "Sao 10 gói swc lành mà không được cho phép?" | Không thấy hết mã sẽ chạy thì không cho phép, đó là chủ đích | Hình 3, lý do R7_review |
| "Model nhỏ có dùng được không?" | 4B nhanh gấp 4 lần và đúng 13/13 trên tập dev, nhưng bỏ lỡ ca canary; 0.8B dao động. Sẽ đo đầy đủ ở tuần 7–8 | Bảng hồi quy; run `demo-rehearsal-a-slm` |
| "Kết quả có tái hiện được không?" | `run_meta.json` ghi commit, digest model, tham số; chạy sandbox 3 lần cho kết quả giống hệt nhau | `reports/<run>/run_meta.json` |
| "Khi nào có chỉ số trên mẫu độc?" | Sau khi đủ kiểm tra chéo nhãn (dự kiến tuần 6), chạy trong VM tuần 7–8 | Bảng vướng ở mục 4 |

## 5. Sự cố thường gặp và cách xử lý ngay

| Sự cố | Xử lý |
| --- | --- |
| Trình duyệt không hiện run mới | Nhấn **F5**. Đường dẫn `#run=…&pkg=…` chỉ được áp dụng khi tải trang |
| Lần chạy đầu A-LLM rất chậm (~20 giây chưa có gì) | Model đang nạp vào GPU; lần sau nhanh. Tránh bằng bước làm nóng |
| Ollama báo lỗi, gói ra "R2 · chuyển người xem" | Đó là cơ chế an toàn: lỗi không bao giờ thành cho phép. Nói rõ điều này, rồi phát lại lượt tổng duyệt |
| `docker: cannot connect` | Docker Desktop chưa chạy xong; chờ biểu tượng cá voi chuyển màu xanh, hoặc dùng bảng trong báo cáo |
| Chữ tiếng Việt lỗi trong terminal | Dùng Windows Terminal; `demo_sandbox` đã tự đặt UTF-8 |
| Lệnh `run_batch` báo "different config" | Đặt `run_id` mới (ví dụ thêm `-2`); `run_id` cũ đã dùng cấu hình khác |

## 6. Checklist in ra giấy

- [ ] `py -3.14 -m pytest -q` → 139 passed (tối hôm trước)
- [ ] Docker chạy, image `sha256:b657e013…`
- [ ] Ollama có 3 model; đã làm nóng `qwen3.5:9b`
- [ ] Đã tắt ứng dụng nặng GPU, máy đang cắm sạc
- [ ] Lượt tổng duyệt `demo-tongduyet-a-llm`: benign approve, canary deny
- [ ] Đã chạy bảng `demo_sandbox` đủ 9 dòng (giữ cửa sổ kết quả)
- [ ] Trình xem trace mở ở `127.0.0.1:8765`, đã phóng to chữ
- [ ] Báo cáo tuần 5 mở ở chế độ xem trước
- [ ] Mỗi người thuộc phần nói của mình và 2–3 câu hỏi ở mục 4
- [ ] Sau buổi demo: ghi góp ý của giảng viên vào mục 1 báo cáo, thêm ảnh `tuan-05-buoi-bao-cao.jpg`
