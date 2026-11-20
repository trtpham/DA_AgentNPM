# viewer/ — trình xem trace

Xem lại hoặc theo dõi trực tiếp các trace trong `reports/` mà không chạy agent.

```powershell
py -3.14 -m viewer --reports reports --port 8765
```

Mở `http://127.0.0.1:8765/`, chọn run rồi chọn gói. Lọc run/gói theo tên và theo nhãn, lọc sự kiện (công cụ/mô hình/lỗi), thanh tua, phím `←` `→` `Space` `Home` `End`, bấm sự kiện để nhảy tới, nút "xem bước đọc" từ bằng chứng, nút sang văn phòng 3D. Gói đang chạy được cập nhật mỗi giây. Mở thẳng một gói: `#run=<run_id>&pkg=<tên@phiên bản>`.

| File | Việc |
| --- | --- |
| `server.py` | Server chỉ nghe `127.0.0.1`, chỉ nhận GET/HEAD |
| `static/index.html`, `app.js`, `style.css` | Trang xem trace |
| `static/office.html`, `office/` | Văn phòng 3D: cùng trace, hiển thị dạng mô phỏng |
| `static/office/rules.mjs` | Luật R1–R8 của `agent/decide.py` bằng lời, theo đúng thứ tự xét; cả 2D và 3D dùng để vẽ "bậc thang luật" |
| `GET /api/labels` | Nhãn chuẩn từ `data/labels.csv` (chỉ đọc) để lọc ca "sai nhãn chuẩn" |
| `static/vendor/` | Three.js 0.170.0 tải sẵn, không gọi mạng |
| `sample_traces/` | 3 trace mẫu vô hại để demo (một trace có chuỗi XSS thử nghiệm) |

Nội dung trace được đưa vào trang bằng `textContent`, không bao giờ chạy. Trang không có nút chạy agent.

## Đo hiệu năng

FPS văn phòng 3D trên 12 tình huống demo, giao diện sáng và tối: [`docs/do-fps-van-phong-3d.md`](docs/do-fps-van-phong-3d.md) (kèm script đo).
