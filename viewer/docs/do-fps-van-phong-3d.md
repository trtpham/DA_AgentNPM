# Đo FPS văn phòng 3D (việc tồn tuần 5)

Ngày đo: 20/11/2026. Người đo: Claude (phiên trình xem 2D/3D), theo yêu cầu của PO qua phiên chính.

## Kết luận

- **Cả 12 tình huống demo, ở cả giao diện tối và sáng, đều trên 30 FPS.** Trung bình 61–71 FPS. FPS p5 (5% khung hình chậm nhất) là 36–48 FPS.
- Giao diện sáng/tối **không ảnh hưởng FPS**. Trung bình 24 lần đo: tối 66,5 FPS, sáng 66,7 FPS. Lý do: giao diện chỉ đổi màu phần trang quanh khung 3D, cảnh 3D giữ nguyên.
- Thời gian tải đến lúc bấm được "Phát lại": 0,75–1,15 giây.
- Không tình huống nào dưới 30 FPS, nên **không sửa code**.
- Có vài khung hình lẻ chậm (thấp nhất 12–21 FPS, tức một khung 50–80 ms), thường ngay sau khi bấm Phát. Chúng không kéo p5 xuống dưới 36. Nguyên nhân chưa đo tách riêng (có thể do tạo bóng chữ/nhãn mới hoặc thu gom bộ nhớ của trình duyệt), ghi lại để theo dõi, chưa sửa.

## Máy đo

| Mục | Giá trị |
| --- | --- |
| Máy | Laptop Windows 11 Home, Intel Core i7-13620H, RAM 15,7 GB |
| GPU trình duyệt dùng | **Intel UHD Graphics** (tích hợp), ANGLE Direct3D11, driver 31.0.101.4255 |
| GPU rời (không dùng khi đo) | NVIDIA GeForce RTX 3050 6 GB Laptop, rảnh lúc đo (0 MiB dùng, Ollama không nạp model) |
| Màn hình | 1920×1080, 144 Hz |
| Trình duyệt | Google Chrome 157, cửa sổ thật (không headless), hồ sơ tạm |
| Cửa sổ trang | 1600×900, `devicePixelRatio` 1 |
| Vùng vẽ 3D | 1097×648 điểm ảnh; bộ đệm hậu kỳ khoảng 39,8 MB |
| Cấu hình trang | Mặc định: "Đồ họa cao" bật (bloom, viền tối), "Cảnh sống động" bật |

Chrome mặc định chọn GPU tích hợp (tiết kiệm điện). Đây là trường hợp **xấu hơn** so với chạy trên RTX 3050, và cũng là trường hợp máy giảng viên hay máy chiếu thường gặp.

## Kết quả (tốc độ phát 4×, mẫu 8 giây khi đang phát)

FPS TB = số lần cảnh thực sự được vẽ / thời gian. p5 = FPS ứng với khung chậm thứ 95%. Thấp nhất = khung chậm nhất trong 8 giây. "Tải xong" = từ lúc mở trang đến khi dữ liệu đã nạp và nút Phát lại bấm được.

| Tình huống | Tối: FPS TB | Tối: p5 | Tối: thấp nhất | Sáng: FPS TB | Sáng: p5 | Sáng: thấp nhất | Tải xong (tối / sáng) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1. Cài gói an toàn | 68.5 | 47.6 | 13.1 | 70.8 | 47.8 | 16.0 | 1152 / 875 ms |
| 2. Gói độc trong cây phụ thuộc | 68.1 | 47.8 | 20.6 | 69.5 | 47.8 | 18.0 | 904 / 843 ms |
| 3. OSV đã biết độc | 66.4 | 47.6 | 18.0 | 63.1 | 36.0 | 16.0 | 885 / 767 ms |
| 4. Mã bị làm rối | 66.4 | 47.8 | 18.0 | 67.3 | 47.8 | 20.6 | 855 / 789 ms |
| 5. Gói lớn tải mã ngoài (swc) | 61.8 | 47.6 | 14.4 | 66.7 | 47.8 | 15.8 | 965 / 825 ms |
| 6. Mô hình lỗi (R2) | 67.2 | 47.8 | 18.0 | 63.4 | 47.6 | 18.0 | 897 / 938 ms |
| 7. AI bịa bằng chứng (R3) | 66.1 | 47.6 | 16.0 | 65.6 | 47.8 | 20.6 | 861 / 800 ms |
| 8. OSV báo độc, AI nói lành (R5) | 65.2 | 47.8 | 12.0 | 61.5 | 36.1 | 14.4 | 841 / 754 ms |
| 9. Sandbox bắt quả tang (R1) | 66.8 | 47.8 | 14.4 | 66.8 | 47.6 | 15.9 | 808 / 809 ms |
| 10. Tên gần giống gói nổi tiếng | 69.6 | 47.8 | 18.0 | 70.5 | 47.8 | 18.0 | 946 / 788 ms |
| 11. Không tải được gói | 64.6 | 47.8 | 16.0 | 66.4 | 47.6 | 16.0 | 920 / 778 ms |
| 12. Gói độc đã từng được cài | 67.7 | 47.8 | 18.0 | 68.2 | 47.8 | 18.0 | 828 / 785 ms |

Ở tình huống 10, câu chuyện kết thúc trước khi hết 8 giây mẫu. Phần cuối mẫu vẫn có cảnh nền chuyển động nên FPS vẫn cao.

## Cách đo

1. Kiểm GPU rảnh trước khi đo: `ollama ps` không có model nào; `nvidia-smi` báo 0 MiB. Không đo khi đang đo tốc độ model, theo rủi ro đã ghi trong `docs/ke-hoach/KE_HOACH_VAN_PHONG_3D.md`.
2. Chạy trình xem: `py -3.14 -m viewer --reports reports --port 8765`.
3. Mở Chrome có cửa sổ bằng `playwright-cli`, dùng cấu hình [`do_fps_chrome.json`](do_fps_chrome.json):
   ```bash
   playwright-cli -s=fps open --config=viewer/docs/do_fps_chrome.json "http://localhost:8765/office"
   ```
   Cấu hình này bật ba cờ `--disable-backgrounding-occluded-windows`, `--disable-renderer-backgrounding`, `--disable-background-timer-throttling`. Không có chúng, Chrome tự giảm còn khoảng 1 khung/giây khi cửa sổ bị cửa sổ khác che, và số đo sai (xem "Lần đo bị loại").
4. Sinh 6 script, mỗi script 4 lần đo (12 tình huống × 2 giao diện):
   ```bash
   py -3.14 viewer/docs/do_fps_van_phong.py <thư-mục-tạm>
   playwright-cli -s=fps --raw run-code --filename=<thư-mục-tạm>/batch00.js
   ```
   Mỗi lần đo [`do_fps_van_phong.py`](do_fps_van_phong.py) làm như sau:
   - đặt `viewer.theme` = `dark` hoặc `light` trong localStorage;
   - mở `/office#mode=truck&scenario=<id>`, chờ dữ liệu nạp xong;
   - chờ 3,2 giây cho máy quay mở đầu bay xong;
   - đặt tốc độ 4×, bấm Phát lại, chờ 0,8 giây, rồi lấy mẫu 8 giây.
5. Trong 8 giây mẫu, script đếm số lần cảnh **thực sự được vẽ** (`__office.stats.frames` tăng). Lý do: trang 3D chỉ vẽ khi có thay đổi, nên chỉ đếm `requestAnimationFrame` sẽ cho FPS cao giả khi cảnh đứng yên.
   - Khoảng cách giữa hai lần vẽ cho ra FPS trung bình, p5 và khung chậm nhất.
   - Thời gian tải lấy từ `performance.now()` lúc nút Phát lại bấm được.
6. Đóng trình duyệt: `playwright-cli -s=fps close`.

## Lần đo bị loại

Lần đo đầu dùng tốc độ 16× mặc định và chưa có ba cờ ở bước 3. Kết quả bị loại vì hai lỗi đo:

- Từ lần thứ 9 trở đi, cửa sổ Chrome bị che, `requestAnimationFrame` chỉ còn ~1 lần/giây, nên FPS đo được ~1. Đây là Chrome giảm nhịp, không phải trang chậm.
- Ở 16×, nhiều câu chuyện kết thúc sau 1–3 giây, nên phần lớn mẫu đo lúc đã phát xong.

Các lần không bị che trong lượt đó cho 47–58 FPS ở 16×, cùng tầm với kết quả chính thức.

## Việc có thể làm sau

- Đo thêm khi ép Chrome dùng RTX 3050 (Windows: Cài đặt → Màn hình → Đồ họa → Chrome → Hiệu năng cao), và khi Ollama đang nạp model 9B, để biết 3D có tranh VRAM với model không (mục O-0 trong kế hoạch văn phòng 3D).
- Nếu khung chậm lẻ lúc bấm Phát gây giật thấy được khi trình chiếu, ghi hình hiệu năng bằng DevTools ở đúng lúc đó để tìm nguyên nhân trước khi sửa.
