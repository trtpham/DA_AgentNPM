# experiments/ — chạy thử nghiệm và đo

## Chạy agent và baseline

| File | Khi nào dùng |
| --- | --- |
| `run_batch.py` | Chạy agent trên máy, cho gói lành và gói thử. Lưu `reports/<run_id>/` và chạy tiếp được khi bị ngắt |
| `run_isolated.py` | Chạy agent hoặc GuardDog (`--guarddog`) trong container dùng một lần. **Bắt buộc cho mẫu độc** (tuần 7–8) |
| `baseline_guarddog.py` | Đọc kết quả GuardDog thành JSON chung |
| `configs/` | Cấu hình model. `A-*` là mốc gốc, `A-*-X` là cấu hình chính thức (thêm công cụ đọc) |
| `runner/`, `guarddog/` | Dockerfile cho hai container trên |

## Đo và phân tích

| File | Việc |
| --- | --- |
| `metrics.py` | Precision, Recall, F1, FPR, tỉ lệ chuyển người xem từ `reports/` và bảng nhãn |
| `threshold_sweep.py` | Thử lại ngưỡng quyết định trên kết quả đã có, không chạy lại model (chỉ tập dev) |
| `calibration.py` | Độ tin cậy của model có khớp tỉ lệ đúng không |
| `dataset.py` | Đọc `labels.csv` |

## Kiểm tra riêng

| File | Việc |
| --- | --- |
| `model_probe.py` | Thử khả năng gọi công cụ của model (TV2-1) |
| `rote_probe.py` | Agent xét mã hay xét tên gói: chạy bộ gói mô phỏng có cặp đổi tên |
| `demo_sandbox.py` | Demo sandbox trên gói mẫu, in một bảng dễ đọc |
| `repro_sandbox.py` | Chạy sandbox nhiều lần để kiểm tính lặp lại (W5-4) |

## Lệnh thường dùng

```powershell
py -3.14 -m tools.intel @swc/core 1.7.36 --output reports/ctx/@swc__core@1.7.36.json        # tra OSV/Registry trước
py -3.14 -m experiments.run_batch <run_id> A-SLM --labels data/labels.csv --split dev --contexts reports/ctx
docker build -t agent-npm-guarddog:2.6.0 experiments/guarddog                                # một lần
py -3.14 -m experiments.baseline_guarddog <run_id> --labels data/labels.csv --split dev
py -3.14 -m experiments.metrics reports/<run_id>                                             # thêm --source guarddog cho GuardDog
```

- Chạy lại cùng `run_id` thì bỏ qua gói đã xong. Một gói lỗi không dừng cả lô.
- Lượt chạy lỗi tính là bỏ sót, vẫn nằm trong mẫu số.
- GuardDog bản pip trên Windows báo "0 lỗi" giả, nên chỉ chạy trong container.

Thứ tự chạy tuần 7–10: [QUY_TRINH_THUC_NGHIEM_TUAN_07_10.md](../docs/ke-hoach/QUY_TRINH_THUC_NGHIEM_TUAN_07_10.md).
