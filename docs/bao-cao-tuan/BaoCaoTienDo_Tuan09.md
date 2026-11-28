# Báo cáo tiến độ tuần 09 — Thực nghiệm cuối trên labels-v2, thử câu lừa và hoàn thiện đồ án (Kế hoạch công việc)

**Thành viên:** Lê Đặng Thiên Phước · Phạm Minh Triết · Nguyễn Đình Thiên

**Giai đoạn:** Đánh giá tổng thể trên `labels-v2`, kiểm tra bền vững và hoàn thiện báo cáo cuối · **Thời gian dự kiến:** 07–13/12/2026 · **Trạng thái:** Bản soạn sẵn kế hoạch tuần 9 (`Chưa chạy`, mọi kết quả sẽ điền sau khi khóa ngưỡng và chạy đúng một lần trên tập `test` v2)

> Nguyên tắc bắt buộc: tập `test` của `labels-v2` chỉ được chạy **đúng một lần** sau khi đã khóa checkpoint và ngưỡng trên tập `dev` v2 qua Gate; tuyệt đối không chỉnh prompt, luật hay ngưỡng sau khi đã thấy số liệu `test`.

## 1. Nội dung công việc dự kiến trong tuần 9

### 1.1. Danh sách đầu việc: đã làm gì → làm thế nào → kết quả kỳ vọng

| STT | Đầu việc | Cách thực hiện dự kiến | Kết quả kỳ vọng (DoD) | Trạng thái |
| --- | --- | --- | --- | --- |
| 1 | **Chọn checkpoint và khóa ngưỡng trên `dev` v2** | Chạy `A-LLM-X`, `A-SLM-X`, `A-SLM-FT` trên `dev` của `labels-v2`; dùng `experiments/threshold_sweep.py` theo luật tuần 6 (0 gói độc cho phép > F1 > ngưỡng cao hơn); mở Gate khóa cấu hình | File cấu hình và ngưỡng được khóa bằng Gate trước khi chạy `test` v2 | `Chưa thực hiện` |
| 2 | **Chạy thực nghiệm cuối trên `test` v2** | Chạy đúng 1 lần trên tập `test` của `labels-v2` (~428 gói): `A-LLM-X`, `A-SLM-X`, `A-SLM-FT` và `GuardDog 2.6.0` (trong container dùng một lần); chấm điểm bằng `experiments/metrics.py` | Bảng tổng hợp P / R / F1 / FPR / tỉ lệ chờ người xem / thời gian / gói độc bị cho phép | `Chưa thực hiện` |
| 3 | **Báo cáo tách biệt tập `test` theo thời gian (`time_split = after`)** | Lọc riêng các mẫu độc năm 2026 có ngày sau mốc `2026-03-02` (`time_split == after`, loại `unknown`) để đánh giá khả năng phát hiện mẫu mới sau ngày phát hành mô hình `qwen3.5` | Bảng chỉ số riêng cho `time_split = after` so với toàn bộ tập `test` v2 | `Chưa thực hiện` |
| 4 | **Thực nghiệm đối chiếu có/không OSV và có/không sandbox trên `test` v2** | Tra OSV cho `labels-v2` (`reports/contexts-v2`), chạy `experiments/osv_ablation.py` trên `test` v2; chạy cấu hình `-XS` với kết quả sandbox pha A của v2 | Bảng so sánh rõ đóng góp riêng của agent (không OSV), khi cộng OSV và khi cộng sandbox | `Chưa thực hiện` |
| 5 | **Thử nghiệm chống câu lừa (`prompt injection`) trên gói lành thật của `test` v2** | Chèn các mẫu câu lừa (mục R11 kế hoạch) vào bản sao cách ly của gói **lành** thật thuộc `test` v2; chạy kiểm tra theo cấu hình `A-LLM-X`, `A-SLM-X`, `A-SLM-FT` | Bảng tỉ lệ bị lừa theo từng cấu hình và tỉ lệ luật `R7_flow` giữ lại | `Chưa thực hiện` |
| 6 | **Hoàn thiện báo cáo cuối, slide và video demo** | Cập nhật `D:\DACN\BaoCaoCuoi\_nguon\noi_dung.py` (chương 4 số liệu `v1` + `v2`, ảnh demo giao diện mới, nguồn vụ AntV, URL docs npm v12, số đo kích thước gói, sửa trang trống trước Mục lục), dựng Word/PDF bằng `build_report.py`; làm slide thuyết trình và quay video demo trên giao diện 2D mới | Bộ hồ sơ đồ án hoàn chỉnh, số liệu khớp 100% với `reports/` và `data/` | `Chưa thực hiện` |

## 2. Khung bảng kết quả chờ điền (khi chạy xong)

### 2.1. Kết quả trên toàn bộ tập `test` của `labels-v2`

| Cấu hình | Model | Precision | Recall | F1 | FPR | Chờ người xem | Lỗi | Giây/gói | Gói độc được cho phép |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `A-LLM-X` | `qwen3.5:9b` | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy |
| `A-SLM-X` | `qwen3.5:4b` | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy |
| `A-SLM-FT` | tag FT | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy |
| `GuardDog 2.6.0` | — | Chưa chạy | Chưa chạy | Chưa chạy | Chưa chạy | — | Chưa chạy | — | — |

### 2.2. Kết quả riêng trên tập `test` theo thời gian (`time_split = after`, sau `2026-03-02`)

| Cấu hình | Số mẫu `after` | Recall | Tỉ lệ chặn (`deny + review`) | Gói độc được cho phép |
| --- | ---: | ---: | ---: | ---: |
| `A-LLM-X` | 50 | Chưa chạy | Chưa chạy | Chưa chạy |
| `A-SLM-X` | 50 | Chưa chạy | Chưa chạy | Chưa chạy |
| `A-SLM-FT` | 50 | Chưa chạy | Chưa chạy | Chưa chạy |
| `GuardDog 2.6.0` | 50 | Chưa chạy | Chưa chạy | — |

### 2.3. Tỉ lệ bị lừa (`prompt injection`) và đối chiếu OSV / Sandbox trên `test` v2

- Có/không OSV (`osv_ablation.py`): `Chưa chạy`.
- Có/không sandbox (`-XS` trên v2): `Chưa chạy`.
- Tỉ lệ bị lừa trên gói lành thật `test` v2: `Chưa chạy`.

## 3. Rủi ro và phương án dự phòng tuần 9

- **Nếu `A-SLM-FT` không cải thiện rõ rệt so với `A-SLM-X` trên `dev`/`test` v2:** báo cáo trung thực số liệu đo được, phân tích nguyên nhân (giới hạn VRAM 6 GB, độ dài ngữ cảnh, tỉ lệ lỗi JSON/bằng chứng) thay vì chỉnh lại dữ liệu hoặc chạy lại trên tập `test`.
- **Quản lý thời gian GPU (~12–15 giờ tổng cho `test` v2):** chia lô chạy qua đêm (có `resume`), kiểm soát mỗi thời điểm chỉ chạy một cấu hình.
- **Kiểm tra trước khi nộp:** chạy lại toàn bộ `py -3.14 -m pytest -q`, test Docker và `node --test tests/js/*.test.mjs`; đối chiếu chéo mọi con số giữa `BaoCaoCuoi` và tệp JSON thật trong `reports/`.
