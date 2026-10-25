# Bộ nhãn

`labels.csv` hiện chỉ có header. Không gán nhãn thật khi chưa có bằng chứng và người kiểm tra chéo. Hợp đồng mục 8 của AGENTS gốc: `id,name,version,label,behavior_main,technique,file,lines,source,split,cluster`. `source` chứa URL bằng chứng; người kiểm tra và quyết định cho từng dòng được ghi trong [hồ sơ tuần 2](REVIEW_WEEK2.md). `split` do `prepare_labels` gán ổn định theo tên gói (80% dev, 20% test theo hash; tỷ lệ thực tế phụ thuộc số mẫu). Dữ liệu mô phỏng chỉ nằm trong `tests/`.

`candidates.csv` lưu **metadata ứng viên**. `source_label=malicious` là nhãn advisory; `unlabeled` nghĩa là nguồn không khẳng định benign. `review_status=needs_independent_review` nghĩa là nhóm chưa kiểm tra chéo. GitHub Advisory và bản OSV tương ứng có cùng nguồn gốc nên không tính là hai lượt kiểm tra độc lập. Chỉ chuyển dòng sang `labels.csv` sau khi TV2 xác minh đúng tên, phiên bản, install hook, hành vi và ghi quyết định vào [hồ sơ tuần 2](REVIEW_WEEK2.md). Không tải hoặc đưa tarball độc vào Git.

Theo phân công trong `KE_HOACH.md`, TV1 phụ trách dữ liệu và **Phạm Minh Triết (TV2) kiểm tra chéo**. Việc nhận vai trò chưa xác nhận nhãn của ứng viên.

Với mỗi ứng viên trong `candidates.csv`, người kiểm tra chéo ghi: `package@version`, bằng chứng install hook, nhãn đề xuất, hành vi chính và lý do kèm nguồn. Xác minh từng mục trước khi chuyển vào `labels.csv`.

Hai ứng viên lành có install hook đã được thêm để TV2 xem xét. Việc không có advisory không đủ để kết luận benign.

```powershell
rtk proxy python -c "from pathlib import Path; from data.prepare_labels import prepare_labels; print(prepare_labels(Path('data/labels.csv'), Path('data/labels-prepared.csv')))"
```

Không chạy lệnh trên nếu đích đã chứa nhãn thủ công cần giữ; hàm ghi đè file đích.

## Kho 450 ứng viên metadata công khai

[`public_candidates_450.csv`](public_candidates_450.csv) chứa 450 tên gói npm duy nhất cùng phiên bản tại thời điểm tra cứu (2026-10-25 UTC). `collect_public_candidates.py` có các từ khóa dự phòng nhưng lần này đã đủ 450 ứng viên từ tìm kiếm `postinstall`; chỉ giữ manifest npm Registry có `preinstall`, `install` hoặc `postinstall`. Có 442 bản ghi với `postinstall`, 13 với `preinstall`, 8 với `install` (một gói có thể có nhiều hook); 236 tên gói có scope. `source_url` trỏ thẳng tới manifest phiên bản đã đối chiếu. Bộ thu thập chỉ gọi API metadata, không tải tarball hoặc chạy mã gói.

Toàn bộ dòng có `source_label=unlabeled` và `review_status=needs_independent_review`. Một lifecycle hook **không chứng minh gói độc hoặc lành**. Mẫu chọn theo từ khóa và xếp hạng tìm kiếm của npm, nên không đại diện thống kê cho toàn bộ hệ sinh thái. Không đưa file này vào thí nghiệm accuracy hay `labels.csv` trước khi TV2 xác minh nhãn, phiên bản, bằng chứng và phân chia tập. File `candidates.csv` 5 dòng cũ là ghi chú cục bộ bị Git ignore; không cộng tự động vào kho 450.
