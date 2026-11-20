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

**Sửa phương pháp 20/11/2026 (Gate B0, chẩn đoán 15/11 trên 3 gói lành):**
- Cài như người dùng thật: `run_install.sh` đóng gói `/input` thành tarball bằng `tar` (không qua npm), tạo dự án rỗng trong `/work/project` rồi `npm install --offline --foreground-scripts <tarball>`. devDependency không còn cần; lifecycle script của gói và của dependency production chạy như ngoài đời. Lý do: trước đây `npm install` chạy trong thư mục gói dừng ở ENOTCACHED, script không bao giờ chạy. `--foreground-scripts` chỉ để output script của dependency hiện ra stdout (npm mặc định ẩn), canary in ra vẫn bắt được.
- Bước cache (`cache_deps.sh`, `cache_command`/`cache_dependencies` trong `run.py`): có mạng, `npm install --ignore-scripts` chỉ để đổ dependency vào `npm-cache/` trong volume; không chạy script nào, không có canary. Bước sandbox gắn `npm-cache/` chỉ đọc vào `/cache`. Fixture (bind mount) dùng cache rỗng.
- `/tmp`: tmpfs 64 MB `noexec,nosuid` (trước đây chỉ đọc, script gặp EROFS khi `mkdtemp`). Nằm trong cùng trần RAM 256 MB; file trong `/tmp` không chạy được.
- Trace: bỏ các lời gọi file một đường dẫn nằm trong `/work/` hoặc thư mục npm (không bao giờ tính là file ngoài gói, canary hay ghi khởi động); `execve`, `clone`, `connect`, `rename`/`link` giữ nguyên. Vẫn vượt ~1,9 MB thì giữ đầu + cuối (trước chỉ giữ cuối, mất gốc cây tiến trình) và `TRACE_TRUNCATED=1`, nên kết quả không bao giờ được coi là trọn vẹn.
- Giữ nguyên: `--network none`, `--read-only`, `--cap-drop ALL` + `SYS_PTRACE`, `no-new-privileges`, 256 MB không swap, 64 PID, 60 s, canary. Test: `tests/fixtures/sandbox-limits/{dev-dependency,tmp-dir,big-trace}`. Build lại image sau khi kéo mã.
