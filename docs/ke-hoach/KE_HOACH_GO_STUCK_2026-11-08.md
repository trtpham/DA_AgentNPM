# Kế hoạch gỡ các điểm tắc (08/11/2026, chờ PO duyệt)

> Người lập: Claude · PO: Phạm Minh Triết · Thành viên: TV1 Lê Đặng Thiên Phước, TV3 Nguyễn Đình Thiên.
> Phần mềm (agent, công cụ, sandbox, công cụ dữ liệu) đã chạy ổn định: pytest 268 passed, Docker 14/14, Node 19/19, agent thật 8/8. **Mọi điểm tắc còn lại nằm ở dữ liệu và việc của người.** Mốc cứng: đóng băng nhãn v1 ngày **19/11** để kịp thực nghiệm tuần 7–8.

## 1. Danh sách điểm tắc

| # | Điểm tắc | Ảnh hưởng | Chặn gì | Ai gỡ được |
| --- | --- | --- | --- | --- |
| S1 | **0/400 mẫu đã kiểm tra chéo.** 116 dòng có sẵn phiếu (W5-10: 76, lượt 5: 40) nhưng chưa ai điền | Không có số liệu đáng tin cho Precision/Recall/F1/FPR | Tuần 7–10 | Người thật |
| S2 | **Chưa có nguồn mẫu độc mới.** Chưa có VM; luồng Datadog chưa chạy | Độc chỉ còn 37 mẫu sau trần cụm; cần ≥ 180 | S4, tuần 7–8 | PO quyết + 1 người chạy |
| S3 | **Thiếu gói lành.** Nhóm A còn 92 chưa đề xuất; nhóm A tổng 132 < 180 | Chỉ tiêu lành ≥ 180 không đạt nếu chỉ dùng nhóm A | Tuần 7–8 | Claude + người kiểm tra |
| S4 | **D-6 chưa làm** (CSV Datadog → đề xuất `malicious`) | Không sinh được lượt độc | S1 phần độc | Claude, sau S2 |
| S5 | **Quyết định PO còn treo:** config mặc định `-X`; Gate cho S2; phân công S1 | Không bắt đầu được S1/S2 | Tất cả | PO |
| S6 | Tuần 7–10 (hiệu chỉnh ngưỡng, đo test, GuardDog, báo cáo, demo) | — | — | Phụ thuộc S1–S4 |

## 2. Cách gỡ từng điểm

### S5 — PO quyết trước (09/11, khoảng 15 phút)

| Quyết định | Đề xuất của Claude | Lý do |
| --- | --- | --- |
| Q1. Nguồn mẫu độc (S2) chạy ở đâu? | **Container Docker dùng một lần** (phương án B ở S2) | Máy Triết đã có Docker; không cần cài VM; Claude tự chạy được; cùng mức cách ly với `triage_candidates`/`review_evidence` đã dùng |
| Q2. Ai kiểm tra chéo? | **Cả 3 người**, kể cả Triết | Quy tắc chỉ cấm người *soạn* nhãn (Claude/Codex) tự kiểm; Triết là người khác người soạn, nên được kiểm. Thêm 1 người rút thời gian ~1/3 |
| Q3. Config mặc định | Giữ `A-*`; đo chính thức bằng `A-*-X` | `-X` tốt hơn ở A-SLM/A-TLM, ngang ở A-LLM; giữ `A-*` làm mốc so sánh |
| Q4. Khi hết 19/11 mà chưa đủ 400 | Đóng băng với số thật, ghi rõ trong báo cáo | Không hạ chuẩn kiểm tra để đủ số |

### S1 — Kiểm tra chéo (09/11 → 18/11)

**Khối lượng hiện có và sắp có:**

| Lượt | Nội dung | Dòng | Phút/dòng | Người |
| --- | --- | --- | --- | --- |
| W5-10 lượt 1, 4 | 20 lành + 20 độc cũ | 40 | 3 | Phước |
| W5-10 lượt 2, 3 | 2 chiến dịch độc cũ | 36 | 2 | Thiên |
| Lượt 5 | 40 lành nháp (nhóm A) | 40 | 2 | Triết |
| Lượt 6–7 (S3) | 80 lành nháp (nhóm A còn lại + nhóm B đã đọc) | 80 | 3 | Thiên, Triết |
| Lượt 8–12 (S2/S4) | ~200 độc từ Datadog (≤ 12/cụm) | 200 | 2 | Phước, Thiên |
| **Tổng** | | **~396** | | ≈ **17 giờ người**, ~6 giờ/người |

**Lịch đề xuất (mỗi người 3 buổi × 2 giờ):**

| Ngày | Phước | Thiên | Triết |
| --- | --- | --- | --- |
| 09–10/11 | W5-10 lượt 1, 4 | W5-10 lượt 2, 3 | Lượt 5; quyết S5 |
| 12–14/11 | Lượt độc 8–9 | Lượt 6 | Lượt 7 |
| 15–17/11 | Lượt độc 10–11 | Lượt độc 12 | Xử lý `revise`/`exclude` |
| 18/11 | — | — | `review_sheet check` cả lượt; `data_report` |

**Cách làm cho nhanh:** mỗi buổi chỉ làm một lượt cùng loại; làm ngay trên máy Triết (bằng chứng chỉ có ở đó); không chắc thì `exclude` kèm `note`. Hướng dẫn: [phiếu W5-10](../giao-viec/W5-10_KIEM_TRA_CHEO_NHAN.md).

**Kiểm soát:** sau mỗi buổi chạy `py -3.14 -m data.scripts.data_report`; Claude cập nhật số vào nhật ký tuần 6.

### S2 — Nguồn mẫu độc

| | Phương án A: VM | Phương án B: container dùng một lần (đề xuất) |
| --- | --- | --- |
| Cài đặt | VMware Workstation Pro hoặc VirtualBox + Ubuntu 24.04 (~1–2 giờ) | Không cần; Docker đã có |
| Ai chạy | Thiên, theo [phiếu D-5](../giao-viec/D_DU_LIEU_DATADOG_VM.md) | Claude |
| Cách ly | Máy ảo riêng; tắt thư mục chia sẻ; snapshot | `--read-only`, tmpfs `noexec`, `cap-drop ALL`, user thường, container bị xóa ngay; ZIP chỉ nằm trong bộ nhớ container |
| Mã gói có chạy? | Không (chỉ đọc ZIP) | Không (chỉ đọc ZIP) |
| Thời gian | 1 buổi | ~1 giờ máy chạy |
| Cần | Thiên có thời gian | **Gate mới** (AGENTS/Gate hiện ghi "chỉ trong VM") |

**Việc của Claude nếu chọn B (10–11/11):**
1. Thêm chế độ `--container` cho `filter_datadog.py`: container clone repo Datadog ở bản cố định (ghi commit), lọc, chỉ trả về CSV metadata `name, version, hooks, sha256, cluster, archive`; không ZIP nào ra ổ đĩa Windows.
2. Test với ZIP giả có mật khẩu; chạy thật; ghi số `scanned/matching/written` vào nhật ký.

**Nếu chọn A:** Thiên làm theo phiếu D-5 trước 12/11; Claude chờ CSV.

### S4 — D-6: đề xuất mẫu độc (Claude, ngay khi có CSV, 1 ngày)

1. `propose_labels --datadog data/datadog-candidates.csv`: tạo dòng `malicious` với `source` = URL ZIP của Datadog, cụm theo `cluster`, tối đa 12/cụm, ưu tiên cụm có hành vi khác nhau.
2. Xác định file và dòng cần trích bằng container (như `triage_candidates`, đọc ZIP của Datadog), để bằng chứng không bị "dòng ngoài file".
3. Chia thành lượt 40 dòng (lượt 8–12); sinh bằng chứng bằng `review_evidence`.
4. DoD: ≥ 30 cụm độc mới; `review_evidence` không báo vấn đề hoặc mọi vấn đề được ghi rõ.

### S3 — Đủ gói lành (Claude, 09–12/11)

1. **Lượt 6:** đề xuất 40 gói nhóm A tiếp theo (`propose_labels 6`).
2. **Nhóm B:** Claude đọc mã tĩnh các gói nhóm B có dấu hiệu nhẹ (chỉ `child_process` để build, tải binary có checksum, gọi registry) và đề xuất nhãn kèm `file:dòng` thật thay vì "1-150"; gói nào có dấu hiệu nặng (luồng secret → mạng, mã làm rối) đề xuất `suspicious` hoặc loại. Thêm chế độ `propose_labels --group B --from-review <file>` để nhận các đề xuất đã đọc này. Mục tiêu ~60 dòng → lượt 7 (và lượt 6 phần dư).
3. **Nhóm C quá lớn (29 gói):** nâng giới hạn giải nén cho triage (50 MB/2000 file → 200 MB/10000 file, vẫn trong tmpfs container) và chạy lại riêng các gói này.
4. DoD: ≥ 200 dòng lành đề xuất sau lọc trùng (đủ dư để sau khi loại vẫn ≥ 180).

### S6 — Sau khi đóng băng (19/11 →)

| Ngày | Việc | Người |
| --- | --- | --- |
| 19/11 | `dedupe_labels --output`, `prepare_labels` chia dev/test theo cụm, tag Git `labels-v1` | Triết, Claude |
| 20–23/11 (tuần 7) | Chạy 3 model `-X` trên dev; quét ngưỡng 0,50–0,95; `calibration`; chọn và **đóng băng** ngưỡng | Claude, Triết duyệt |
| 24–27/11 (tuần 8) | Chạy test một lần; `metrics`; GuardDog trong container; bảng so sánh | Claude, Thiên |
| tuần 9–10 | Báo cáo, phân tích lỗi, demo 3 ca | Cả nhóm |

## 3. Rủi ro và phương án dự phòng

| Rủi ro | Dấu hiệu sớm | Dự phòng |
| --- | --- | --- |
| Người kiểm tra không đủ giờ | 12/11 chưa xong W5-10 | Giảm chỉ tiêu xuống ≥ 300 (vẫn ≥ 120 lành, ≥ 120 độc) và ghi rõ; không bỏ kiểm tra chéo |
| Không chọn được S2 trước 10/11 | Chưa có quyết định Q1 | Claude làm S3 trước; S2 dời, lượt độc rút còn 3 |
| Datadog thiếu cụm có hook | `written` < 30 | Bổ sung từ OSV `MAL-*` có link tarball còn tồn tại (đọc trong container) |
| Gói "lành" thực ra độc | Người kiểm tra ghi `revise` sang độc | Giữ đúng nhãn sau kiểm tra; báo cáo số ca này như một phát hiện |
| Rò rỉ dev → test | `dedupe_labels` báo `leaking_clusters > 0` | Chia lại theo cụm trước khi đóng băng |

## 4. Việc không tắc, để sau

B2 (bảng luồng), C3 (mạng sinkhole), C5 (chạy sandbox 2 lần), `typosquat_check`: không ảnh hưởng mốc 19/11; chỉ làm nếu còn thời gian sau tuần 8 và có Gate.
