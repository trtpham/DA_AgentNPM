# Báo cáo tiến độ tuần 08 — Đóng băng labels-v2, sửa sandbox và fine-tune mô hình 4B (Kế hoạch công việc)

**Thành viên:** Lê Đặng Thiên Phước · Phạm Minh Triết · Nguyễn Đình Thiên

**Giai đoạn:** Đóng băng bộ dữ liệu mới, sửa lỗi sandbox, đánh giá `-XS` và huấn luyện `A-SLM-FT` · **Thời gian dự kiến:** 30/11–06/12/2026 · **Trạng thái:** Bản soạn sẵn kế hoạch tuần 8 (`Chưa chạy`, các ô kết quả sẽ điền bằng số đo thật sau khi thực hiện)

> Ghi chú quy trình: mọi thay đổi mã nguồn (`sandbox/`, cấu hình ngưỡng, cài môi trường QLoRA, đóng băng nhãn) chỉ thực hiện sau khi PO mở Gate tương ứng.

## 1. Nội dung công việc dự kiến trong tuần 8

### 1.1. Danh sách đầu việc: đã làm gì → làm thế nào → kết quả kỳ vọng

| STT | Đầu việc | Cách thực hiện dự kiến | Kết quả kỳ vọng (DoD) | Trạng thái |
| --- | --- | --- | --- | --- |
| 1 | **Đóng băng bộ dữ liệu `labels-v2`** | Rà lại thống kê [README-v2-draft.md](../../data/README-v2-draft.md), PO duyệt Gate đóng băng → tạo `data/labels-v2.csv` (~1.411–1.500 gói) và `data/labels-v2-review.csv` kèm phiếu mù thêm 60 gói lành v2 | Bộ nhãn `v2` khóa hàm băm, chia `train/dev/test` không rò rỉ cụm, lưu `time_split` | `Chưa thực hiện` |
| 2 | **Hoàn tất kiểm chéo mù `labels-v1`** | 3 thành viên điền độc lập `data/review_rounds/blind-v1/phieu-*.csv` từ trang bằng chứng mù, sau đó chạy `py -3.14 -m data.scripts.blind_review score` | Bảng tỉ lệ đồng ý và hệ số kappa ghi nhận vào báo cáo | `Chưa thực hiện` |
| 3 | **Sửa sandbox nhóm A (22 gói) và nhóm F (11 gói)** | Mở Gate `sandbox/`: tách bộ nhớ đệm npm khỏi `/tmp` 64 MB sang volume/tmpfs riêng ~512 MB (`noexec`), giữ nguyên mọi cờ cách ly; ghi thêm `npm error code` và vài dòng stderr lọc cho nhóm F; chạy lại test Docker rồi thao tác `--retry-failed` trong VM Ubuntu cho `sbx-dev-v1b`, `sbx-test-v1b` | Test Docker qua hết; độ phủ sandbox trên v1 tăng so với 86,6%, không còn ca thiếu không rõ nguyên nhân | `Chưa thực hiện` |
| 4 | **Chạy và khóa cấu hình có sandbox (`-XS`) trên `labels-v1`** | Chạy `experiments.run_isolated dev-v1-a-llm-xs A-LLM-XS --labels data/labels-v1.csv --split dev --sandbox-results reports/sbx-dev-v1b/sandbox` → quét ngưỡng (`threshold_sweep.py`) → PO duyệt Gate khóa ngưỡng → chạy `test` v1 một lần | Bảng so sánh `A-LLM-X` và `A-LLM-XS` (P/R/F1/FPR, số gói bị R1/R7_sandbox bắt, số gói thiếu sandbox) | `Chưa thực hiện` |
| 5 | **Sandbox pha A cho `labels-v2` trong VM** | Chuẩn bị và chạy `sandbox_batch.py` trong máy ảo VMware Ubuntu cho `labels-v2` (`train/dev/test`), ghi kết quả phủ hành vi và canary | Độ phủ sandbox của `labels-v2` để dùng cho tuần 9 | `Chưa thực hiện` |
| 6 | **Huấn luyện QLoRA `Qwen3.5-4B` (`A-SLM-FT`)** | Mở Gate cài thư viện vào môi trường riêng (WSL2 Ubuntu hoặc Python 3.12 trên ổ `D:`), benchmark 10 bước đo VRAM/giây; chạy `A-LLM-X` trên tập `train` v2 (~702 gói); trích mẫu sạch bằng `experiments/extract_sft.py`; fine-tune QLoRA 4B (hoặc dự phòng `0.8B` nếu vượt 6 GB); xuất GGUF và nạp vào Ollama; tạo `experiments/configs/A-SLM-FT.yaml` (cùng công cụ, prompt, luật với `A-SLM-X`) | Tag `A-SLM-FT` hoạt động ổn định trong Ollama (`model_probe.py` PASS), lưu checkpoint và phiên bản thư viện | `Chưa thực hiện` |
| 7 | **Frontend: trang so sánh cấu hình & ca sai** | Hoàn thiện tab `So sánh model` và trang/bộ lọc `Ca sai` đọc trực tiếp từ lượt chạy thật trong `reports/`, viết test Python/JS và cập nhật kịch bản demo trên mẫu thật | Mở và so sánh trực tiếp `test-v1-*` trên giao diện 2D, `pytest` và `node --test` PASS | `Chưa thực hiện` |

## 2. Khung bảng kết quả chờ điền (khi chạy xong)

### 2.1. Đối chiếu có / không sandbox trên `labels-v1` (`A-LLM-X` vs `A-LLM-XS`)

| Cấu hình | Precision | Recall | F1 | FPR | Gói độc được cho phép | Gói bị sandbox chặn (R1) | Gói đổi quyết định | Thiếu kết quả sandbox |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `A-LLM-X` (test v1, đã có) | 0,726 | 0,969 | 0,830 | 0,411 | 0 | — | — | — |
| `A-LLM-XS` (dev v1) | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy |
| `A-LLM-XS` (test v1, sau Gate) | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy |

### 2.2. Kiểm chéo mù `labels-v1` (60 gói) và độ phủ sandbox sau khi sửa nhóm A/F

- Tỉ lệ đồng ý (raw agreement): `Chưa có` · Cohen/Fleiss kappa: `Chưa có`.
- Độ phủ sandbox v1 sau `--retry-failed`: `Chưa chạy` (mốc tuần 6: `86,6%`).

### 2.3. Kết quả chuẩn bị dữ liệu và huấn luyện QLoRA 4B

- Số lượt `A-LLM-X` chạy trên `train` v2: `Chưa chạy` / tổng số gói `train`.
- Số mẫu hội thoại sạch trích được bằng `experiments/extract_sft.py`: `Chưa chạy`.
- Đo 10 bước thử nghiệm (VRAM đỉnh / giây mỗi bước / `max_seq_len`): `Chưa đo`.

## 3. Rủi ro cần theo dõi trong tuần 8

- **Ngân sách GPU (mỗi lúc 1 việc, chạy đêm):** chạy `A-LLM-X` trên ~702 gói `train` v2 ước mất ~5–6 giờ; huấn luyện QLoRA ước ~1,5–4 giờ; cần ưu tiên chạy tuần tự, không chạy song song hai tiến trình Ollama/PyTorch trên RTX 3050 6 GB.
- **Tràn 6 GB VRAM khi fine-tune 4B:** theo khảo sát ở `KHA_THI_QLORA_4B.md`, nếu vượt 6 GB dù đã giảm `max_seq_len = 2048`, chuyển sang phương án dự phòng fine-tune `qwen3.5:0.8b`.
- **Thao tác trong VM Ubuntu:** chỉ thực hiện trên snapshot sạch `sach-2211`, giữ nguyên cách ly mạng và đối chiếu độ phủ trước khi đưa kết quả sandbox vào `-XS`.

## 4. Đề xuất bước chuyển sang tuần 9

- Chọn checkpoint và quét ngưỡng cho `A-SLM-FT` (và `A-LLM-X`, `A-SLM-X`) trên tập **`dev` của `labels-v2`**, khóa Gate trước khi mở tập `test` v2 ở tuần 9.
