"""The standalone report contains only escaped trace summaries."""

from tools.visualize_agent import render


def test_visualizer_escapes_untrusted_package_text():
    page = render("A-SLM", "qwen3.5:4b", [
        {"step": 0, "kind": "manifest", "status": "ok", "detail": '<script>alert(1)</script>'},
        {"step": 1, "kind": "tool", "status": "error", "detail": '<img src=x onerror=alert(1)>'},
    ], error="No valid verdict")

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "&lt;img src=x onerror=alert(1)&gt;" in page
    assert "<script>" not in page
    assert "<img src=x" not in page
    assert "No valid verdict" in page
