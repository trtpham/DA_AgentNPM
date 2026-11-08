# Kế hoạch dữ liệu: từ 76 lên 400–500 mẫu có nhãn (BẢN NHÁP chờ PO duyệt)

> Ngày lập: 08/11/2026 · Người lập: Claude · Người duyệt: PO Phạm Minh Triết · Owner dữ liệu: TV1 Lê Đặng Thiên Phước · Kiểm tra chéo: TV1, TV3 Nguyễn Đình Thiên, TV2 chốt.
> Căn cứ: [KE_HOACH.md](KE_HOACH.md) giai đoạn 4 — "Chuẩn bị 400–500 mẫu sau lọc trùng, tách dev/test" trước thực nghiệm tuần 7–8.

## 1. Hiện trạng (đo ngày 08/11)

| Nguồn | Số lượng | Tình trạng |
| --- | --- | --- |
| `data/labels.csv` | 76 nhãn: 54 độc, 20 lành, 2 nghi vấn; 48 dev / 28 test; 8 cụm | Chưa kiểm tra chéo (4 phiếu W5-10 trống) |
| `data/review_450/` | 450 ứng viên npm có hook, metadata đã đối chiếu (445 còn tải được) | Chưa gán nhãn, chưa đọc mã |
| Bộ Datadog `malicious-software-packages-dataset` | hàng nghìn gói npm độc, đã được chuyên gia Datadog gán nhãn | Mới lọc 3 chiến dịch (53 mẫu); chỉ đọc trong VM |
| `tests/fixtures/corpus/` | 22 gói mô phỏng | **Không tính** vào 400 (chỉ dùng đo học vẹt) |

**Vấn đề:** thiếu khoảng 330 mẫu; mất cân bằng (20 lành so với 54 độc); ít đa dạng (2 chiến dịch chiếm 36 dòng); khâu kiểm tra chéo bằng người đang tắc.

## 2. Mục tiêu bộ nhãn v1

| Chỉ tiêu | Mức tối thiểu | Lý do |
| --- | --- | --- |
| Tổng số mẫu sau lọc trùng | **≥ 400** (mục tiêu 450) | KE_HOACH giai đoạn 4 |
| `benign` có install hook | ≥ 180 | Đo FPR cần nhiều gói lành *có* script cài đặt, không phải gói lành bất kỳ |
| `malicious` | ≥ 180 | Đo Recall |
| `suspicious` | 10–40, không ép | Ca thật sự mơ hồ; không dùng làm chỗ "đổ" nhãn khó |
| Số cụm (họ gói / chiến dịch) | ≥ 40 | Tránh đo trên một vài chiến dịch có mã giống nhau |
| Trần mỗi cụm | ≤ 12 mẫu (≤ 3%) | Không cụm nào lấn át chỉ số |
| Chia dev / test | ~40% / 60%, **theo cụm** | Cụm ở test không xuất hiện ở dev (đã có trong `prepare_labels`) |
| Kiểm tra chéo | 100% mẫu dùng đo có `decision=verified` của một người thật khác người đề xuất | Quy tắc W5-10 |

## 3. Nguồn và cách lấy (giữ quy tắc an toàn AGENTS §2)

### 3.1 Gói lành (~200) — từ 450 ứng viên công khai

1. **Tải và đọc tĩnh trong container dùng một lần** (như `review_evidence.py`): `npm pack` theo đúng phiên bản và hash trong metadata; không chạy script. Một số ứng viên có thể độc dù chưa có advisory, nên **không giải nén trên máy Windows**.
2. **Phân loại sơ bộ bằng công cụ tĩnh của dự án** (`inspect_scripts`, `trace_requires`, `extract_indicators`, `list_endpoints`, `trace_flow`). Kết quả chỉ là gợi ý để sắp thứ tự, **không phải nhãn**:
   - nhóm A: hook chỉ build native (`node-gyp`, `prebuild-install`), tải binary có checksum, hoặc chạy file trong gói không gọi mạng → ứng viên `benign` dễ kiểm;
   - nhóm B: có mạng, `child_process`, đọc env… → cần đọc kỹ; có thể ra `benign` (ví dụ esbuild), `suspicious` hoặc `malicious`;
   - nhóm C: không đọc được (thiếu file, quá lớn, bị làm rối) → loại hoặc để sau.
3. **Đối chiếu OSV/GitHub Advisory** cho từng gói (đã có `tools/intel.py`). Có advisory `MAL-*` thì chuyển sang luồng 3.2.
4. Bỏ trùng theo họ: các phiên bản liên tiếp cùng một gói chỉ lấy tối đa 3 (trần cụm).

### 3.2 Gói độc (~200) — từ bộ Datadog và OSV `MAL-*`

1. **Chỉ làm trong VM** (TV3 hoặc TV1 chạy): `filter_datadog.py` lọc gói npm có hook cài đặt, ghi `name, version, hooks, sha256, cluster`.
2. **Chọn theo cụm:** mở rộng từ 3 lên ≥ 30 chiến dịch/họ; mỗi cụm tối đa 12 mẫu, ưu tiên cụm có hành vi khác nhau (đánh cắp token, dropper, reverse shell, chèn file khởi động, làm rối mã, typosquat).
3. **Bằng chứng:** `review_evidence.py` trong container trích đúng `file:dòng` của đường cài đặt, kèm hash. Không đưa tarball độc lên Git.
4. Nhãn của Datadog là **nguồn độc lập thứ nhất** (chuyên gia Datadog); người kiểm tra chéo của nhóm chỉ cần xác nhận *bằng chứng trên đường cài đặt* và hành vi chính, nên nhanh hơn gói lành.

### 3.3 Lọc trùng và chia tập

- Trùng chính xác: cùng `name@version` hoặc cùng sha256 tarball.
- Gần trùng: cùng hash của các file trên đường cài đặt (sau khi bỏ khoảng trắng) → cùng cụm, áp trần cụm.
- Gán `split` theo cụm bằng `prepare_labels` (ổn định, có seed); ghi sha256 của `labels.csv` vào `run_meta.json` khi đo (đã có).

## 4. Kiểm tra chéo (khâu tắc chính)

- **Ước lượng công:** lành nhóm A ~2 phút/mẫu, lành nhóm B và độc ~4 phút/mẫu → khoảng 400 mẫu × 3 phút ≈ **20 giờ người**, chia cho 3 người ≈ 7 giờ/người trong 1,5 tuần.
- **Chia lượt 40 mẫu** (`round-5.csv` trở đi), mỗi lượt một loại (lành A, lành B, một nhóm chiến dịch độc), để người kiểm tra quen mẫu và làm nhanh.
- **Người đề xuất nhãn ≠ người kiểm tra.** Claude/Codex được soạn bằng chứng và đề xuất, **không** điền cột kiểm tra. Đề xuất: Claude chuẩn bị bằng chứng; TV1 kiểm tra lượt độc; TV3 kiểm tra lượt lành; TV2 xử lý `revise`/`exclude` và chốt.
- Làm trước 4 phiếu W5-10 (76 dòng) để thống nhất cách điền.
- Mẫu nào chưa `verified` khi đóng băng thì **không** vào bộ đo (ghi rõ số bị loại).

## 5. Việc của Claude (code, chỉ đọc, có test)

| ID | Việc | File | Xong khi |
| --- | --- | --- | --- |
| D-1 | Phân loại sơ bộ 450 ứng viên trong container: tải đúng phiên bản + hash, chạy công cụ tĩnh, ghi bảng nhóm A/B/C kèm lý do; resume theo batch | `data/scripts/triage_candidates.py` | Test trên fixture; chạy hết 450 trong container, 0 lần chạy script gói |
| D-2 | Sinh phiếu và bằng chứng cho lượt mới từ bảng đề xuất (mở rộng `review_sheet`/`review_evidence` khỏi cố định 4 lượt) | `data/scripts/review_sheet.py`, `review_evidence.py` | `round-5…` tạo được, `check` chạy đúng |
| D-3 | Lọc trùng chính xác và gần trùng, gán cụm, áp trần cụm | `data/scripts/dedupe_labels.py` | Test với dữ liệu giả: trùng hash bị gộp, cụm vượt trần bị cắt có ghi lý do |
| D-4 | Báo cáo độ phủ: số mẫu theo nhãn/cụm/split, tỷ lệ đã kiểm tra, cụm vượt trần | `data/scripts/data_report.py` | In bảng so với chỉ tiêu mục 2 |
| D-5 | Hướng dẫn chạy luồng Datadog trong VM (lệnh, kiểm tra hash, không giải nén trên Windows) | `docs/giao-viec/D_DU_LIEU_DATADOG_VM.md` | TV3/TV1 làm theo được |

## 6. Lịch (tuần 6 → đầu tuần 8)

| Ngày | Việc | Người |
| --- | --- | --- |
| 09–10/11 | PO duyệt kế hoạch và ghi Gate (mục 7); TV1/TV3 điền 4 phiếu W5-10 | PO, TV1, TV3 |
| 09–11/11 | D-1 → D-4; chạy D-1 trên 450 ứng viên | Claude |
| 11–13/11 | Luồng Datadog trong VM: lọc ≥ 30 cụm, sinh bằng chứng | TV3 (VM), Claude soạn lệnh |
| 12–18/11 | Kiểm tra chéo theo lượt 40 mẫu | TV1, TV3; TV2 chốt |
| 19/11 | Lọc trùng, chia tập, `data_report`, **đóng băng nhãn v1** (tag Git) | TV2, Claude |
| 20/11 → | Hiệu chỉnh trên dev (tuần 7), đo test (tuần 8) | Cả nhóm |

Nếu đến 19/11 chưa đủ 400 mẫu đã kiểm tra: đóng băng với số thật đang có, ghi rõ trong báo cáo, **không** hạ chuẩn kiểm tra để đủ số.

## 7. Cần PO quyết trước khi làm

1. **Gate dữ liệu:** cho phép tải 450 tarball ứng viên bằng `npm pack` **trong container dùng một lần** (không chạy script, không giải nén trên Windows).
2. **Chỉ tiêu:** giữ ≥ 400 mẫu với ≥ 180 lành và ≥ 180 độc như mục 2, hay chấp nhận ít lành hơn nếu 450 ứng viên không đủ gói lành?
3. **Phân công kiểm tra chéo** như mục 4 (TV1 lượt độc, TV3 lượt lành, TV2 chốt).

## 8. Rủi ro

| Rủi ro | Giảm thiểu |
| --- | --- |
| Không đủ thời gian người để kiểm tra 400 mẫu | Lượt nhỏ cùng loại; bằng chứng soạn sẵn; ưu tiên lành nhóm A và độc có nhãn Datadog; đóng băng với số thật |
| Ứng viên "lành" thực ra độc | Chỉ đọc trong container; đối chiếu OSV; ca nghi ngờ thành `suspicious` hoặc loại |
| Một chiến dịch lấn át chỉ số | Trần 12 mẫu/cụm, chia theo cụm |
| Rò rỉ dev → test | Chia theo cụm, kiểm tra không cụm nào ở cả hai tập |
| Antivirus cách ly file bằng chứng | Bằng chứng ở dạng văn bản trích dòng, chỉ trên máy Triết, không đưa lên Git |
| Học vẹt theo tên | Agent đã đánh giá mù (L1); không đưa nhãn hay tên cụm vào prompt |
