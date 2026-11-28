import pytest

from data.scripts import collect_public_candidates as collector


def test_manifest_records_only_hook_names_and_exact_source(monkeypatch):
    def metadata(path):
        assert path == "/%40scope%2Fpkg/1.2.3"
        return {"name": "@scope/pkg", "version": "1.2.3",
                "scripts": {"postinstall": "do-not-execute-or-export-this"}}

    monkeypatch.setattr(collector, "get_json", metadata)
    row = collector.manifest(("@scope/pkg", "1.2.3", "postinstall"))
    assert row["install_hook"] == "postinstall"
    assert "do-not-execute-or-export-this" not in str(row)
    assert row["source_label"] == "unlabeled"


def test_registry_request_rejects_non_path_url():
    with pytest.raises(ValueError, match="registry path required"):
        collector.get_json("//other.example.invalid/private")


def test_metadata_review_checks_scoped_hook_without_assigning_label():
    from data.scripts.review_public_candidates import review_row

    row = {"package": "@scope/example", "version": "1.2.3", "source_label": "unlabeled",
           "install_hook": "postinstall", "source_url": "https://registry.npmjs.org/%40scope%2Fexample/1.2.3",
           "review_status": "needs_independent_review", "search_term": "postinstall", "observed_at": "2026-10-25"}
    calls = []

    def fetch(path):
        calls.append(path)
        return {"name": "@scope/example", "version": "1.2.3",
                "scripts": {"postinstall": "node install.js"}, "dist": {"integrity": "sha512-example"}}

    reviewed = review_row(row, fetch)
    assert calls == ["/%40scope%2Fexample/1.2.3"]
    assert reviewed["metadata_status"] == "verified"
    assert reviewed["integrity_present"] == "yes"
    assert reviewed["label_decision"] == "needs_code_review"
    assert reviewed["hook_commands"] == '{"postinstall": "node install.js"}'
    assert reviewed["source_label"] == "unlabeled"

    row["source_url"] = "https://example.invalid/private"
    assert review_row(row, fetch)["metadata_status"] == "invalid_input"
    assert len(calls) == 1


def test_metadata_review_reports_changed_or_unavailable_manifest():
    from data.scripts.review_public_candidates import review_row

    row = {"package": "example", "version": "1.2.3", "source_label": "unlabeled",
           "install_hook": "postinstall", "source_url": "https://registry.npmjs.org/example/1.2.3",
           "review_status": "needs_independent_review", "search_term": "postinstall", "observed_at": "2026-10-25"}
    changed = review_row(row, lambda path: {"name": "example", "version": "1.2.3",
                                            "scripts": {"preinstall": "node x.js"}})
    assert changed["metadata_status"] == "mismatch"
    assert changed["metadata_detail"] == "hook_changed"

    def missing(path):
        raise ValueError("registry HTTP 404")

    assert review_row(row, missing)["metadata_status"] == "unavailable"


def test_popular_candidates_filters_sorts_and_writes_downloads(monkeypatch, tmp_path):
    def fake_search(path):
        if "text=a" in path:
            return {"objects": [
                {"package": {"name": "seen-pkg", "version": "1.0.0"}, "downloads": {"monthly": 999999}},
                {"package": {"name": "pre-pkg", "version": "1.0.0-rc.1"}, "downloads": {"monthly": 50000}},
                {"package": {"name": "small-pkg", "version": "1.0.0"}, "downloads": {"monthly": 500}},
                {"package": {"name": "sharp", "version": "0.33.5"}, "downloads": {"monthly": 200000}},
                {"package": {"name": "esbuild", "version": "0.24.0"}, "downloads": {"monthly": 500000}},
            ]}
        return {"objects": [
            {"package": {"name": "esbuild", "version": "0.24.0"}, "downloads": {"monthly": 500000}},
            {"package": {"name": "@scope/native", "version": "2.1.0"}, "downloads": {"monthly": 300000}},
        ]}

    found = collector.popular_candidates(fake_search, ("a", "b"), min_monthly=20000, seen={"seen-pkg"}, pages=1)
    assert [(p, m) for p, _, _, m in found] == [("esbuild", 500000), ("@scope/native", 300000), ("sharp", 200000)]

    def fake_get_json(path):
        if path.startswith("/-/v1/search"):
            return fake_search(path)
        if path == "/esbuild/0.24.0":
            return {"name": "esbuild", "version": "0.24.0", "scripts": {"postinstall": "node install.js"}}
        if path == "/%40scope%2Fnative/2.1.0":
            return {"name": "@scope/native", "version": "2.1.0", "scripts": {}}  # no install hook -> skipped
        if path == "/sharp/0.33.5":
            return {"name": "sharp", "version": "0.33.5", "scripts": {"install": "node install/check.js"}}
        raise ValueError(f"unexpected {path}")

    monkeypatch.setattr(collector, "get_json", fake_get_json)
    out = tmp_path / "review_v2" / "public_candidates_v2.csv"
    collector.collect_popular(out, target=2, terms=("a", "b"), min_monthly=20000, seen={"seen-pkg"})
    assert out.is_file()
    dl = tmp_path / "review_v2" / "downloads_v2.csv"
    assert dl.is_file()
    lines = dl.read_text(encoding="utf-8").splitlines()
    assert lines == ["package,version,monthly_downloads", "esbuild,0.24.0,500000", "sharp,0.33.5,200000"]
