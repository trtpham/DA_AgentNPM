# Hồ sơ kiểm tra nhãn tuần 2

Trạng thái: **chờ TV2 (Phạm Minh Triết) kiểm tra chéo và xác nhận từng dòng**. Các nhãn dưới đây là đề xuất, chưa phải ground truth. Không chạy mã gói trên host và không tải gói độc vào repo.

| Ứng viên | Nhãn đề xuất | Bằng chứng install hook và hành vi | Nguồn | TV2 |
| --- | --- | --- | --- | --- |
| `greensaver@1.2.3` | malicious | Báo cáo nguồn ghi `postinstall: node lib/greensaver.js`; script giải mã các file giả sourcemap, tải blob mã hóa và đưa mã sau giải mã vào `eval`. Gói đã bị gỡ khỏi npm; chưa đối chiếu được tarball. | [GHSA-jfw2-6254-9cwg](https://github.com/advisories/GHSA-jfw2-6254-9cwg), [OSV MAL-2026-16138](https://github.com/ossf/malicious-packages/blob/f128a26926ba435054707f5af00821644544b030/osv/malicious/npm/greensaver/MAL-2026-16138.json) | Chưa duyệt |
| `merge-grid-stats@1.5.0` | malicious | Báo cáo nguồn ghi `postinstall: node install-cb.js`; script khảo sát container và đọc token service account, biến môi trường có tên liên quan bí mật. Gói đã bị gỡ khỏi npm; chưa đối chiếu được tarball. | [GHSA-vqp7-j6jf-34qm](https://github.com/advisories/GHSA-vqp7-j6jf-34qm), [OSV MAL-2026-13484](https://github.com/ossf/malicious-packages/blob/f8d6dbca88029f7084e1904bf07393368dc9681e/osv/malicious/npm/merge-grid-stats/MAL-2026-13484.json) | Chưa duyệt |
| `carbon-monorepo@20.1.1` | malicious | Báo cáo nguồn ghi `postinstall` chạy `index.js`; đọc môi trường, `.npmrc` và log npm rồi gửi qua HTTP. Gói đã bị gỡ khỏi npm; chưa đối chiếu được tarball. | [GHSA-qqpg-vxw2-32f8](https://github.com/advisories/GHSA-qqpg-vxw2-32f8), [OSV MAL-2026-14229](https://github.com/ossf/malicious-packages/blob/4f8382c22379fc0093ad418cb40f30e203d946ed/osv/malicious/npm/carbon-monorepo/MAL-2026-14229.json) | Chưa duyệt |
| `esbuild@0.24.0` | benign | Registry và manifest chính thức ghi `postinstall: node install.js`. Đã đọc tĩnh tarball phát hành: `install.js:253-284` tìm binary theo nền tảng, khi thiếu thì lấy đúng phiên bản từ npm registry và kiểm tra phiên bản binary. Đây là tác vụ cài binary của trình bundler; **có tải và chạy binary**. | [manifest bản phát hành](https://github.com/evanw/esbuild/blob/v0.24.0/npm/esbuild/package.json), [tài liệu cài đặt](https://esbuild.github.io/getting-started/) | Chưa duyệt |
| `@swc/core@1.7.36` | benign | Registry ghi `postinstall: node postinstall.js`. Đã đọc tĩnh tarball phát hành: `postinstall.js:88-128` kiểm tra native binding; khi thiếu thử cài `@swc/wasm` cùng phiên bản. Đây là đường dự phòng của compiler; **có thể gọi npm install trong install hook**. | [trang bản phát hành](https://www.npmjs.com/package/@swc/core/v/1.7.36), [repo chính thức](https://github.com/swc-project/swc) | Chưa duyệt |

Hai tarball lành được tải bằng `npm pack --ignore-scripts`, chỉ đọc tĩnh trong thư mục tạm bị ignore. SHA-512 của từng tarball khớp `dist.integrity` từ npm registry: `esbuild@0.24.0` = `sha512-FuLPevChGDshgSicjisSooU0cemp/sGXR841D5LHMB7mTVOmsEHcAxaH3irL53+8YDIeVNQEySh4DaYU/iuPqQ==`; `@swc/core@1.7.36` = `sha512-bu7ymMX+LCJOSSrKank25Jaq66ymLVA9fOUuy4ck3/6rbXdLw+pIJPnIDKQ9uNcxww8KDxOuJk9Ui9pqR+aGFw==`. Không thực thi hook.

Ba nguồn malware đều bắt nguồn từ Amazon Inspector qua GitHub Advisory/OSV; hai URL cho cùng gói không phải hai kiểm tra độc lập. `npm view` trả E404/unpublished cho cả ba. Để nhập nhãn malicious theo hợp đồng có `file,lines`, TV2 cần bằng chứng dòng từ bản sao an toàn trong VM hoặc nguồn công khai đáng tin cậy có đánh số dòng. Nếu không lấy được, ghi `không xác minh được` và giữ ứng viên ngoài `labels.csv`.

Nếu cả năm đề xuất được duyệt, quy tắc split hiện tại cho 4 gói vào `dev` và chỉ `@swc/core` vào `test`; tập test chưa có gói malicious. Cần thêm nhãn đã kiểm tra thuộc tập test trước khi dùng tập này để báo cáo recall/F1.

## Việc TV2 cần ghi cho từng ứng viên

1. Xác minh `name@version`, lifecycle hook, mục đích và hành vi bằng nguồn độc lập hoặc phân tích tĩnh trong VM.
2. Ghi đường dẫn file, dòng bằng chứng, nhãn cuối (`malicious`/`suspicious`/`benign`), nguồn và lý do. Với gói lành, xác nhận hành vi cài binary có giới hạn đúng gói/phiên bản.
3. Điền tên người kiểm tra và ngày vào đây; sau đó TV1 mới đưa dòng đạt chuẩn vào `labels.csv` và chạy `prepare_labels`.

| Ứng viên | File:dòng đã xác minh | Nhãn TV2 | Lý do/nguồn độc lập | Người kiểm tra/ngày |
| --- | --- | --- | --- | --- |
| `greensaver@1.2.3` | | | | |
| `merge-grid-stats@1.5.0` | | | | |
| `carbon-monorepo@20.1.1` | | | | |
| `esbuild@0.24.0` | | | | |
| `@swc/core@1.7.36` | | | | |
