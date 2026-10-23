# Sandbox cơ bản

`run_sandbox(package)` dùng Docker với mạng tắt, quyền tối thiểu và bind mount chỉ đọc. Gói được chép vào `/work` tạm trong container trước khi chạy `npm install`. Chỉ thử trên gói mô phỏng vô hại ở `tests/fixtures/benign-package`; chưa nối sandbox vào agent. Không đặt secret thật trong gói hoặc biến môi trường container.

Ví dụ khi Docker Linux daemon sẵn sàng:

```powershell
rtk python -c "from pathlib import Path; from sandbox.run import run_sandbox; print(run_sandbox(Path('tests/fixtures/benign-package')))"
```
