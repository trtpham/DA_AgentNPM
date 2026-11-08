# Dữ liệu

Thư mục `data/` chỉ chứa dữ liệu. Script nằm trong `data/scripts/`, chạy bằng `py -3.14 -m data.scripts.<tên>`. `data/samples/` (mẫu độc thật) bị Git bỏ qua và chỉ mở trong môi trường cách ly.

## File chính (đang dùng)

| Đường dẫn | Vai trò | Ai sửa |
| --- | --- | --- |
| `labels.csv` | Bảng nhãn gốc, 76 dòng (20 lành, 2 nghi vấn, 54 độc) | Chỉ sửa khi người kiểm tra đã ký |
| `proposals.csv` | 440 nhãn nháp do Claude soạn (lượt 5–15), **chưa dùng để đo** | `propose_labels` |
| `review_rounds/round-N.csv` | 15 phiếu kiểm tra chéo, người thật điền `verified / revise / exclude` | Người được phân công |
| `review_rounds/ai-precheck/` | Ô kiểm tự động cho từng lượt (gợi ý, không phải chữ ký) | `ai_precheck` |
| `review_450/triage_450.csv` | Phân loại sơ bộ 450 gói công khai: nhóm A, B, C | `triage_candidates` |
| `datadog/candidates-batch-*.jsonl` | Metadata mẫu độc lấy từ bộ Datadog (không có mã) | `datadog_container` |

Sau ngày 19/11 sẽ có thêm `labels-v1.csv`: bản đóng băng, chỉ gồm dòng đã `verified`. Đây sẽ là file duy nhất dùng để tính chỉ số.

## File phụ (giữ để tra cứu)

| Đường dẫn | Vì sao còn giữ |
| --- | --- |
| `review_rounds/REVIEW_WEEK2.md` | Hồ sơ bằng chứng của 76 nhãn đầu (tuần 2) |
| `review_450/public_candidates_450.csv` | Danh sách gốc 450 gói, đầu vào của bước phân loại |
| `review_450/metadata_review_450.csv` | Kết quả đối chiếu manifest tuần 2 (445 khớp, 5 lỗi 404) |
| `review_450/triage/` | Kết quả phân loại theo từng batch, để chạy tiếp khi bị ngắt |

File cũ hơn đã chuyển vào `archive/data/` (chỉ trên máy).

## Quy trình

```powershell
py -3.14 -m data.scripts.triage_candidates                 # 1. phân loại 450 gói (trong container)
py -3.14 -m data.scripts.propose_labels 5 --limit 40       # 2. soạn nhãn nháp cho một lượt
py -3.14 -m data.scripts.review_evidence 5 --labels data/proposals.csv   # 3. trang bằng chứng HTML
py -3.14 -m data.scripts.ai_precheck 5                     # 4. ô kiểm tự động
py -3.14 -m data.scripts.review_sheet check data/review_rounds/round-5.csv   # 5. kiểm phiếu đã điền
py -3.14 -m data.scripts.dedupe_labels --report reports/dedupe.json         # 6. lọc trùng
py -3.14 -m data.scripts.data_report                       # 7. đã đủ chỉ tiêu chưa
py -3.14 -m data.scripts.freeze_labels --output data/labels-v1.csv          # 8. đóng băng (19/11)
```

Mẫu độc: `datadog_container --zips 800`, rồi `propose_labels 10 --limit 40 --datadog`. Repo Datadog ghim ở commit `72c723be547033c558244520524b117c8d71663b`.

## Script

| Script | Việc |
| --- | --- |
| `triage_candidates` | Tải, kiểm sha512, đọc tĩnh 450 gói trong container; chia nhóm A/B/C |
| `datadog_container` | Đọc ZIP Datadog trong container, chỉ ghi metadata |
| `propose_labels` | Soạn nhãn nháp và tạo phiếu một lượt |
| `review_evidence` | Trích đoạn mã được dẫn ra trang HTML (mã hóa để antivirus không chặn) |
| `ai_precheck` | So đoạn trích với nhãn nháp: `khớp / cần xem / nghi ngờ` |
| `review_sheet` | Tạo và kiểm phiếu kiểm tra chéo |
| `dedupe_labels` | Lọc trùng theo tên, hash tarball, hash mã cài đặt; trần 12 dòng mỗi cụm |
| `data_report` | So bộ nhãn với chỉ tiêu v1 (≥ 400 mẫu, ≥ 180 lành, ≥ 180 độc, ≥ 40 cụm) |
| `freeze_labels` | Ghi `labels-v1.csv`, chia dev/test theo cụm |
| `prepare_labels` | Chia dev/test cho một bảng nhãn bất kỳ |
| `collect_public_candidates`, `review_public_candidates`, `review_batches` | Thu thập và đối chiếu metadata 450 gói (tuần 2) |
| `filter_datadog` | Bản đọc Datadog cho máy ảo (tuần 2); nay dùng `datadog_container` |

## Lưu ý

- Nhóm A/B/C **không phải nhãn**. Nhóm A chỉ nghĩa là công cụ tĩnh không thấy dấu hiệu.
- Nhãn nháp và ô kiểm tự động không bao giờ thay chữ ký của người kiểm tra.
- Không chạy nội dung cột `hook_commands`: đó là văn bản không tin cậy của nhà phát hành gói.
- Phân công kiểm tra: PHAN_CONG_KIEM_TRA_CHEO.md. Kế hoạch dữ liệu: KE_HOACH_DU_LIEU_400.md.
