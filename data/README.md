# Bộ nhãn

Bố cục (sắp xếp lại ngày 05/11/2026):
- Thư mục `data/` chỉ chứa **dữ liệu**: `labels.csv`, `candidates.csv`, `review_450/`, `review_rounds/`.
- Mọi script nằm trong `data/scripts/` và chạy bằng `py -3.14 -m data.scripts.<tên>`, ví dụ `py -3.14 -m data.scripts.review_sheet check data/review_rounds/round-1.csv`.
- `data/samples/` (mẫu độc thật) bị Git ignore và chỉ mở trong VM.

## File nào dùng để làm gì?

| Đường dẫn | Vai trò |
| --- | --- |
| `labels.csv` | Bảng 76 nhãn có bằng chứng mã tĩnh; 71 nhãn thêm sau bộ 5 nhãn đầu chờ kiểm tra chéo trước khi dùng đánh giá. |
| `candidates.csv` | 5 ứng viên cũ để tham khảo, chưa phải bảng nhãn. |
| `review_450/public_candidates_450.csv` | Danh sách 450 ứng viên công khai, chưa được gán nhãn. |
| `review_450/metadata_review_450.csv` | Kết quả đối chiếu metadata của 450 ứng viên; không phải kết luận lành/độc. |
| `review_450/batches/` | 25 file kết quả theo từng lượt 18 gói; giữ lại để kiểm tra và chạy tiếp. |

Các script `.py` ở thư mục này tạo/lọc/kiểm tra dữ liệu; `REVIEW_WEEK2.md` là hồ sơ bằng chứng. Không nhập 450 ứng viên vào `labels.csv` chỉ dựa trên metadata.

`labels.csv` có 76 nhãn Codex kiểm tra tĩnh theo ủy quyền của Phạm Minh Triết: 20 `benign`, 2 `suspicious`, 54 `malicious`. Trong 71 bản mới, 53 bản độc thuộc ba chiến dịch Datadog và 18 bản lành thuộc hai họ `esbuild`/`@swc/core`. Hợp đồng mục 8 của AGENTS gốc: `id,name,version,label,behavior_main,technique,file,lines,source,split,cluster`. `source` trỏ tới tarball npm hoặc archive bằng chứng đúng phiên bản; người kiểm tra, hash và lý do nằm trong [hồ sơ tuần 2](REVIEW_WEEK2.md). `prepare_labels` từ chối bảng rỗng và chia theo cụm. Nhãn mới chờ kiểm tra chéo trước khi đánh giá; bộ này chưa đại diện để công bố accuracy/recall/F1.

`candidates.csv` lưu **metadata ứng viên**. `source_label=malicious` là nhãn advisory; `unlabeled` nghĩa là nguồn không khẳng định benign. `review_status=needs_independent_review` nghĩa là nhóm chưa kiểm tra chéo. GitHub Advisory và bản OSV tương ứng có cùng nguồn gốc nên không tính là hai lượt kiểm tra độc lập. Chỉ chuyển dòng sang `labels.csv` sau khi TV2 hoặc người được TV2 ủy quyền xác minh đúng tên, phiên bản, install hook, hành vi và ghi người kiểm tra/quyết định vào [hồ sơ tuần 2](REVIEW_WEEK2.md). Không tải hoặc đưa tarball độc vào Git.

Theo phân công trong `docs/ke-hoach/KE_HOACH.md`, TV1 phụ trách dữ liệu và Phạm Minh Triết (TV2) phụ trách kiểm tra chéo. Ngày 29/10/2026, TV2 ủy quyền Codex duyệt các gói lành; hồ sơ ghi Codex là người thực hiện, không coi đây là chữ ký kiểm tra trực tiếp của TV2.

Với mỗi ứng viên trong `candidates.csv`, người kiểm tra chéo ghi: `package@version`, bằng chứng install hook, nhãn đề xuất, hành vi chính và lý do kèm nguồn. Xác minh từng mục trước khi chuyển vào `labels.csv`.

Hai ứng viên lành có install hook đã được Codex kiểm tra tĩnh và gán nhãn `benign` theo ủy quyền. Việc không có advisory tự nó không đủ để kết luận benign; xem giới hạn và bằng chứng trong [hồ sơ tuần 2](REVIEW_WEEK2.md).

```powershell
rtk proxy python -c "from pathlib import Path; from data.scripts.prepare_labels import prepare_labels; print(prepare_labels(Path('data/labels.csv'), Path('data/labels-prepared.csv')))"
```

Không chạy lệnh trên nếu đích đã chứa nhãn thủ công cần giữ; hàm ghi đè file đích.

## Kho 450 ứng viên metadata công khai

Lượt đối chiếu manifest ngày 29/10/2026 nằm trong [`metadata_review_450.csv`](review_450/metadata_review_450.csv): 445/450 manifest còn truy cập được, khớp tên, phiên bản và install hook đã ghi; 5/450 trả HTTP 404. Cột `hook_commands` giữ lệnh lifecycle để chọn ca cần đọc mã; nó không chứng minh an toàn. Đây là ảnh chụp metadata: cả 450 dòng lúc đó còn `needs_code_review`. Sau lượt này, ba ứng viên đã được kiểm tra tĩnh và gán nhãn trong `labels.csv`; 447 ứng viên vẫn chưa có nhãn. Lượt metadata chỉ đọc npm Registry, không tải tarball, chạy install script hoặc AI scan các gói.

[`public_candidates_450.csv`](review_450/public_candidates_450.csv) chứa 450 tên gói npm duy nhất cùng phiên bản tại thời điểm tra cứu (2026-10-25 UTC). `collect_public_candidates.py` có các từ khóa dự phòng nhưng lần này đã đủ 450 ứng viên từ tìm kiếm `postinstall`; chỉ giữ manifest npm Registry có `preinstall`, `install` hoặc `postinstall`. Có 442 bản ghi với `postinstall`, 13 với `preinstall`, 8 với `install` (một gói có thể có nhiều hook); 236 tên gói có scope. `source_url` trỏ thẳng tới manifest phiên bản đã đối chiếu. Bộ thu thập chỉ gọi API metadata, không tải tarball hoặc chạy mã gói.

Toàn bộ dòng có `source_label=unlabeled` và `review_status=needs_independent_review`. Một lifecycle hook **không chứng minh gói độc hoặc lành**. Mẫu chọn theo từ khóa và xếp hạng tìm kiếm của npm, nên không đại diện thống kê cho toàn bộ hệ sinh thái. Không đưa file này vào thí nghiệm accuracy hay `labels.csv` trước khi TV2 hoặc người được ủy quyền xác minh nhãn, phiên bản, bằng chứng và phân chia tập. File `candidates.csv` 5 dòng cũ là ghi chú cục bộ bị Git ignore; không cộng tự động vào kho 450.

## Đối chiếu theo batch

`data/scripts/review_batches.py` chia danh sách cố định thành **25 batch, mỗi batch 18 gói**. Mỗi batch ghi một CSV riêng trong [`review_batches/`](review_450/batches/) sau khi hoàn tất; chạy lại sẽ kiểm tra và bỏ qua batch đã có để tiếp tục từ chỗ dừng. Nếu mạng gây `fetch_error`, batch đó chưa được ghi và có thể chạy lại. Lượt chạy ngày 29/10/2026 có 450 dòng duy nhất, 445 manifest khớp và 5 manifest HTTP 404; các trường kết quả khớp [`metadata_review_450.csv`](review_450/metadata_review_450.csv). Đây là lượt đối chiếu metadata và lệnh lifecycle, không phải AI scan hay kết luận nhãn.

```powershell
rtk proxy python -m data.scripts.review_batches --batch 1
rtk proxy python -m data.scripts.review_batches
```

Không thực thi nội dung trong cột `hook_commands`: đó là văn bản không tin cậy do nhà phát hành gói cung cấp. Quyết định nhãn mới nhất nằm ở `labels.csv` và [hồ sơ tuần 2](REVIEW_WEEK2.md); các batch là ảnh chụp metadata tại thời điểm chạy.

## Phân loại sơ bộ 450 ứng viên (D-1, 08/11/2026)

`py -3.14 -m data.scripts.triage_candidates` chạy trong container dùng một lần (tải đúng phiên bản, kiểm `sha512` của npm, giải nén an toàn trong tmpfs, chỉ đọc bằng công cụ tĩnh của dự án; không chạy script gói, không giải nén trên Windows). Kết quả: [`review_450/triage_450.csv`](review_450/triage_450.csv) và từng batch trong `review_450/triage/`.

| Nhóm | Số gói | Nghĩa |
| --- | --- | --- |
| A | 132 | Không thấy dấu hiệu rủi ro trên đường cài đặt → kiểm nhanh |
| B | 258 | Có thứ người kiểm tra phải đọc (chỉ báo rủi ro, endpoint, luồng secret/env, shell script, mã inline, làm rối) |
| C | 60 | Chưa phân loại được: 29 gói vượt giới hạn giải nén/kích thước, 8 gói 404, 3 không còn hook trong tarball, 20 không đọc được file cài đặt |

**Nhóm không phải nhãn.** Nhóm A chỉ có nghĩa là công cụ tĩnh không thấy dấu hiệu; nhóm B gồm cả gói lành (tải binary, build) lẫn gói đáng ngờ. Ví dụ `@ma.vu/virus@1.0.3` (nhãn `suspicious` trong `labels.csv`) nằm ở nhóm B vì `moon.sh`. Nhãn chỉ được ghi sau khi người thật kiểm tra (kế hoạch [KE_HOACH_DU_LIEU_400](../docs/ke-hoach/KE_HOACH_DU_LIEU_400.md)).

## Lượt kiểm tra chéo mới từ đề xuất (D-2, 08/11/2026)

```powershell
py -3.14 -m data.scripts.propose_labels 5 --limit 40              # nhóm A → data/proposals.csv + data/review_rounds/round-5.csv
py -3.14 -m data.scripts.review_evidence 5 --labels data/proposals.csv   # bằng chứng trong container → evidence/round-5.md (chỉ trên máy)
py -3.14 -m data.scripts.review_sheet check data/review_rounds/round-5.csv
```

- `data/proposals.csv` cùng hợp đồng 11 cột với `labels.csv`. Mỗi dòng là **bản nháp do Claude viết từ phân loại tĩnh**: nhãn `benign`, file mà hook chạy và tối đa 150 dòng đầu, `technique = draft-no-risky-sign`, `split = pending`. Bản nháp **không** dùng để đo cho tới khi người khác người soạn đánh `verified` trong phiếu.
- Chỉ nhóm A được đề xuất tự động; nhóm B cần người đọc mã trước. Mỗi cụm tối đa 12 dòng (tính cả `labels.csv`).
- Lượt 5: 40 gói, phân công TV3 Nguyễn Đình Thiên (lượt lành, theo kế hoạch dữ liệu). Cách điền giống [phiếu W5-10](../docs/giao-viec/W5-10_KIEM_TRA_CHEO_NHAN.md); nếu đoạn trích không đủ để kết luận, ghi `exclude` hoặc `revise` kèm `note`.

## Lọc trùng và trần cụm (D-3, 08/11/2026)

```powershell
py -3.14 -m data.scripts.dedupe_labels --report reports/dedupe.json               # chỉ báo cáo
py -3.14 -m data.scripts.dedupe_labels --output data/dataset-v1-draft.csv         # ghi bảng đã lọc (không bao giờ ghi labels.csv)
```

Thứ tự luật: cùng `name@version` → giữ dòng đầu (`labels.csv` trước `proposals.csv`); cùng sha256 tarball → một mẫu; cùng `install_hash` (mã chạy lúc cài, bỏ tên/phiên bản/khoảng trắng; tính trong D-1) → gộp cụm; cụm quá 12 dòng → giữ 12 dòng đầu; cụm có ở cả dev và test → báo rò rỉ.

Lần chạy 08/11 trên 76 nhãn + 40 đề xuất: giữ **99**, bỏ 17 (đều do trần cụm: `mut-4831` 5, `npm-token-worm-2026-03` 6, `shai-hulud-2-2025-11` 6), gộp 1 cặp cụm, 47 cụm, 0 cụm rò rỉ dev/test. Trong 450 ứng viên có 10 nhóm mã cài đặt giống hệt nhau (21 gói), ví dụ 3 gói `@db-ux/*`.

## Báo cáo độ phủ (D-4)

`py -3.14 -m data.scripts.data_report` so bộ nhãn sau lọc trùng (D-3) với chỉ tiêu v1 (≥ 400 mẫu, ≥ 180 lành, ≥ 180 độc, ≥ 40 cụm, cụm ≤ 12). Chỉ dòng `verified` trong phiếu kiểm tra mới được tính. Ngày 08/11: 0/400 verified; 99 dòng sau lọc trùng đang chờ kiểm tra. Luồng mẫu độc từ Datadog: [phiếu D-5](../docs/giao-viec/D_DU_LIEU_DATADOG_VM.md).
