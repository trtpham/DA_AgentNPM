# Kế hoạch cải thiện chất lượng — từ 03/11/2026

**Phạm vi:** làm tốt hơn những gì đã có; **không thêm chức năng mới**. Không thêm công cụ cho agent, không bật approve/deny thật, không nối sandbox vào agent (việc đó thuộc tuần 5 và cần gate riêng). Mỗi hạng mục đều có số đo trước/sau, test và tiêu chí hoàn thành (DoD). Hạng mục nào sửa `agent/` hoặc `decide` cần Gate B0 riêng trước khi code.

## 0. Mốc xuất phát (đo ngày 03/11, commit `4ff2132`)

| Chỉ số | A-LLM 9B | A-SLM 4B | A-TLM 0.8B | Nguồn |
| --- | --- | --- | --- | --- |
| Verdict hợp lệ, 3 fixture × 3 lần | 9/9 | 9/9 | 1/9 | `reports/b5v3-*` |
| Verdict hợp lệ, 10 swc dev | 10/10 | 10/10 | 2/10 | `reports/week4-dev-*` |
| Giây/gói (trung vị, swc + fixture) | 49.9 | 15.6 | 19.5 | trace `run_end` |
| Gói thật lành được approve | 0/10 (cả 10 về `review`) | 0/10 | 0/10 | R7_review |
| Lý do `review` nêu đúng nguyên nhân cụ thể | 0/10 (chỉ ghi "Install path not fully reviewed") | 0/10 | — | `decision.reasons` |

Các vấn đề đã thấy trong trace là cơ sở cho kế hoạch:
- A-TLM viết `description` quá 15 từ dù đã được nhắc số từ, và dẫn bằng chứng ở file không tồn tại (`manifest.json`).
- Với swc, kết quả `review` là đúng, nhưng lý do do trùng hợp: `binding.js` require file `.node` nằm ngoài tarball nên bộ quét đánh dấu "thiếu". Lệnh `execSync("npm install …")` ở `postinstall.js:125` (tải mã ngoài khi cài) chỉ được ghi nhận như một chỉ báo `child_process`.
- `agent/run.py` (489 dòng) duy trì hai hệ trace song song: JSONL và danh sách `legacy_trace` (21 chỗ) dành riêng cho `tools/visualize_agent.py`.
- Sandbox báo 4 lời gọi `connect()` ở mọi fixture, đều là npm tự tra DNS/nscd, lẫn với hành vi của gói.

## 1. Thứ tự ưu tiên

### I1. Lý do quyết định phải đúng và cụ thể — *ưu tiên cao nhất* (cần Gate B0)

> **Trạng thái 04/11: PASS.** A-LLM và A-SLM đều 10/10 lý do đúng; số đo ở [nhật ký tuần 5](tuan-05.md).

- **Vì sao:** người xem `review` cần biết chính xác điều gì chặn approve. Hiện lý do đúng ở gói swc chỉ là nhờ trùng hợp.
- **Việc làm:**
  - `R7_review` liệt kê nguyên nhân thật:
    - file trên đường install không đọc được (tên file);
    - lệnh hook gọi mã ngoài gói;
    - quét chạm giới hạn 30 chỉ báo / 100 file / độ sâu 2.
  - Bộ quét tách "file `.node` nhị phân không có trong tarball" khỏi "file mã nguồn bị thiếu". Cả hai vẫn chặn approve, chỉ khác lý do.
  - Lệnh tải mã ngoài nằm **trong mã nguồn** đường install (`execSync('npm install …')`, `spawn('npx' …)`) được xếp cùng nhóm với lệnh tương tự trong hook.
- **Số đo/DoD:** 10/10 gói swc vẫn ra `review` (không đổi kết luận), nhưng lý do nêu đúng `postinstall.js:125` và file `.node` thiếu. 3 fixture giữ nguyên kết quả. Có test cho từng nguyên nhân.

### I2. Độ ổn định của A-TLM và A-SLM mà không nới schema (cần Gate B0)

> **Trạng thái 04/11: PASS.** A-TLM 2/9 → 9/9 trên fixture; A-LLM/A-SLM giữ 9/9.

- **Vì sao:** A-TLM chỉ 1/9 và 2/10. Mọi lần thất bại đều an toàn, nhưng không có kết quả để so sánh.
- **Việc làm, đo từng thay đổi riêng lẻ:**
  1. Rút gọn đầu vào: gửi chỉ báo dạng `file:dòng loại` thay vì JSON đầy đủ có snippet; bỏ trường lặp. Đo số token prompt.
  2. Thêm một ví dụ verdict hợp lệ ngắn (một behavior, `description` 10 từ) vào system prompt.
  3. Lời nhắc sửa liệt kê đúng các file đã đọc khi model dẫn file chưa đọc. Trường hợp `manifest.json` cho thấy model không biết danh sách file.
  4. Thử đưa ràng buộc độ dài vào JSON schema gửi cho Ollama (`maxLength` của `description`). Codex từng thử 100 ký tự không hiệu quả, nên giữ lại chỉ khi số đo cải thiện.
- **Số đo/DoD:** chạy lại ma trận 27 lượt và 10 swc. Mục tiêu: A-TLM ≥ 5/9 trên fixture mà A-LLM/A-SLM không tụt dưới 9/9. Thay đổi nào không cải thiện thì revert và ghi lại kết quả âm, như cách Codex đã làm.

### I3. Tốc độ (không đổi kết luận)

> **Trạng thái 04/11: ĐẠT một phần.** Giây/gói trung vị trên 13 gói dev: A-TLM −59%, A-SLM −30%, **A-LLM +62% (không đạt)**. Token vào/ra đã được ghi trong trace. Còn mở: tìm nguyên nhân A-LLM chậm ([nhật ký tuần 5](tuan-05.md)).

- **Vì sao:** A-LLM mất khoảng 50–100 giây cho một gói swc. Chạy lô 76 gói × 3 model mất nhiều giờ.
- **Việc làm:**
  - Đo token vào/ra mỗi bước. Ollama trả `prompt_eval_count`/`eval_count`; ghi vào trace `run_end.tokens_per_s`, trường đã có nhưng đang luôn `null`.
  - Giảm `num_predict` của lượt gọi công cụ nếu đo thấy dư.
  - Áp dụng phần rút gọn đầu vào ở I2.
- **Số đo/DoD:** `tokens_per_s` có giá trị trong mọi trace mới. Trung vị giây/gói của A-LLM giảm ≥ 25% trên cùng 13 gói, với kết luận và luật cuối giống hệt lần đo mốc.

### I4. Sức khỏe mã nguồn và test hồi quy

> **Trạng thái 04/11: PASS.** Không hàm nào quá 80 dòng; 5 bản ghi phát lại; 115/115 test.

- **Việc làm:**
  - Tách `analyze()` thành các hàm nhỏ: chuẩn bị đầu vào, một bước model, xử lý công cụ, kiểm chứng verdict. Hành vi không đổi; 99 test hiện có là lưới an toàn.
  - Chuyển `tools/visualize_agent.py` sang đọc trace JSONL rồi bỏ `legacy_trace`. Chỉ làm sau khi viewer mới được PO nghiệm thu.
  - **Test phát lại trace thật:** lấy phản hồi model đã ghi trong `reports/b5v3-*` làm dữ liệu cho `chat` giả. Nhờ vậy lỗi của A-SLM/A-TLM trở thành test hồi quy tất định, không cần Ollama.
- **Số đo/DoD:** `agent/run.py` không còn hàm nào trên 80 dòng; 99 test cũ cùng các test phát lại đều PASS; kết quả 13 gói dev không đổi.

### I5. Độ chính xác đầu ra sandbox (không nối vào agent)

- **Việc làm:** trong kết quả `run_sandbox`, gắn mỗi `connect()`/`execve` với tiến trình gây ra nó (cây PID từ `strace -f`). Tách hoạt động của npm (tra DNS, nscd) khỏi hoạt động của script gói.
- **Số đo/DoD:** fixture `benign`/`no-hook` có 0 lời gọi mạng thuộc script gói; `canary` vẫn ghi nhận `ssh` + `environment`. Test trên log strace mẫu.

### I6. Viewer và dashboard (sau khi PO nghiệm thu G3–G4)

- **Việc làm:**
  - Nếu PO đồng ý, tách CSS dùng chung giữa viewer và `visualize_agent`.
  - Thêm điều khiển bàn phím và thông báo `aria-live` khi sự kiện mới đến ở chế độ live.
  - Hiển thị lý do quyết định cụ thể (kết quả của I1).
- **DoD:** kiểm tra lại XSS, khổ 375px và console sạch trên trình duyệt; có test tĩnh cho các điểm có thể đưa HTML vào trang.

### I7. Tái hiện thực nghiệm

- **Việc làm:**
  - Ma trận fixture hiện chạy bằng script tạm ngoài repo. Thay bằng `run_batch --dir` với `run_id` `-r1..-r3`, ghi lệnh vào README.
  - Đưa tham số chat (`num_ctx`, `temperature`) vào YAML cấu hình, đúng như AGENTS §6.7 mô tả. `run_meta.json` đọc từ đó.
  - Ghi RAM đỉnh của Ollama khi chạy lô. KE_HOACH tuần 7–8 yêu cầu chỉ số này.
- **DoD:** một lệnh README tái tạo được bảng mốc ở mục 0; `run_meta.json` khớp với YAML.

## 2. Những gì cố ý **không** đưa vào kế hoạch này

- Công cụ agent mới, `typosquat_check`, nối sandbox vào agent, hành động approve/deny thật: đều là chức năng mới.
- Đổi split dev/test để chỉ số đẹp hơn: chỉ bổ sung họ/chiến dịch mới **trước** khi chạy test, theo `data/REVIEW_WEEK2.md`.
- Recall/F1 trên mẫu độc: chờ nhãn v1 được kiểm tra chéo và môi trường VM.

## 3. Trình tự đề xuất

```
I1 (lý do quyết định) ─┐
                       ├─► I4 (tách hàm + test phát lại) ─► I2 (ổn định TLM/SLM) ─► I3 (tốc độ) ─► I7
I5 (sandbox) ──────────┘
I6 sau khi PO nghiệm thu viewer
```

I4 đi trước I2/I3 để mọi thử nghiệm prompt có lưới test tất định. Mỗi hạng mục là một commit riêng, kèm số đo trước/sau trong nhật ký tuần tương ứng.
