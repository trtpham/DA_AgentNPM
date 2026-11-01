import pytest

from data import collect_public_candidates as collector


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
    from data.review_public_candidates import review_row

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
    from data.review_public_candidates import review_row

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
