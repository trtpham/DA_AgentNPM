# Bộ nhãn

`labels.csv` hiện chỉ có header. Không gán nhãn thật khi chưa có bằng chứng và người kiểm tra chéo. Hợp đồng mục 8 của AGENTS gốc: `id,name,version,label,behavior_main,technique,file,lines,source,split,cluster`. `source` chứa URL bằng chứng; người kiểm tra và quyết định cho từng dòng được ghi trong [hồ sơ tuần 2](REVIEW_WEEK2.md). `split` do `prepare_labels` gán ổn định theo tên gói (80% dev, 20% test theo hash; tỷ lệ thực tế phụ thuộc số mẫu). Dữ liệu mô phỏng chỉ nằm trong `tests/`.

`candidates.csv` lưu **metadata ứng viên**. `source_label=malicious` là nhãn advisory; `unlabeled` nghĩa là nguồn không khẳng định benign. `review_status=needs_independent_review` nghĩa là nhóm chưa kiểm tra chéo. GitHub Advisory và bản OSV tương ứng có cùng nguồn gốc nên không tính là hai lượt kiểm tra độc lập. Chỉ chuyển dòng sang `labels.csv` sau khi TV2 xác minh đúng tên, phiên bản, install hook, hành vi và ghi quyết định vào [hồ sơ tuần 2](REVIEW_WEEK2.md). Không tải hoặc đưa tarball độc vào Git.

Theo phân công trong `KE_HOACH.md`, TV1 phụ trách dữ liệu và **Phạm Minh Triết (TV2) kiểm tra chéo**. Việc nhận vai trò chưa xác nhận nhãn của ứng viên.

Với mỗi ứng viên trong `candidates.csv`, người kiểm tra chéo ghi: `package@version`, bằng chứng install hook, nhãn đề xuất, hành vi chính và lý do kèm nguồn. Xác minh từng mục trước khi chuyển vào `labels.csv`.

Hai ứng viên lành có install hook đã được thêm để TV2 xem xét. Việc không có advisory không đủ để kết luận benign.

```powershell
rtk python -c "from pathlib import Path; from data.prepare_labels import prepare_labels; print(prepare_labels(Path('data/labels.csv'), Path('data/labels-prepared.csv')))"
```

Không chạy lệnh trên nếu đích đã chứa nhãn thủ công cần giữ; hàm ghi đè file đích.
