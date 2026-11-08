# Kế hoạch đồ án: AI Agent kiểm tra install script của gói npm

Thời lượng: 10 tuần. Phạm vi trước mắt là các task TV1-1 đến TV3-5 trong tài liệu hướng dẫn; các mục mở rộng của bản DOCX chỉ làm sau khi lõi chạy ổn định. Mỗi task có một người thực hiện và một người kiểm tra chéo.

| Giai đoạn | Thời gian | Việc chính | Mốc nghiệm thu |
| --- | --- | --- | --- |
| 0. Chốt nền tảng | Tuần 1 | Tạo repo, khóa phiên bản Python/Node/npm/Ollama và ba tag model; chốt hợp đồng JSON và phân quyền chỉ `tools/actions.py` được ghi `package.json`. Thử tool calling 20 lượt/model bằng công cụ giả (TV2-1). | Repo và `.gitignore` không nhận `data/samples/`, `*.tgz`, `sandbox/out/`; `pytest` chạy; có bảng tỉ lệ tool call/JSON hợp lệ, tốc độ và tài nguyên cho từng model. |
| 1. Dữ liệu và công cụ đọc | Tuần 2–3 | TV1-2 đến TV1-6: nhãn CSV, `npm pack`, giải nén an toàn, đọc manifest/file, trích chỉ báo chỉ từ đường chạy của install script. TV2-3: schema verdict. | Test với dữ liệu giả bao phủ path traversal, symlink, thoát thư mục gói, thiếu `scripts`, dòng đầu/cuối; công cụ trả đúng hợp đồng `ok/data/error`, nội dung gói bọc `untrusted`. |
| 2. Agent và sandbox độc lập | Tuần 2–4 | TV2-2/4/5: Ollama qua cấu hình, vòng lặp tối đa 15 bước, prompt phân tích nguồn–hành động–đích. TV3-1/2/3: sandbox Linux, `strace`, canary giả. | Agent trả verdict hợp lệ trên gói giả và tập dev nhỏ; sandbox ghi được dấu vết trên gói mô phỏng vô hại. Chưa nối sandbox vào agent trước khi kiểm tra cách ly. |
| 3. Quyết định và chạy lô | Tuần 4–6 | TV1-7/8: kiểm tra bằng chứng, luật approve/deny, mặc định dry-run; chạy lô có resume và `run_meta.json`. TV3-4: GuardDog baseline. Sau khi đạt mốc sandbox, thêm công cụ bối cảnh/động theo bản DOCX. | Bằng chứng sai không thể tự approve/deny; một gói lỗi không dừng lô; ba cấu hình dùng cùng agent, công cụ, prompt và tập dữ liệu. |
| 4. Thực nghiệm | Tuần 7–8 | TV3-5: confusion matrix, Precision/Recall/F1/FPR, tỉ lệ suspicious và JSON hợp lệ. Chuẩn bị 400–500 mẫu sau lọc trùng, tách dev/test; hiệu chỉnh ngưỡng trên dev, chốt trước khi chạy test. So A-LLM/A-SLM/A-TLM với GuardDog; kiểm tra ẩn danh hóa, bỏ tín hiệu bối cảnh và prompt injection. | Có script tái hiện, phiên bản model và cấu hình từng lượt, bảng kết quả, thời gian/gói, RAM đỉnh, lỗi JSON và ca sai. Không đưa nhãn thật vào prompt. |
| 5. Báo cáo và demo | Tuần 9–10 | Điền Chương 1–5 bằng số liệu đo được, phân tích báo nhầm/bỏ sót; chuẩn bị slide và demo ba ca: lành, độc, độc có câu lừa. | Báo cáo, mã nguồn, cấu hình và video demo tái hiện được; mọi kết luận demo có file/dòng bằng chứng và hành động đã qua luật cứng. |

## Phân công và phụ thuộc

- TV1: dữ liệu, công cụ đọc, luật quyết định và chạy lô; TV2 kiểm tra chéo.
- TV2: probe model, Ollama, schema, vòng lặp và prompt; TV3 kiểm tra chéo.
- TV3: sandbox, GuardDog và metrics; TV1 kiểm tra chéo.
- Chốt schema và hợp đồng công cụ trước khi TV1/TV2 tích hợp. Sandbox chỉ nối vào agent sau khi TV3 chứng minh cách ly và log trên gói mô phỏng. Bản hướng dẫn đính kèm là hợp đồng thực thi trước mắt; đối chiếu các khác biệt với DOCX (schema, độ dài `description`, công cụ mở rộng) trước khi code phần tương ứng.

## Ba model Ollama

| Cấu hình | Tag | Vai trò |
| --- | --- | --- |
| A-LLM | `qwen3.5:9b` | Mốc chất lượng |
| A-SLM | `qwen3.5:4b` | Cân bằng chất lượng/tốc độ |
| A-TLM | `qwen3.5:0.8b` | Mốc nhẹ nhất |

Giữ tag model trong `experiments/configs/*.yaml`, không viết cứng trong mã. Sau khi tải, ghi `ollama list` và mã định danh model vào metadata thực nghiệm; probe 20 lượt trước khi dùng tập dev. Nếu model nhỏ không gọi công cụ hoặc tạo JSON ổn định, ghi nhận tỷ lệ lỗi thay vì sửa nhãn thủ công.

## Quy tắc chạy

Không chạy mã gói npm hoặc mẫu độc trên máy thật; không mở `data/samples/`. Chỉ chạy gói mô phỏng trong VM/container cách ly, không có secret thật. Mọi hành động approve/deny mặc định dry-run; chạy thật cần yêu cầu riêng và bằng chứng đã xác minh.
