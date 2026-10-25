# Sandbox có dấu vết và canary giả

`run_sandbox(package)` dùng image `agent-npm-sandbox:local`, mạng tắt, quyền tối thiểu và bind mount gói chỉ đọc. Gói được chép vào `/work` tạm trước khi `npm install --offline` chạy **trong container**. `strace` theo dõi tiến trình, file và kết nối; CLI lưu `strace.log` vào `sandbox/out/` (Git ignore). Canary `.npmrc`, `.ssh`, `.aws` và biến môi trường đều là chuỗi giả. Chưa nối sandbox vào agent.

Ví dụ khi Docker Linux daemon sẵn sàng:

```powershell
rtk proxy docker build -t agent-npm-sandbox:local sandbox
rtk proxy python -m sandbox.run tests/fixtures/benign-package
rtk proxy python -m sandbox.run tests/fixtures/canary-package
rtk proxy python -m sandbox.run tests/fixtures/no-hook-package
```

Chỉ chạy ba fixture vô hại trên; không chạy gói npm thật trên host. `canary_touched` ghi file giả được mở thành công và biến môi trường giả được in ra. Đọc biến môi trường mà không in ra chưa được quan sát; cần instrument tiến trình nếu muốn bắt trường hợp đó.
