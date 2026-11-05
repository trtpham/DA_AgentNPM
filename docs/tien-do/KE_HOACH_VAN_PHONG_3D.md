# Kế hoạch: "Văn phòng 3D" — trực quan hóa agent (đã duyệt 04/11/2026)

Ngày lập: 04/11/2026. Trạng thái: **ĐÃ DUYỆT 04/11/2026 — bắt đầu sau khi tuần 5 ổn định; chưa viết code.**

## 1. Đánh giá

**Kết luận: nên làm, nhưng giới hạn phạm vi.** Đây là lớp hiển thị chỉ đọc, phục vụ demo và báo cáo. Không đụng vào agent, sandbox hay luật quyết định, và không làm lệch mốc tuần 5–8.

### Được gì

- **Demo tuần 9–10 dễ hiểu hơn.** Hội đồng nhìn được 4 bước *nhận diện → phân tích → kiểm chứng → quyết định* (AGENTS §3) như một nhân viên đi qua từng phòng, thay vì đọc JSON.
- **So sánh 3 model trực quan.** A-LLM/A-SLM/A-TLM là 3 nhân viên xử lý cùng một gói. Thấy ngay model nào đi nhiều bước, đọc sai file hay bị luật hạ nhãn.
- **Tận dụng thứ đã có.** `viewer/server.py` đã phục vụ trace qua `/api/runs`, `/api/runs/<id>/packages`, `/api/trace`. Văn phòng 3D chỉ là một giao diện mới đọc cùng dữ liệu, không cần backend mới.
- **Hình ảnh thật cho báo cáo tuần** (mục "Ảnh kết quả" vẫn đang để trống).

### Rủi ro và cách xử lý

| Rủi ro | Mức | Cách xử lý |
| --- | --- | --- |
| Lấn thời gian việc chính (sandbox W5, thực nghiệm tuần 7–8) | Cao | Không làm trong tuần 5. Chia giai đoạn nhỏ, mỗi giai đoạn dùng được ngay. Có thể dừng sau giai đoạn 1 mà vẫn có giá trị. |
| GPU 6 GB dùng chung với Ollama, 3D làm chậm phép đo | Trung bình | Low-poly. Giới hạn `devicePixelRatio ≤ 1.5`. Dừng vẽ khi tab ẩn hoặc khi không có sự kiện mới. **Không mở văn phòng 3D lúc đang đo thời gian model.** |
| Hiển thị nội dung gói (dữ liệu không tin cậy) gây XSS | Trung bình | Chỉ dùng `textContent`/canvas, cấm `innerHTML` với dữ liệu trace. Thêm header CSP `script-src 'self'`. Có test tĩnh như I6. |
| Thêm thư viện lạ (AGENTS §7) | Trung bình | Chỉ thêm **Three.js**, ghim phiên bản, **chép vào repo** (không CDN, chạy offline, loopback). Nêu lý do trong Gate B0. Phương án không thư viện ở mục 3. |
| Trông như "game", bị đánh giá là màu mè | Thấp | Giữ phong cách bảng điều khiển hiện có (token màu trong `viewer/static/style.css`). Mọi chi tiết bấm vào phải dẫn tới bằng chứng `file:dòng` và luật `R1–R8`. |
| Máy không có WebGL hoặc người xem cần trợ năng | Thấp | Luôn có chế độ 2D: dòng thời gian của viewer hiện tại. Tôn trọng `prefers-reduced-motion`; điều khiển được bằng bàn phím. |

### Không làm

- Không sửa agent, công cụ, sandbox hay luật approve/deny.
- Không gọi dịch vụ đám mây, không tải tài nguyên từ Internet khi chạy.
- Không có âm thanh, nhân vật hay mô hình 3D tải về. Mọi hình khối tự dựng từ khối cơ bản.
- Không chạy agent từ giao diện. Chỉ xem trace đã có (replay) hoặc trace đang ghi (live, như viewer hiện tại).

## 2. Thiết kế

### 2.1. Ánh xạ sự kiện trace → phòng

Mặt bằng là một tầng văn phòng nhìn chéo từ trên xuống (camera isometric, có thể xoay/thu phóng trong giới hạn). Mỗi phòng tương ứng một bước của agent:

| Phòng | Sự kiện trace | Hiển thị |
| --- | --- | --- |
| **Lễ tân** | `run_start`, đọc manifest | Hồ sơ gói: tên@phiên bản, các hook `preinstall/install/postinstall` |
| **Phòng đọc mã** | `tool_call`/`tool_result` của `read_file`, `extract_indicators`, `deobfuscate` | Bàn có tập tài liệu; tên file và khoảng dòng đang đọc; số chỉ báo tìm thấy |
| **Phòng tra cứu** | context OSV/Registry (`tools/intel.py`) | Tủ hồ sơ: có/không có cảnh báo đã biết |
| **Phòng thí nghiệm (sandbox)** | chưa có (W5-6 chưa nối) | **Khóa, màu xám**, ghi "chưa nối vào agent". Chỉ mở sau W5-6. |
| **Bàn kiểm chứng** | `decision.evidence_checks` | Mỗi bằng chứng là một tờ giấy: xanh nếu `file:dòng` tồn tại, đỏ nếu bịa |
| **Phòng quyết định** | `decision` (`rule`, `final_label`, `final_action`, `reasons`) | Đèn approve/review/deny, luật áp dụng, lý do; nhãn model đề xuất so với nhãn sau luật |
| **Hành lang** | `error`, `limit` (hết 15 bước) | Biển cảnh báo; nhân viên quay về "review" (R2) |

Nhân viên (khối đơn giản có màu theo model) đi giữa các phòng theo thứ tự sự kiện. Bóng chữ trên đầu chỉ hiện `summary` ngắn. Chi tiết nằm ở **bảng bên** (DOM, `textContent`), có đường dẫn `file:dòng`.

### 2.2. Chế độ xem

1. **Replay một trace:** chọn run và gói như viewer hiện tại; phát, dừng, tua từng bước, chọn tốc độ 0.5×–4×.
2. **Live:** đọc trace đang ghi như viewer hiện tại; nhân viên di chuyển khi có sự kiện mới.
3. **So sánh 3 model:** cùng gói, 3 run (A-LLM/A-SLM/A-TLM); 3 nhân viên đi song song, mỗi người một làn. Dưới cùng là bảng tóm tắt: số bước, thời gian, nhãn, luật cuối.
4. **2D dự phòng:** nút chuyển sang dòng thời gian hiện có. Tự chuyển khi không có WebGL.

### 2.3. Kiến trúc

```
viewer/
├── server.py            # thêm route /office, /office/*.js, header CSP; KHÔNG thêm API mới
└── static/
    ├── office.html      # trang mới, dùng lại token CSS
    ├── office/
    │   ├── events.mjs   # hàm thuần: trace event → {room, action, label}; có test
    │   ├── timeline.mjs # hàng đợi phát lại, tốc độ, tua; có test
    │   ├── scene.mjs    # dựng phòng, nhân viên, camera (Three.js)
    │   └── panel.mjs    # bảng chi tiết, chỉ textContent
    └── vendor/three.module.min.js   # ghim phiên bản, kèm LICENSE (MIT)
```

- Phần logic (`events.mjs`, `timeline.mjs`) không phụ thuộc Three.js, test bằng `node --test`. Đây là mã của nhóm, không phải mã gói npm.
- Phần vẽ (`scene.mjs`) được kiểm bằng trình duyệt: ảnh chụp, console sạch, khổ 375 px.

## 3. Phương án công nghệ

| Phương án | Ưu | Nhược | Đề xuất |
| --- | --- | --- | --- |
| **A. Three.js chép vào repo** | 3D thật, xoay/thu phóng, bóng đổ nhẹ; tài liệu nhiều; không cần build | Thêm khoảng 700 KB thư viện; dùng GPU | **Chọn** |
| B. CSS 3D / SVG isometric, không thư viện | Không thêm phụ thuộc, nhẹ GPU | Khó làm camera, khó di chuyển mượt; "3D giả" | Dự phòng nếu PO không duyệt thư viện |
| C. Engine game (Babylon, Unity WebGL…) | Nhiều tính năng | Nặng, quá mức cần cho đồ án | Không chọn |

## 4. Kế hoạch triển khai

Đề xuất thời điểm: **sau mốc nghiệm thu tuần 5**, vào phần trống của tuần 6, phần trau chuốt ở tuần 9 (demo). Mỗi giai đoạn là một commit riêng, có DoD riêng.

| ID | Việc | Owner / Reviewer | Phụ thuộc | DoD (bằng chứng) |
| --- | --- | --- | --- | --- |
| **O-0** | **Spike (nửa ngày):** một phòng, một nhân viên đi theo trace mẫu `viewer/sample_traces/`; đo FPS và VRAM khi Ollama đang nạp model | Claude / PO | Gate B0 | Ảnh chụp; số FPS và VRAM. Nếu ≥ 30 FPS và không làm Ollama phải đẩy model sang CPU thì làm tiếp, không thì chuyển phương án B |
| **O-1** | **Ánh xạ sự kiện + dòng thời gian** (`events.mjs`, `timeline.mjs`) | Claude / TV2 | O-0 | `node --test` bao phủ mọi loại sự kiện trong `agent/trace.py`, kể cả sự kiện lạ → "Hành lang", trace hỏng/thiếu dòng |
| **O-2** | **Dựng văn phòng + replay một trace** (7 phòng, nhân viên, bảng chi tiết, điều khiển phát) | Claude / TV2 | O-1 | Replay đúng thứ tự trên 3 fixture và 1 bản swc; bảng hiện `file:dòng`, luật, lý do; console sạch; điều khiển được bằng bàn phím |
| **O-3** | **An toàn hiển thị** | Claude / Security (TV3) | O-2 | Test tĩnh: không có `innerHTML`/`eval` với dữ liệu; header CSP; trace chứa `<script>`/chuỗi lừa hiện nguyên văn, không chạy; server vẫn chỉ nghe loopback |
| **O-4** | **So sánh 3 model** (3 làn, bảng tóm tắt) | Claude / TV2 | O-2 | Dùng các run `w58-*`/`i3b-dev-*` có sẵn; số bước, thời gian, nhãn, luật khớp file `reports/<run>/<gói>.json` |
| **O-5** | **Live + 2D dự phòng + trợ năng** | Claude / PO | O-2 | Live theo trace đang ghi; tắt WebGL thì tự về 2D; `prefers-reduced-motion` tắt chuyển động; khổ 375 px không cuộn ngang |
| **O-6** | **Phòng thí nghiệm sandbox** | Claude / TV3 | **W5-6 đã xong** | Hiện `outcome`, `canary_touched`, sự kiện theo `actor` (`npm`/`package`) |
| **O-7** | **Đóng gói cho demo/báo cáo:** ảnh và video ngắn 3 ca (lành, độc, độc có câu lừa); cập nhật README | Claude / PO | O-4, O-5 | Ảnh thật trong `docs/tien-do/hinh-anh/`; ca độc chỉ chạy trên VM theo quy tắc an toàn |

Ước lượng: O-0 nửa ngày; O-1 + O-2 khoảng 2 ngày; O-3 nửa ngày; O-4 1 ngày; O-5 1 ngày; O-6 nửa ngày; O-7 nửa ngày. **Tổng khoảng 6 ngày công.** Bản dùng được cho demo cần O-0 → O-4, khoảng 4 ngày.

## 5. Điều PO cần quyết

1. Có làm không, và làm vào lúc nào (đề xuất: sau mốc tuần 5).
2. Có cho thêm Three.js (chép vào repo, MIT, ghim phiên bản) không. Nếu không thì chọn phương án B.
3. Phạm vi tối thiểu: chỉ O-0 → O-2 (replay), hay tới O-4 (so sánh 3 model).

### Quyết định của PO (04/11/2026)

1. **Thời điểm:** bắt đầu O-0 sau khi tuần 5 ổn định (đạt mốc nghiệm thu tuần 5).
2. **Three.js:** đồng ý, chép vào repo, ghim phiên bản, kèm LICENSE.
3. **Phạm vi:** đầy đủ O-0 → O-7. O-6 vẫn phụ thuộc W5-6.

Ghi nhận trong [`../docs/brownfield/TRANSITION_APPROVAL.md`](../../docs/brownfield/TRANSITION_APPROVAL.md).

## Chế độ "Xe hàng" — luồng sản phẩm (PO chốt 05/11/2026)

**Câu chuyện:**
1. Người dùng (hoặc trợ lý AI đang vibe-code) gửi `npm install` tới kho npm Registry.
2. Xe tải chở các gói tới cổng công ty.
3. Từng thùng đi qua các bước của agent.
4. Kết quả cả xe:
   - an toàn hết → giao tới máy người dùng;
   - có gói nghi vấn → xe bị giữ chờ người xem;
   - có gói độc → xe bị giữ, gói vào khu cách ly, phiếu báo cáo gửi người dùng và trợ lý AI.

**Quyết định:**

| Vấn đề | Quyết định | Lý do |
| --- | --- | --- |
| Gói bị từ chối | **Cách ly**, không xóa | Thực tế là `npm deny-scripts` (chặn script, không xóa gói); giữ bằng chứng để làm phiếu, khiếu nại, đối chiếu mã băm |
| Kết luận cả xe | **Nghiêm ngặt nhất thắng**: deny > review > approve | Gói con là phụ thuộc bắt buộc; giao thiếu thì lệnh cài hỏng |
| Kết quả thứ ba | **Kệ chờ duyệt** ở Bàn người xem | `review` là kết quả phổ biến nhất trên gói thật (10/10 swc) |
| Làn xanh | Gói không có script cài đặt thì sản phẩm cho đi thẳng | Đa số gói npm không có script; trong lô thực nghiệm agent vẫn phân tích để đo, và phụ đề nói rõ điều này |
| OSV | **Chặn trước, phân tích sau**; chế độ thực nghiệm không chặn | Không mất số liệu kiểm chứng (xem tuan-07.md) |
| Phiếu báo cáo | Gửi **cả người dùng và trợ lý AI** | Trợ lý AI mới là bên gõ lệnh cài; nó cần lý do để chọn gói khác |
| Các chế độ | Giữ cả 3: Xe hàng (mặc định), Đua 3 model, Một model | Xe hàng kể câu chuyện sản phẩm; Đua 3 model dùng cho đánh giá nghiên cứu |

**Trung thực khi thuyết trình:**
- Lô `w57-reg-a-llm` là **13 gói độc lập** (10 bản `@swc/core` + 3 fixture), không phải một cây phụ thuộc thật.
- Các phần sau là **minh họa dựng trên kết quả thật của từng gói**, chưa có trong code của agent: "xe tải", "gộp kết luận cả xe", "giao tới máy người dùng", "phiếu gửi người dùng".
- Bước quét OSV ở cổng trong chế độ này **không dùng dữ liệu OSV thật**, vì trace không có trường đó. Phụ đề ghi rõ.

**Kết quả trên dữ liệu thật:** ✅ 1 an toàn (benign fixture), 👁 11 chờ duyệt (10 swc + no-hook), ⛔ 1 cách ly (canary đọc khóa SSH giả) → **xe bị chặn, có phiếu báo cáo**.

## Danh mục kịch bản xe hàng (05/11/2026)

Mỗi thùng mang **nhãn nguồn** trên màn hình, để không ai nhầm mô phỏng với kết quả thật:
- **THẬT**: trace thật trong `reports/`.
- **MÔ PHỎNG**: luật có trong `agent/decide.py` nhưng chưa có trace.
- **THIẾT KẾ**: bước của thiết kế sản phẩm, chưa có trong code.

Bước mô phỏng ghi "[MÔ PHỎNG]" trong phụ đề và không bao giờ giả làm câu trả lời của model.

| # | Kịch bản | Nguồn | Luật / bước | Kết quả cả xe (đã kiểm trên trình duyệt) |
| --- | --- | --- | --- | --- |
| 0 | Lô thực nghiệm thật (chọn run) | THẬT | R6, R7, R7_review | `w57-reg-a-llm`: ✅ 1 · 👁 11 · ⛔ 1 → chặn |
| 1 | Cài gói an toàn → giao hàng | THẬT + THIẾT KẾ | R7, làn xanh, bộ nhớ đệm | ✅ 4 → **giao tới máy người dùng** |
| 2 | Gói độc ẩn trong cây phụ thuộc | THẬT + THIẾT KẾ | R6, nghiêm ngặt nhất thắng | ✅ 3 · ⛔ 1 → **chặn cả xe**, có phiếu |
| 3 | OSV đã biết độc: chặn trước, phân tích sau | THẬT + THIẾT KẾ | R6 + cờ OSV ở cổng | Chặn ngay ở cổng; agent độc lập **khớp** OSV |
| 4 | Mã bị làm rối → người xem từ chối | THẬT + THIẾT KẾ | R8 → người xem | ⛔ (do người xem) |
| 5 | Gói tải mã ngoài (swc) → người xem cho qua | THẬT + THIẾT KẾ | R7_review → người xem | ✅ → giao hàng |
| 6 | Mô hình lỗi / lặp kết luận sai | THẬT | R2 (`repeated_invalid`, `json_invalid`) | 👁 2 → giữ xe |
| 7 | AI bịa bằng chứng | MÔ PHỎNG | **R3** | 👁 → giữ xe |
| 8 | OSV báo độc, AI nói lành | MÔ PHỎNG | **R5** | Gói bị chặn, phiếu ghi **bất đồng** |
| 9 | Sandbox bắt quả tang (sau W5-6) | MÔ PHỎNG | **R1** | ⛔ → chặn |
| 10 | Tên gần giống gói nổi tiếng | THIẾT KẾ | Kiểm tên ở cổng | 👁 → giữ xe |
| 11 | Không tải được gói / hết 15 bước | MÔ PHỎNG | **R2** (lỗi tải, `limit`) | 👁 2 → giữ xe |
| 12 | Gói độc đã từng được cài | THẬT + THIẾT KẾ | R6 + cảnh báo | ⛔, phiếu có **cảnh báo đổi token** |

**Phủ bộ luật `decide.py`:** R1, R2, R3, R5, R6, R7, R7_review, R8 đều có kịch bản.
- R4 là nhánh phòng thủ mà schema đã chặn từ trước (R3 luôn chạy trước), nên không thể xảy ra trong thực tế.
- R7_risk chưa có kịch bản.

**Kiểm chứng:**
- `node --test tests/js/office_scenarios.test.mjs` (4 test): mọi bước mô phỏng đều có nhãn; luật mô phỏng đạt đúng luật minh họa; kết quả từng kịch bản đúng; run không có trong `reports/` thì bị bỏ qua, không bị bịa ra.
- Kiểm cả 13 kịch bản trên trình duyệt ngày 05/11.
