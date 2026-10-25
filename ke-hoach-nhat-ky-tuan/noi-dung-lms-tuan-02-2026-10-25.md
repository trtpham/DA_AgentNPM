# Báo cáo tuần 02 để nộp LMS

**Đề tài:** AI Agent kiểm tra gói npm

**Thành viên:** Lê Đặng Thiên Phước · Phạm Minh Triết · Nguyễn Đình Thiên

**Ngày cập nhật:** 25/10/2026

## 1. Nội dung buổi báo cáo tuần

Trong tuần 2, nhóm tập trung chuẩn bị dữ liệu và xây dựng những phần đầu tiên để hệ thống có thể kiểm tra gói npm. Nhóm đã thử cách đọc thông tin của một gói mẫu trong môi trường an toàn và tổng hợp được danh sách **450 gói** kèm nguồn để tiếp tục xem xét.

Điểm nhóm còn kẹt là **chưa xác nhận gói nào lành hoặc độc** trong danh sách mới. Vì vậy, nhóm chưa thể dùng 450 gói này để đánh giá độ chính xác của hệ thống. Theo ghi nhận của nhóm, góp ý chính của thầy trong buổi báo cáo là cần tiếp tục tìm và hoàn thiện dữ liệu. Nhóm đã bổ sung số lượng ứng viên, còn bước quan trọng tiếp theo là kiểm tra và gán nhãn có bằng chứng.

## 2. Demo bao nhiêu phần trăm (kèm ảnh)

Nhóm có thể trình bày khoảng **75% nội dung dự kiến của tuần 2**: cho xem danh sách gói đã tìm được, cách hệ thống đọc một gói mẫu mà không chạy mã gói trên máy, và kết quả thử trong môi trường cách ly. Phần chưa thể demo như một kết quả hoàn chỉnh là đánh giá đúng/sai trên bộ dữ liệu đã được kiểm tra nhãn. Con số 75% chỉ tính trong phạm vi tuần 2, không phải tiến độ toàn đồ án.

![Hình 1 — danh sách 450 ứng viên, chưa có nhãn được kiểm tra chéo]![Uploading image.png…]()


*Hình 1 tổng hợp số liệu nhóm đã tìm được. Đây không phải ảnh chụp lúc báo cáo.*

![Hình 2 — kết quả thử các phần đã xây dựng](hinh-anh/tuan-02-ket-qua.svg)

*Hình 2 tổng hợp kết quả thử trước đó. Khi nộp LMS, nhóm tải hai file ảnh trong thư mục `hinh-anh/` lên cùng bài và chèn vào các vị trí này.*

## 3. Ảnh chụp lúc báo cáo

Nhóm quên chụp ảnh trong buổi báo cáo nên **không có ảnh chụp thực tế** để đính kèm. Nhóm có file ghi âm buổi trao đổi và có thể cung cấp khi cần. Hai hình ở mục 2 chỉ minh họa kết quả làm việc, không được xem là ảnh chụp buổi gặp.

## 4. Đề xuất tuần 3 và 4, cách giải quyết và định hướng

**Tuần 3:** Nhóm sẽ chọn trước khoảng 20–30 gói trong danh sách để kiểm tra kỹ, thay vì chạy thử cả 450 gói. Phạm Minh Triết đối chiếu nguồn và nhãn; Lê Đặng Thiên Phước loại gói trùng, bổ sung gói đối chứng; Nguyễn Đình Thiên tiếp tục kiểm tra môi trường chạy cách ly. Gói nào thiếu bằng chứng sẽ giữ ở trạng thái chờ, không vội kết luận.

**Tuần 4:** Khi đã có một nhóm dữ liệu đáng tin, nhóm mới dùng chúng để đánh giá cách hệ thống phân tích và so sánh ba mô hình. Nhóm sẽ bổ sung công cụ hỗ trợ và ghi lại các trường hợp hệ thống nhận định sai để điều chỉnh. Việc thử nghiệm vẫn ưu tiên môi trường an toàn và chưa chạy hàng loạt trên 450 gói.

**Định hướng chung:** Ưu tiên **dữ liệu đúng và có thể kiểm tra lại** hơn là chỉ tăng số lượng. Mục tiêu tiếp theo là biến danh sách ứng viên thành bộ dữ liệu có nhãn rõ ràng, sau đó mới đo kết quả và mở rộng quy mô. Mã nguồn, dữ liệu và báo cáo tuần 02 đã được cập nhật trên GitHub.
