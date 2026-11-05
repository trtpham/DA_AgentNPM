# Thư viện bên thứ ba (chép vào repo, không dùng CDN khi chạy)

Nguồn: `https://cdn.jsdelivr.net/npm/three@0.170.0/` · tải ngày 05/11/2026 · giấy phép MIT (`LICENSE`).
Được PO duyệt trong `docs/brownfield/TRANSITION_APPROVAL.md` (Gate văn phòng 3D, 05/11/2026).

| File | Đường dẫn gốc | SHA-256 bản gốc | Đã sửa |
| --- | --- | --- | --- |
| `three.module.min.js` | `build/three.module.min.js` | `08fd7545d13d2c7fb65ab691530a802dafefd638596501854f267d0fb13c39e7` | Không |
| `OrbitControls.js` | `examples/jsm/controls/OrbitControls.js` | `80efaadea4f8a636a65fb0bd08bfef62f3d93a0bb94e2e7500f23176c5c07f4e` | Dòng 12: `from 'three'` → `from './three.module.min.js'`. SHA-256 sau sửa: `0879a94d7f153c81652b0f20d96783c430a521a68d7a5234d9b9cc31293972b9` |
| `LICENSE` | `LICENSE` | `4c40a1ef62450b857c3b2aaf294936304cd552d965fbcd9d32d4c5bcf4ba4454` | Không |

Lý do sửa `OrbitControls.js`: viewer gửi CSP `default-src 'self'`, chặn import map nội tuyến, nên đường dẫn `'three'` phải trỏ thẳng tới file cùng thư mục.
