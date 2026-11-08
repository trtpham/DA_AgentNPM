# Kế hoạch, nhật ký và báo cáo tiến độ

Mọi tài liệu về kế hoạch, tiến độ và báo cáo tuần của đồ án nằm trong thư mục này. Mỗi tuần có **một** nhật ký (`tuan-XX.md`, ghi bằng chứng kỹ thuật chi tiết) và **một** báo cáo tiến độ (`BaoCaoTienDo_TuanXX.md`, bản trình bày cho giảng viên). Khi cập nhật, sửa file hiện có, không tạo bản `v2`/`final`.

## Kế hoạch

- [Kế hoạch tổng thể 10 tuần](KE_HOACH.md)
- (Đã xong, lưu trữ) [Kế hoạch xử lý tồn đọng khi Claude tiếp nhận (03/11/2026)](../../archive/ke-hoach-da-xong/KE_HOACH_XU_LY_TON_DONG_2026-11-03.md)
- (Đã xong, lưu trữ) [Kế hoạch cải thiện chất lượng I1–I7 (03/11/2026)](../../archive/ke-hoach-da-xong/KE_HOACH_CAI_THIEN_2026-11-03.md)

## Theo tuần

| Tuần | Trọng tâm | Nhật ký | Báo cáo tiến độ |
| --- | --- | --- | --- |
| 01 | Nền tảng và model | [tuan-01.md](tuan-01.md) | [BaoCaoTienDo_Tuan01.md](BaoCaoTienDo_Tuan01.md) |
| 02 | Dữ liệu và hợp đồng công cụ | [tuan-02.md](tuan-02.md) | [BaoCaoTienDo_Tuan02.md](BaoCaoTienDo_Tuan02.md) |
| 03 | Công cụ đọc, agent và sandbox cơ bản | [tuan-03.md](tuan-03.md) | [BaoCaoTienDo_Tuan03.md](BaoCaoTienDo_Tuan03.md) |
| 04 | Tích hợp công cụ tĩnh và baseline | [tuan-04.md](tuan-04.md) | [BaoCaoTienDo_Tuan04.md](BaoCaoTienDo_Tuan04.md) |
| 05 | Hoàn thiện sandbox và công cụ mở rộng | [tuan-05.md](tuan-05.md) | [BaoCaoTienDo_Tuan05.md](BaoCaoTienDo_Tuan05.md) |
| 06 | Quyết định và chạy lô | [tuan-06.md](tuan-06.md) | — |
| 07 | Hiệu chỉnh trên tập phát triển | [tuan-07.md](tuan-07.md) | — |
| 08 | Đánh giá trên tập kiểm tra | [tuan-08.md](tuan-08.md) | — |
| 09 | Viết báo cáo và phân tích lỗi | [tuan-09.md](tuan-09.md) | — |
| 10 | Demo và bàn giao | [tuan-10.md](tuan-10.md) | — |

## Ảnh và dữ liệu chạy

- Ảnh kết quả thật đặt trong [`hinh-anh/`](hinh-anh/) với tên `tuan-XX-mo-ta.png` hoặc `.jpg`, kèm chú thích lệnh, môi trường và ngày chụp. Không đưa token, secret hay mẫu độc vào ảnh. File `.svg` là hình tổng hợp, không phải ảnh chụp; `chua-co-anh.svg` chỉ đánh dấu chỗ còn trống.
- Trace và kết quả chạy lô (`reports/`) chỉ nằm trên máy chạy, không đưa lên Git. Số liệu dùng trong báo cáo được chép vào nhật ký tuần kèm `run_id`, để có thể mở lại bằng `py -3.14 -m viewer --reports reports`.
