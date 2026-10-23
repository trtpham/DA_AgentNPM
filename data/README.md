# Bộ nhãn

`labels.csv` hiện chỉ có header. Không gán nhãn thật khi chưa có nguồn và người kiểm tra chéo. Các cột bắt buộc: package, version, label, source, source_url, reviewer; cột split do `prepare_labels` gán ổn định theo tên package để các phiên bản cùng gói không lọt vào cả hai tập (80% dev, 20% test theo hash, tỷ lệ thực tế phụ thuộc số mẫu). Dữ liệu mô phỏng chỉ nằm trong `tests/`.

`candidates.csv` lưu **metadata ứng viên** từ advisory công khai. `source_label` là nhãn của nguồn, `review_status=needs_independent_review` nghĩa là nhóm đồ án chưa kiểm tra chéo. GitHub Advisory và bản OSV tương ứng có cùng nguồn gốc nên không tính là hai lượt kiểm tra độc lập. Chỉ chuyển dòng sang `labels.csv` sau khi người kiểm tra xác minh đúng tên, phiên bản, install hook và hành vi; ghi tên người kiểm tra vào cột `reviewer`. Không tải hoặc đưa tarball vào Git.

Theo phân công trong `KE_HOACH.md`, TV1 phụ trách dữ liệu và **TV2 kiểm tra chéo**. Chưa có danh sách tên thành viên trong repo, nên chỉ ghi vai trò TV2 cho đến khi có người thực hiện và ký nhận kết quả.

Hiện chỉ có ứng viên malicious. Để tạo tập benign, chọn gói có install script với phiên bản cụ thể rồi kiểm tra hành vi và mục đích sử dụng; việc không có advisory không đủ để kết luận benign.

```powershell
rtk python -c "from pathlib import Path; from data.prepare_labels import prepare_labels; print(prepare_labels(Path('data/labels.csv'), Path('data/labels-prepared.csv')))"
```

Không chạy lệnh trên nếu đích đã chứa nhãn thủ công cần giữ; hàm ghi đè file đích.
