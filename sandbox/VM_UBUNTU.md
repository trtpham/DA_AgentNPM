# Chạy sandbox trên mẫu độc trong VM Ubuntu (pha A)

Gate B0 2026-11-09. Mẫu độc chỉ được **chạy** (cài thử) trong VM này. Máy Windows chỉ nhận lại file JSON tóm tắt hành vi, không nhận mã gói.

## 1. Dựng lại VM sạch

1. Xóa VM cũ hoặc khôi phục về bản cài mới. Không giữ dữ liệu, khóa SSH hay token của đồ án cơ sở.
2. Cài Ubuntu Server 24.04 LTS: 4 vCPU, 8 GB RAM, ổ 60 GB.
3. **Tắt** thư mục chia sẻ, clipboard chung, kéo thả giữa máy thật và VM.
4. Mạng: NAT (pha A cần tải gói từ `registry.npmjs.org` và kho Datadog trên GitHub). Sandbox tự tắt mạng khi cài gói (`--network none`).
5. Tạo user thường, không đăng nhập tài khoản cá nhân (GitHub, npm, cloud) trong VM.
6. Chụp snapshot **"sach"** ngay sau bước 7. Sau mỗi đợt chạy mẫu độc, khôi phục về snapshot này.

## 2. Cài đặt (bước 7)

```bash
sudo apt update && sudo apt install -y docker.io python3 python3-venv python3-pydantic python3-pytest git
sudo usermod -aG docker "$USER"   # đăng xuất rồi vào lại
git clone https://github.com/trtpham/DA_AgentNPM.git && cd DA_AgentNPM
docker build -t agent-npm-sandbox:local sandbox
docker build -t agent-npm-runner:local experiments/runner
RUN_SANDBOX_TESTS=1 python3 -m pytest -q tests/test_sandbox_limits.py   # phải đạt 14/14 trước khi chạy mẫu độc
```

Chép `data/labels-v1.csv` (chỉ là bảng nhãn, không chứa mã) vào VM bằng `scp`.

## 3. Chạy pha A

```bash
python3 -m experiments.sandbox_batch sbx-dev-v1 --labels data/labels-v1.csv --split dev
python3 -m experiments.sandbox_batch sbx-test-v1 --labels data/labels-v1.csv --split test
```

- Mỗi gói: tạo volume `agentnpm-…` → container chuẩn bị tải và giải nén vào volume → sandbox cài thử từ volume → xóa volume.
- Kết quả: `reports/<run_id>/sandbox/*.json`. Chỉ có tóm tắt hành vi (kết quả, canary bị chạm, kết nối, file khởi động, cây tiến trình); không có strace, stdout hay mã gói.
- Bị ngắt thì chạy lại đúng lệnh; gói đã có kết quả được bỏ qua.
- Kiểm tra sau mỗi đợt: `docker volume ls | grep agentnpm` phải rỗng.

## 4. Đưa kết quả về máy Windows (pha B)

```bash
tar czf sbx-dev-v1.tgz -C reports sbx-dev-v1/sandbox     # trong VM
scp <user>@<ip-vm>:DA_AgentNPM/sbx-dev-v1.tgz .            # trên máy Windows
```

Trên máy Windows, giải nén vào `reports/` rồi chạy agent với cấu hình có sandbox:

```powershell
py -3.14 -m experiments.run_isolated dev-v1-a-llm-xs A-LLM-XS --labels data/labels-v1.csv --split dev --sandbox-results reports/sbx-dev-v1/sandbox
```

Gói thiếu kết quả sandbox không bao giờ được tự động cho phép.

## 5. Lưu ý khi đọc kết quả

- Gói lành cần mạng lúc cài (tải binary như `esbuild`, `@swc/core`) sẽ ra `outcome: failed` vì sandbox tắt mạng. Kết quả "không trọn vẹn" chặn tự động cho phép, nên cấu hình `-XS` sẽ có tỉ lệ chuyển người xem cao hơn `-X`. Ghi rõ điều này khi so sánh có và không có sandbox.
- Khôi phục snapshot "sach" sau khi chạy xong mẫu độc.
