# Thống kê nháp bộ dữ liệu labels-v2

Tổng số dòng: **1411** · Mốc `time_split`: `2026-03-02`.

## Theo nhãn

- `benign`: 781
- `malicious`: 600
- `suspicious`: 30

## Theo tập chia (cluster-disjoint)

- `dev`: 281
- `test`: 428
- `train`: 702

## Theo nguồn

- `datadog`: 600
- `labels-v1-suspicious`: 30
- `npm-popular`: 406
- `npm-search`: 375
- Đối chiếu OSV (mã `MAL-` trong mẫu độc): **547/600**

## Theo năm (`source_date`)

- `2025`: 340
- `2026`: 260
- `unknown`: 811

## Theo `time_split`

- `after`: 175
- `before`: 425
- `unknown`: 811
- Tập test theo thời gian (`split == test` và `time_split == after`): **50**
