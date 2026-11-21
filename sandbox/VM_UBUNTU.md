# Chạy sandbox trên mẫu độc trong VM Ubuntu (pha A)

Gate B0 2026-11-09. Mẫu độc chỉ được **chạy** (cài thử) trong VM này, bên trong container sandbox tắt mạng. Máy Windows chỉ nhận lại file JSON tóm tắt hành vi, không bao giờ nhận mã gói.

Thứ tự: dựng VM (mục 1–3) → cài và kiểm tra (mục 4–6) → chụp snapshot sạch (mục 7) → **sau 19/11** chạy mẫu độc (mục 8–10) → khôi phục snapshot (mục 11).

## 1. Tạo VM mới (khuyến nghị) hoặc dùng lại VM cũ

**Khuyến nghị: tạo VM mới**, giữ nguyên `D:\DACS_PROJECT\Lab\Ubuntu Server\Ubuntu Server_SIEM.vmx` của đồ án cơ sở. VM cũ có 8 snapshot và cấu hình mạng `VMnet2` của lab SIEM; dọn sạch nó tốn công hơn cài mới, và dễ sót khóa hay cấu hình cũ.

Nếu vẫn muốn dùng lại VM cũ: trong VMware chọn VM đó → **VM → Manage → Delete from Disk** (xóa hẳn cùng mọi snapshot), rồi làm như tạo mới bên dưới. Không dùng lại ổ đĩa cũ.

## 2. Tạo VM trong VMware Workstation

1. **File → New Virtual Machine… → Typical → Next.**
2. **Installer disc image file (iso):** `D:\DACS_PROJECT\Lab\Ubuntu Server\ubuntu-24.04.4-live-server-amd64.iso` → Next.
3. **Virtual machine name:** `AgentNPM-Sandbox`. **Location:** `D:\DACN\VM\AgentNPM-Sandbox` → Next.
4. **Disk:** 60 GB, *Store virtual disk as a single file* → Next.
5. **Customize Hardware…**
   - Memory: **6 GB** (máy có 16 GB; không chạy cùng lúc với Ollama nặng).
   - Processors: **4** lõi.
   - Network Adapter: **NAT** (không dùng `VMnet2` của lab cũ).
   - Xóa **Sound Card**, **Printer**; USB Controller để mặc định hoặc xóa.
   - Close → **Finish**. Chưa bật VM.
6. **VM → Settings → Options:**
   - **Shared Folders: Disabled.**
   - **Guest Isolation:** bỏ chọn *Enable drag and drop* và *Enable copy and paste*.
   - OK.

## 3. Cài Ubuntu Server

Bật VM, trình cài đặt hiện ra. Dùng phím mũi tên, Space để chọn, Enter để tiếp.

1. Language: **English**. Keyboard: mặc định.
2. Type of install: **Ubuntu Server** (không chọn minimized).
3. Network: để DHCP (VMware NAT tự cấp IP). Proxy: để trống. Mirror: mặc định, chờ kiểm tra xong.
4. Storage: **Use an entire disk**, bỏ chọn *Set up this disk as an LVM group* → Done → Continue.
5. Profile:
   - Your name: `agent`; Server name: `agentnpm-vm`; Username: `agent`.
   - Mật khẩu: mật khẩu mới, **không dùng lại** mật khẩu cá nhân.
6. Ubuntu Pro: **Skip**.
7. SSH: **chọn Install OpenSSH server** (để chép file từ Windows). Không import khóa.
8. Featured snaps: **không chọn gì** (đặc biệt không chọn `docker` snap).
9. Chờ cài xong → **Reboot Now**. Nếu màn hình báo gỡ đĩa cài, nhấn Enter.

## 4. Cập nhật và cài phần mềm

Đăng nhập trên cửa sổ VM bằng `agent`, rồi:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y docker.io python3-venv git tmux
sudo usermod -aG docker agent
sudo reboot
```

Sau khi khởi động lại, đăng nhập và lấy IP:

```bash
ip -4 addr show | grep inet        # ví dụ 192.168.x.y trên ens33
docker run --rm hello-world        # phải in "Hello from Docker!"
```

Từ đây có thể làm việc qua SSH trên PowerShell của Windows (dễ dán lệnh hơn): `ssh agent@<IP>`.

## 5. Đưa mã nguồn vào VM (không đăng nhập GitHub trong VM)

Trên **Windows** (PowerShell), đóng gói đúng commit hiện tại rồi chép sang:

```powershell
cd D:\DACN\DA_AgentNPM
git archive --format=tar.gz -o $env:TEMP\agentnpm.tgz HEAD
scp $env:TEMP\agentnpm.tgz agent@<IP>:~/
```

Trong **VM**:

```bash
mkdir -p ~/DA_AgentNPM && tar xzf ~/agentnpm.tgz -C ~/DA_AgentNPM && cd ~/DA_AgentNPM
python3 -m venv .venv
.venv/bin/pip install pydantic==2.13.2 pytest     # apt chỉ có pydantic 1, dự án cần bản 2
docker build -t agent-npm-sandbox:local sandbox
docker build -t agent-npm-runner:local experiments/runner
```

`git archive` chỉ lấy file đã commit, nên không kéo theo `data/samples/`, `reports/` hay tài liệu nội bộ.

## 6. Kiểm tra trước khi dùng

```bash
cd ~/DA_AgentNPM
RUN_SANDBOX_TESTS=1 .venv/bin/python -m pytest -q tests/test_sandbox_limits.py   # yêu cầu: 18 passed (từ 20/11)
.venv/bin/python -m pytest -q tests/test_sandbox_batch.py                         # yêu cầu: 15 passed (từ 21/11)
```

Chạy thử pha A trên 2 gói **lành** (bảng nhãn cũ có sẵn trong mã):

```bash
head -3 data/labels.csv > /tmp/labels2.csv
.venv/bin/python -m experiments.sandbox_batch sbx-smoke --labels /tmp/labels2.csv
docker volume ls | grep agentnpm || echo "khong con volume"
```

Kết quả đúng: 2 dòng kết quả (từ 20/11 có thể `ok` hoặc `failed`: hai gói này tải binary qua mạng lúc cài, sandbox tắt mạng nên thất bại vẫn là bình thường; dependency thì đã được tải sẵn ở bước cache), và không còn volume nào. Nếu một bước không đạt: ghi FAIL vào nhật ký, **không** chạy mẫu độc.

## 7. Chụp snapshot sạch

```bash
rm -rf ~/DA_AgentNPM/reports/sbx-smoke && sudo poweroff
```

Trong VMware: **VM → Snapshot → Take Snapshot…**, tên `sach`, mô tả "cài xong, test 14/14, chưa chạy mẫu độc". Bật lại VM.

## 8. Chạy mẫu độc (chỉ sau khi đóng băng nhãn v1, 19/11)

Chép bảng nhãn từ Windows (chỉ là văn bản):

```powershell
scp D:\DACN\DA_AgentNPM\data\labels-v1.csv agent@<IP>:~/DA_AgentNPM/data/
```

Trong VM, chạy trong `tmux` để mất kết nối SSH không làm dừng lô:

```bash
cd ~/DA_AgentNPM && tmux new -s sbx
.venv/bin/python -m experiments.sandbox_batch sbx-dev-v1 --labels data/labels-v1.csv --split dev
.venv/bin/python -m experiments.sandbox_batch sbx-test-v1 --labels data/labels-v1.csv --split test
```

- Thoát tmux mà lô vẫn chạy: `Ctrl+B` rồi `D`. Vào lại: `tmux attach -t sbx`.
- Mỗi gói: tạo volume `agentnpm-…` → container chuẩn bị tải và giải nén vào volume → sandbox cài thử (tắt mạng, tối đa 60 giây) → xóa volume. Ước tính 30–90 giây/gói.
- Bị ngắt thì chạy lại đúng lệnh; gói đã có kết quả được bỏ qua. Đầu mỗi lô tự dọn volume `agentnpm-*` và container `agentnpm-sbx-*` còn sót (từ 21/11).
- Trước khi chạy, lô tự kiểm tra: có đủ 2 image, đĩa trống ≥ 5 GB; thiếu thì dừng với thông báo `preflight: …`. `sandbox_meta.json` ghi digest image, sha256 bảng nhãn và số đếm theo `fail_reason`.
- Mỗi kết quả có `script_ran` (install script đã chạy chưa) và `fail_reason`: `network` (script cần mạng), `missing_tool` (thiếu công cụ như Python, `vercel`), `resource` (timeout/RAM/PID), `script` (script tự lỗi) là hành vi của gói, giữ nguyên; `not_started`, `prepare`, `infra` là lỗi hạ tầng, đã tự thử lại 1 lần. Còn sót thì chạy lại riêng chúng bằng cùng lệnh thêm `--retry-failed`.
- Xong mỗi lô: `cat reports/sbx-dev-v1/sandbox/sandbox_meta.json` xem số đếm; `docker volume ls | grep agentnpm` phải rỗng.

## 9. Đưa kết quả về Windows

Trong VM:

```bash
cd ~/DA_AgentNPM && tar czf ~/sbx-v1.tgz -C reports sbx-dev-v1/sandbox sbx-test-v1/sandbox
```

Trên Windows:

```powershell
scp agent@<IP>:~/sbx-v1.tgz $env:TEMP\
tar xzf $env:TEMP\sbx-v1.tgz -C D:\DACN\DA_AgentNPM\reports
```

File nhận về chỉ có tóm tắt hành vi: kết quả, canary bị chạm, kết nối, file khởi động, cây tiến trình. Không có strace, stdout hay mã gói.

## 10. Chạy agent có sandbox trên Windows (pha B)

```powershell
cd D:\DACN\DA_AgentNPM
foreach ($v in "A-LLM-XS","A-SLM-XS","A-TLM-XS") {
  py -3.14 -m experiments.run_isolated "dev-v1-$($v.ToLower())" $v --labels data/labels-v1.csv --split dev --sandbox-results reports/sbx-dev-v1/sandbox
}
```

Tập test làm y hệt với `test-v1-…`, `--split test` và `reports/sbx-test-v1/sandbox`, sau khi đã khóa cấu hình. Gói thiếu kết quả sandbox không bao giờ được tự động cho phép.

## 11. Dọn sau khi chạy mẫu độc

Tắt VM → **VM → Snapshot → Revert to Snapshot "sach"**. Không dùng VM đã chạy mẫu độc cho việc khác.

## 12. Chạy lại pha A sau khi sửa sandbox (20/11)

Lô `sbx-dev-v1` chạy trước 20/11 phần lớn ra `failed` vì lỗi phương pháp, không phải vì gói: `npm install --offline` chạy ngay trong thư mục gói nên đòi cả devDependency (ENOTCACHED), `/tmp` chỉ đọc (EROFS), trace dài mất đầu cây tiến trình. Bản sửa: bước chuẩn bị (có mạng) tải sẵn dependency vào npm cache trong volume bằng `--ignore-scripts` (không chạy mã gói); bước sandbox (tắt mạng) tạo dự án rỗng rồi `npm install --offline <tarball gói>` như người dùng thật; `/tmp` là tmpfs 64 MB `noexec`; trace bỏ dòng đọc file trong gói, vượt trần thì giữ đầu + cuối. Kết quả cũ **không dùng được**, phải chạy lại cả lô.

1. Tắt VM → **VM → Snapshot → Revert to Snapshot "sach"** (bỏ trạng thái đã chạy mẫu độc). Bật VM, lấy IP (`ip -4 addr show | grep inet`).
2. Trên Windows, đóng gói commit mới và chép sang (như mục 5):

   ```powershell
   cd D:\DACN\DA_AgentNPM
   git archive --format=tar.gz -o $env:TEMPgentnpm.tgz HEAD
   scp $env:TEMPgentnpm.tgz agent@<IP>:~/
   ```

3. Trong VM, thay mã cũ bằng mã mới và build lại image sandbox (có thêm `cache_deps.sh`):

   ```bash
   rm -rf ~/DA_AgentNPM && mkdir -p ~/DA_AgentNPM && tar xzf ~/agentnpm.tgz -C ~/DA_AgentNPM && cd ~/DA_AgentNPM
   python3 -m venv .venv && .venv/bin/pip install pydantic==2.13.2 pytest
   docker build -t agent-npm-sandbox:local sandbox
   docker build -t agent-npm-runner:local experiments/runner
   ```

4. Kiểm tra như mục 6: `18 passed` và `10 passed`. Không đạt thì dừng, ghi FAIL.
5. Chụp lại snapshot sạch (mục 7), đặt tên `sach-2011` để phân biệt.
6. Chép `labels-v1.csv` sang (mục 8), rồi chạy lại lô dev với **run id mới** để không lẫn với kết quả lỗi (gói đã có kết quả bị bỏ qua khi chạy lại cùng id):

   ```bash
   cd ~/DA_AgentNPM && tmux new -s sbx
   .venv/bin/python -m experiments.sandbox_batch sbx-dev-v1b --labels data/labels-v1.csv --split dev
   ```

   Mỗi gói giờ có thêm bước cache (cần mạng NAT của VM tới registry.npmjs.org), nên chậm hơn khoảng 10–60 giây/gói. Mỗi file kết quả có thêm `dependencies.ok`; `sandbox_meta.json` có thêm `cache_failed`.
7. Đưa kết quả về Windows như mục 9, thay `sbx-dev-v1` bằng `sbx-dev-v1b`. Pha B (mục 10) dùng `--sandbox-results reports/sbx-dev-v1b/sandbox`.
8. Xong: revert snapshot (mục 11).

## Lưu ý khi đọc kết quả

- Gói lành cần mạng lúc cài (tải binary như `esbuild`, `@swc/core`) ra `outcome: failed`. Kết quả không trọn vẹn chặn tự động cho phép, nên cấu hình `-XS` có tỉ lệ chuyển người xem cao hơn `-X`. Ghi rõ điều này trong bảng so sánh có/không có sandbox.
- Mạng NAT của VM vẫn ra được mạng LAN của máy thật. Mã độc chỉ chạy trong container `--network none`, nên rủi ro còn lại là lỗ hổng thoát container, thấp; đó là lý do dùng VM riêng và snapshot.
