# Bộ nhãn

`labels.csv` hiện chỉ có header. Không gán nhãn thật khi chưa có nguồn và người kiểm tra chéo. Các cột bắt buộc: package, version, label, source, source_url, reviewer; cột split do `prepare_labels` gán ổn định theo tên package để các phiên bản cùng gói không lọt vào cả hai tập (80% dev, 20% test theo hash, tỷ lệ thực tế phụ thuộc số mẫu). Dữ liệu mô phỏng chỉ nằm trong `tests/`.

```powershell
rtk python -c "from pathlib import Path; from data.prepare_labels import prepare_labels; print(prepare_labels(Path('data/labels.csv'), Path('data/labels-prepared.csv')))"
```

Không chạy lệnh trên nếu đích đã chứa nhãn thủ công cần giữ; hàm ghi đè file đích.
