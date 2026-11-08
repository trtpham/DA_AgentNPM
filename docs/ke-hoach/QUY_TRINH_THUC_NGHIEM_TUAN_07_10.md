# Quy trình thực nghiệm tuần 7–10 (chuẩn bị 08/11/2026)

> Mọi công cụ dưới đây đã có, đã có test và đã chạy thử. Điều kiện duy nhất để bắt đầu: **nhãn v1 đã đóng băng** (19/11). Mẫu độc chỉ được tải và đọc trong container dùng một lần; không có mã gói nào được chạy (Gate B0 08/11).

## 0. Chuẩn bị một lần

```powershell
docker build -t agent-npm-runner:local experiments/runner        # Python + pydantic, user thường
docker build -t agent-npm-guarddog:2.6.0 experiments/guarddog    # đã có từ tuần 4
```

Ollama phải đang chạy trên máy (`ollama list` thấy `qwen3.5:9b`, `qwen3.5:4b`, `qwen3.5:0.8b`). Container gọi nó qua `host.docker.internal`; agent từ chối mọi địa chỉ khác.

## 1. Đóng băng nhãn v1 (19/11)

```powershell
py -3.14 -m data.scripts.data_report                              # kiểm tra chỉ tiêu; cần >= 300 mẫu verified
py -3.14 -m data.scripts.freeze_labels --output data/labels-v1.csv
git add data/labels-v1.csv; git commit -m "data: freeze labels v1"; git tag labels-v1
```

`freeze_labels` chỉ lấy dòng `verified`, thay mô tả nháp bằng `observed_behavior` của người kiểm tra, tách cụm có hai nhãn, chia dev/test theo cụm (test 60%), và không bao giờ ghi đè file đã có.

## 2. Tuần 7 — chỉ tập dev

```powershell
# Agent: 3 cấu hình chính thức và 3 cấu hình mốc
foreach ($v in "A-LLM-X","A-SLM-X","A-TLM-X","A-LLM","A-SLM","A-TLM") {
  py -3.14 -m experiments.run_isolated "dev-v1-$($v.ToLower())" $v --labels data/labels-v1.csv --split dev
}
# GuardDog trên cùng tập dev
py -3.14 -m experiments.run_isolated dev-v1-guarddog --guarddog --labels data/labels-v1.csv --split dev
```

- Bị ngắt thì chạy lại đúng lệnh: gói đã có kết quả được bỏ qua.
- **Chọn ngưỡng** (chỉ dev, luật chọn ghi sẵn trong script: 0 gói độc được approve → F1 cao nhất → hòa thì lấy ngưỡng cao hơn):

```powershell
py -3.14 -m experiments.threshold_sweep reports/dev-v1-a-llm-x --labels data/labels-v1.csv --split dev
py -3.14 -m experiments.calibration dev-v1-a-llm-x dev-v1-a-slm-x dev-v1-a-tlm-x --labels data/labels-v1.csv
```

- Ghi ngưỡng đã chọn vào `deny_threshold`/`approve_threshold` của từng `experiments/configs/A-*-X.yaml`, commit, **Gate mới** (đổi ngưỡng cần PO duyệt). Từ đây không đổi cấu hình nữa.

## 3. Tuần 8 — tập test, chạy một lần

```powershell
foreach ($v in "A-LLM-X","A-SLM-X","A-TLM-X","A-LLM","A-SLM","A-TLM") {
  py -3.14 -m experiments.run_isolated "test-v1-$($v.ToLower())" $v --labels data/labels-v1.csv --split test
}
py -3.14 -m experiments.run_isolated test-v1-guarddog --guarddog --labels data/labels-v1.csv --split test
py -3.14 -m experiments.metrics reports/test-v1-a-llm-x --labels data/labels-v1.csv
py -3.14 -m experiments.metrics reports/test-v1-guarddog/guarddog --labels data/labels-v1.csv --source guarddog
py -3.14 -m experiments.rote_probe test-v1-corpus A-LLM-X A-SLM-X A-TLM-X   # đo học vẹt trên 22 gói mô phỏng
```

Báo cáo theo tuần 7 (KE_HOACH): **chỉ agent** (không OSV) là số chính; Precision, Recall, F1, FPR, tỷ lệ review, tỷ lệ JSON hợp lệ, thời gian/gói; so với GuardDog; bảng lỗi (báo nhầm/bỏ sót) kèm `run_id` để mở trace bằng `py -3.14 -m viewer --reports reports`.

## 4. Tuần 9–10

| Việc | Nguồn số liệu |
| --- | --- |
| Chương kết quả: bảng chỉ số 3 model × (mốc, `-X`) và GuardDog | `metrics` của bước 3 |
| Phân tích lỗi: 10 ca báo nhầm + 10 ca bỏ sót, mỗi ca 1 đoạn | trace trong viewer |
| Học vẹt: corpus 22 gói, cặp phân tách | `rote_probe` |
| Calibration: ECE, Brier | `calibration` |
| Demo 3 ca (lành, độc, độc có câu lừa) | [hướng dẫn demo tuần 5](../bao-cao-tuan/HUONG_DAN_DEMO_TUAN05.md), văn phòng 3D |

## 5. Kiểm tra trước mỗi lần chạy lớn

```powershell
py -3.14 -m pytest -q
$env:RUN_SANDBOX_TESTS="1"; py -3.14 -m pytest -q tests/test_sandbox_limits.py
```
