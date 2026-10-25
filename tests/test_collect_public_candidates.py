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
