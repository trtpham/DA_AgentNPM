# viewer/ — trình xem trace

Xem lại hoặc theo dõi trực tiếp các trace trong `reports/` mà không chạy agent.

```powershell
py -3.14 -m viewer --reports reports --port 8765
```

Mở `http://127.0.0.1:8765/`, chọn run rồi chọn gói. Có nút phát lại, bước trước/tiếp và tốc độ 1×/2×/4×. Gói đang chạy được cập nhật mỗi giây. Mở thẳng một gói: `#run=<run_id>&pkg=<tên@phiên bản>`.

| File | Việc |
| --- | --- |
| `server.py` | Server chỉ nghe `127.0.0.1`, chỉ nhận GET/HEAD |
| `static/index.html`, `app.js`, `style.css` | Trang xem trace |
| `static/office.html`, `office/` | Văn phòng 3D: cùng trace, hiển thị dạng mô phỏng |
| `static/vendor/` | Three.js 0.170.0 tải sẵn, không gọi mạng |
| `sample_traces/` | 3 trace mẫu vô hại để demo (một trace có chuỗi XSS thử nghiệm) |

Nội dung trace được đưa vào trang bằng `textContent`, không bao giờ chạy. Trang không có nút chạy agent.
