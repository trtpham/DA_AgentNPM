# Giao việc D-5 — Lọc mẫu độc từ bộ Datadog trong VM

> **Không cần làm nữa (08/11/2026):** PO duyệt dùng container Docker thay VM (Gate B0 08/11). Claude đã chạy `data/scripts/datadog_container.py` trên 800 ZIP và sinh lượt 10–15. Phiếu này giữ lại cho trường hợp cần chạy trong VM.

**Người nhận:** TV3 Nguyễn Đình Thiên (có VM Ubuntu) · **Người giao:** TV2 Phạm Minh Triết (PO) · **Ngày giao:** 08/11/2026 · **Hạn đề xuất:** 13/11/2026
**Thời lượng:** khoảng 45 phút, phần lớn là máy chạy · **Kế hoạch:** [KE_HOACH_DU_LIEU_400.md](../ke-hoach/KE_HOACH_DU_LIEU_400.md), mục 3.2

## Vì sao phải làm trong VM

Bộ [`DataDog/malicious-software-packages-dataset`](https://github.com/DataDog/malicious-software-packages-dataset) chứa **mã độc thật** đã nén (ZIP có mật khẩu). Theo AGENTS.md §2, máy Windows của nhóm chỉ được giữ metadata; các file ZIP chỉ nằm trong VM. Script lọc **chỉ đọc** ZIP và `package.json` bên trong; không giải nén ra đĩa, không chạy mã gói.

## Kết quả cần nộp

**Một file CSV duy nhất:** `datadog-candidates.csv` với các cột `name, version, hooks, sha256, cluster, archive`. Không gửi file ZIP, không gửi mã nguồn của gói.

## Các bước (trong VM Ubuntu)

1. **Chuẩn bị** (một lần). VM cần Python ≥ 3.11 và git; nên tắt thư mục chia sẻ với Windows trong lúc làm.
   ```bash
   git clone --depth 1 https://github.com/trtpham/DA_AgentNPM.git ~/DA_AgentNPM
   git clone --depth 1 https://github.com/DataDog/malicious-software-packages-dataset.git ~/datadog
   ```
2. **Lọc** (khoảng 10–30 phút tùy máy). Script đọc mọi `*.zip` trong `samples/npm`, chỉ giữ gói có `preinstall`/`install`/`postinstall`/`prepare`, và **giữ một mẫu cho mỗi cụm** (mã cài đặt giống nhau thì cùng cụm):
   ```bash
   cd ~/DA_AgentNPM
   python3 -m data.scripts.filter_datadog ~/datadog/samples/npm ~/datadog-candidates.csv
   ```
   Lệnh in một dòng JSON với `scanned`, `matching`, `failed`, `written`. **Chép dòng này** vào tin nhắn nộp kết quả.
3. **Kiểm tra nhanh:**
   ```bash
   wc -l ~/datadog-candidates.csv          # số dòng = written + 1 dòng tiêu đề
   head -3 ~/datadog-candidates.csv        # cột name,version,hooks,sha256,cluster,archive
   ```
4. **Chuyển file CSV ra ngoài:** chỉ chép `~/datadog-candidates.csv` sang máy Triết (USB, Drive cá nhân hoặc thư mục chia sẻ bật tạm). Đặt vào `D:\DACN\DA_AgentNPM\data\datadog-candidates.csv`.
5. **Dọn VM** (tùy chọn): `rm -rf ~/datadog` nếu không cần chạy lại.

## Không được làm

- Không chạy `npm install`, `node`, hay giải nén ZIP trong VM ngoài script trên.
- Không chép ZIP hay thư mục `samples/` sang Windows, không đưa lên Git hay nhóm chat.
- Không sửa nhãn trong CSV: nhãn "độc" là của Datadog; nhóm chỉ kiểm tra bằng chứng ở bước sau.

## Sau khi nộp

1. Claude chuyển CSV thành đề xuất `malicious` trong `data/proposals.csv`, chọn tối đa 12 mẫu mỗi cụm và ưu tiên cụm có hành vi khác nhau (D-6, chưa làm).
2. Bằng chứng `file:dòng` được tạo trong container dùng một lần bằng `review_evidence` (cách đã dùng cho lượt 2–4); file bằng chứng chỉ ở trên máy Triết.
3. TV1 Lê Đặng Thiên Phước kiểm tra chéo các lượt độc (phân công trong kế hoạch dữ liệu).

## Báo kết quả

Nhắn Triết: dòng JSON ở bước 2, số dòng ở bước 3, ngày chạy, và commit của repo DataDog đã clone (`git -C ~/datadog rev-parse HEAD`).
