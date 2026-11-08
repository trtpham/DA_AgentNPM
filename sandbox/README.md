# Sandbox có dấu vết và canary giả

`run_sandbox(package)` dùng image `agent-npm-sandbox:local`, mạng tắt, quyền tối thiểu và bind mount gói chỉ đọc. Gói được chép vào `/work` tạm trước khi `npm install --offline` chạy **trong container**. `strace` theo dõi tiến trình, file và kết nối; CLI lưu `strace.log` vào `sandbox/out/` (Git ignore). Canary `.npmrc`, `.ssh`, `.aws` và biến môi trường đều là chuỗi giả. Chưa nối sandbox vào agent.

Ví dụ khi Docker Linux daemon sẵn sàng:

```powershell
rtk proxy docker build -t agent-npm-sandbox:local sandbox
rtk proxy python -m sandbox.run tests/fixtures/packages/benign-package
rtk proxy python -m sandbox.run tests/fixtures/packages/canary-package
rtk proxy python -m sandbox.run tests/fixtures/packages/no-hook-package
```

**Bổ sung 07/11/2026 (Gate B0, phần không chạy mã):**
- 8 file canary giả (thêm `.git-credentials`, `.docker/config.json`, `.kube/config`, `.config/gh/hosts.yml`, `.config/solana/id.json`) và 3 biến môi trường giả (`NPM_TOKEN`, `GITHUB_TOKEN`, `AWS_SECRET_ACCESS_KEY`); giá trị biến bị coi là chạm khi xuất hiện trong output hoặc tham số tiến trình. Cần build lại image để có file mới.
- `data.behavior` (`behavior_events`): `connects` (IP, cổng, DNS, tác nhân), `persistence_writes` (ghi `.bashrc`, crontab, autostart, systemd, `/etc`), `process_tree`.
- Từ 08/11 lệnh mặc định có `--memory-swap 256m` (không swap; W5-5 phương án 1): fixture `memory` dừng ở 192 MB. `run_sandbox(package, hardening=True)` thêm `--ulimit nofile`, `--ulimit fsize` (opt-in). Build lại image: `docker build -t agent-npm-sandbox:local sandbox`.
- Agent: `sandbox: true` trong config chạy sandbox một lần trước vòng lặp, chỉ với `tests/fixtures/`. Canary bị chạm → R1 deny; gói ghi file khởi động → `R7_sandbox` review.

Chỉ chạy ba fixture vô hại trên; không chạy gói npm thật trên host. `canary_touched` ghi file giả được mở thành công và biến môi trường giả được in ra. Đọc biến môi trường mà không in ra chưa được quan sát; cần instrument tiến trình nếu muốn bắt trường hợp đó.
