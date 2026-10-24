"""The standalone report contains only escaped trace summaries."""

from tools.visualize_agent import render


def test_visualizer_escapes_untrusted_package_text():
    page = render("A-SLM", "qwen3.5:4b", [
        {"step": 0, "kind": "manifest", "status": "ok", "detail": '<script>alert(1)</script>'},
        {"step": 1, "kind": "tool", "status": "error", "detail": '<img src=x onerror=alert(1)>',
         "what": "Đọc postinstall.js", "how": "Chỉ đọc file", "found": "Không thực thi mã",
         "sources": [{"file": "postinstall.js", "start": 7,
                      "content": '<img src=x onerror=alert(1)>', "truncated": False,
                      "behavior": "Đọc file", "claim": '<script>alert(2)</script>'}]},
    ], error="No valid verdict")

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "&lt;img src=x onerror=alert(1)&gt;" in page
    assert "<script>alert(1)</script>" not in page
    assert "<img src=x" not in page
    assert "No valid verdict" in page
    assert 'id="transport"' in page
    assert 'id="step-inspector"' in page
    assert '   7 │ &lt;img src=x onerror=alert(1)&gt;' in page
    assert 'Dữ liệu mã gói không tin cậy' in page
    assert '&lt;script&gt;alert(2)&lt;/script&gt;' in page
    assert 'Hiện thêm đoạn mã' in page
    assert "Bốn giai đoạn kiểm tra" in page
    assert "prefers-reduced-motion" in page
    assert "innerHTML" not in page
