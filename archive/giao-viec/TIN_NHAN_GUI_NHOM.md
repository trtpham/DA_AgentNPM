# Tin nhắn giao việc tuần 5 (soạn sẵn để dán)

Thay `<TV1>`, `<TV3>` bằng tên thật trước khi gửi.

## 1. Gửi nhóm chung

> Chào cả nhóm, tuần 5 còn 2 việc cần người thật làm, mình đã soạn sẵn hướng dẫn trong repo, thư mục `docs/tien-do/giao-viec/`:
>
> 1. **W5-5 — <TV3> nghiệm thu cách ly sandbox** (~45 phút, hạn 07/11): file `W5-5_NGHIEM_THU_SANDBOX_TV3.md`. Có nghiệm thu thì mới nối sandbox vào agent được.
> 2. **W5-10 — kiểm tra chéo 76 nhãn** (hạn 09/11): file `W5-10_KIEM_TRA_CHEO_NHAN.md`. <TV1> làm lượt 1 + 4 (40 dòng), <TV3> làm lượt 2 + 3 (36 dòng). Việc này đang chặn phần thực nghiệm tuần 7–8, nhờ mọi người ưu tiên.
>
> File bằng chứng nhãn chỉ có trên máy mình (không đưa lên Git vì chứa mã độc dạng chữ). Tiện nhất là qua máy mình làm, hoặc mình gửi riêng từng người. W5-8 (tốc độ A-LLM) đã chốt ĐẠT: giảm 45%.

## 2. Gửi riêng <TV3>

> <TV3> ơi, nhờ bạn 2 việc:
>
> **(a) Nghiệm thu sandbox W5-5**, hướng dẫn từng bước trong `W5-5_NGHIEM_THU_SANDBOX_TV3.md`:
> - đọc bảng W5-1…W5-4 trong `tuan-05.md`;
> - tự chạy 2 lệnh (test Docker 8/8 và bảng `demo_sandbox`);
> - tick checklist 10 mục;
> - chọn phương án swap (đề xuất phương án 1: thêm `--memory-swap 256m`);
> - ký theo mẫu cuối file.
>
> Bạn qua máy mình làm cho tiện vì image Docker có sẵn.
>
> **(b) Kiểm tra chéo nhãn lượt 2 và 3** (36 dòng, 2 chiến dịch, mã khá giống nhau nên nhanh): xem `W5-10_KIEM_TRA_CHEO_NHAN.md`. Mình gửi riêng 2 file bằng chứng `round-2.md`, `round-3.md`. Đừng mở link zip trong đó trên máy Windows nhé. Điền xong thì chạy lệnh `check` phải ra `complete: True`.

## 3. Gửi riêng <TV1>

> <TV1> ơi, nhờ bạn kiểm tra chéo nhãn **lượt 1 (20 gói lành) và lượt 4 (20 gói độc họ khác)**, hướng dẫn trong `W5-10_KIEM_TRA_CHEO_NHAN.md`.
>
> - Mỗi dòng: đọc đoạn mã trích trong file bằng chứng, tự mô tả "nguồn → hành động → đích", rồi điền `decision`, họ tên, ngày, 1 câu hành vi, và `note` nếu sửa hoặc loại.
> - Mở CSV bằng VS Code hoặc LibreOffice, **đừng dùng Excel** (Excel làm hỏng cột số dòng).
> - Mình gửi riêng 2 file bằng chứng `round-1.md`, `round-4.md`.
> - Hạn 09/11. Không chắc thì đừng ghi `verified`, cứ ghi `revise` hoặc `exclude` kèm lý do.
