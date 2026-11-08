# Tài liệu đồ án

| Thư mục | Nội dung |
| --- | --- |
| [`nhat-ky-tuan/`](nhat-ky-tuan/) | Nhật ký kỹ thuật từng tuần: việc đã làm, lệnh kiểm chứng, PASS/FAIL |
| [`bao-cao-tuan/`](bao-cao-tuan/) | Báo cáo tiến độ cho giảng viên, hướng dẫn demo |
| [`hinh-anh/`](hinh-anh/) | Ảnh kết quả thật dùng trong báo cáo |
| `lms/` | Bản LMS docx/pdf nộp trường, chỉ trên máy (Git ignore) |

Mỗi tuần có **một** nhật ký (`nhat-ky-tuan/tuan-XX.md`) và **một** báo cáo tiến độ (`bao-cao-tuan/BaoCaoTienDo_TuanXX.md`). Khi cập nhật, sửa file hiện có, không tạo bản `v2`/`final`. Tài liệu cũ không còn dùng nằm ở `archive/` (chỉ trên máy).

## Tài liệu nội bộ (chỉ trên máy, không có trên GitHub)

`ke-hoach/` (kế hoạch), `giao-viec/` (phiếu giao việc, phân công kiểm tra chéo), `brownfield/` (Gate B0 do PO duyệt), `ban-giao/` (bàn giao giữa trợ lý code), `../archive/` (file cũ).

## Theo tuần

| Tuần | Trọng tâm | Nhật ký | Báo cáo tiến độ |
| --- | --- | --- | --- |
| 01 | Nền tảng và model | [tuan-01.md](nhat-ky-tuan/tuan-01.md) | [BaoCaoTienDo_Tuan01.md](bao-cao-tuan/BaoCaoTienDo_Tuan01.md) |
| 02 | Dữ liệu và hợp đồng công cụ | [tuan-02.md](nhat-ky-tuan/tuan-02.md) | [BaoCaoTienDo_Tuan02.md](bao-cao-tuan/BaoCaoTienDo_Tuan02.md) |
| 03 | Công cụ đọc, agent và sandbox cơ bản | [tuan-03.md](nhat-ky-tuan/tuan-03.md) | [BaoCaoTienDo_Tuan03.md](bao-cao-tuan/BaoCaoTienDo_Tuan03.md) |
| 04 | Tích hợp công cụ tĩnh và baseline | [tuan-04.md](nhat-ky-tuan/tuan-04.md) | [BaoCaoTienDo_Tuan04.md](bao-cao-tuan/BaoCaoTienDo_Tuan04.md) |
| 05 | Hoàn thiện sandbox và công cụ mở rộng | [tuan-05.md](nhat-ky-tuan/tuan-05.md) | [BaoCaoTienDo_Tuan05.md](bao-cao-tuan/BaoCaoTienDo_Tuan05.md) |
| 06 | Quyết định và chạy lô | [tuan-06.md](nhat-ky-tuan/tuan-06.md) | [BaoCaoTienDo_Tuan06.md](bao-cao-tuan/BaoCaoTienDo_Tuan06.md) |
| 07 | Hiệu chỉnh trên tập phát triển | [tuan-07.md](nhat-ky-tuan/tuan-07.md) | — |
| 08 | Đánh giá trên tập kiểm tra | [tuan-08.md](nhat-ky-tuan/tuan-08.md) | — |
| 09 | Viết báo cáo và phân tích lỗi | [tuan-09.md](nhat-ky-tuan/tuan-09.md) | — |
| 10 | Demo và bàn giao | [tuan-10.md](nhat-ky-tuan/tuan-10.md) | — |

## Ảnh và dữ liệu chạy

- Ảnh kết quả thật đặt trong [`hinh-anh/`](hinh-anh/) với tên `tuan-XX-mo-ta.png` hoặc `.jpg`, kèm chú thích lệnh, môi trường và ngày chụp. Không đưa token, secret hay mẫu độc vào ảnh. File `.svg` là hình tổng hợp, không phải ảnh chụp; `chua-co-anh.svg` chỉ đánh dấu chỗ còn trống.
- Trace và kết quả chạy lô (`reports/`) chỉ nằm trên máy chạy, không đưa lên Git. Số liệu dùng trong báo cáo được chép vào nhật ký tuần kèm `run_id`, để có thể mở lại bằng `py -3.14 -m viewer --reports reports`.
