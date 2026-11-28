import io
import json
import tarfile
import zipfile
from subprocess import CompletedProcess

import pytest

from data.scripts import datadog_container as dd


def tgz(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, body in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
    return buffer.getvalue()


def dataset_zip(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.writestr("demo-1.0.0.tgz", tgz(files))
    return buffer.getvalue()


PACKAGE = {"package/package.json": json.dumps({"name": "demo", "version": "1.0.0",
                                               "scripts": {"postinstall": "node i.js"}}).encode(),
           "package/i.js": b"console.log(1);\n"}


def test_inspect_reads_metadata_and_triage(monkeypatch, tmp_path):
    monkeypatch.setattr(dd, "_get", lambda url, limit=0: dataset_zip(PACKAGE))
    result = dd.inspect("demo/1.0.0/2025-01-01-demo-v1.0.0.zip", tmp_path / "work")
    assert (result["name"], result["version"], result["has_hook"]) == ("demo", "1.0.0", True)
    assert result["entries"] == [{"hook": "postinstall", "file": "i.js", "lines": 1}]
    assert result["archive"].startswith(dd.RAW) and len(result["install_hash"]) == 64
    assert not (tmp_path / "work").exists()


def test_scoped_name_and_bad_archives_are_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(dd, "_get", lambda url, limit=0: b"not a zip")
    result = dd.inspect("@s/pkg/2.0.0/x.zip", tmp_path / "work")
    assert (result["name"], result["version"]) == ("@s/pkg", "2.0.0") and "BadZipFile" in result["error"]
    monkeypatch.setattr(dd, "_get", lambda url, limit=0: dataset_zip({**PACKAGE, "package/../x": b"1"}))
    assert "unsafe tar path" in dd.inspect("demo/1.0.0/x.zip", tmp_path / "work")["error"]


def test_hosts_sample_and_container_flags():
    with pytest.raises(ValueError):
        dd._get("https://example.invalid/x.zip")
    paths = [f"p{i}/1.0.0/x.zip" for i in range(50)]
    assert dd.sample(paths, 10) == dd.sample(paths, 10) and len(set(dd.sample(paths, 10))) == 10
    command = dd.container_command()
    assert "--read-only" in command and "ALL" in command and "node" not in command
    assert all(part.endswith(",readonly") for part in command if part.startswith("type=bind"))


def test_batches_resume(tmp_path):
    calls = []

    def runner(command, input, **_kwargs):
        calls.append(1)
        return CompletedProcess(command, 0, "\n".join(json.dumps({"path": line}) for line in input.splitlines()), "")

    assert dd.run_batch(1, ["a", "b"], tmp_path, runner) is not None
    assert dd.run_batch(1, ["a", "b"], tmp_path, runner) is None and len(calls) == 1


def plain_zip(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        for name, body in files.items():
            zipped.writestr(name, body)
    return buffer.getvalue()


def test_zip_with_package_files_directly(monkeypatch, tmp_path):
    files = {f"demo-1.0.0/{name}": body for name, body in PACKAGE.items()}
    monkeypatch.setattr(dd, "_get", lambda url, limit=0: plain_zip(files))
    result = dd.inspect("demo/1.0.0/x.zip", tmp_path / "work")
    assert result.get("error") is None and result["entries"][0]["file"] == "i.js"
    monkeypatch.setattr(dd, "_get", lambda url, limit=0: plain_zip({**files, "demo-1.0.0/package/../../evil": b"x"}))
    assert "unsafe zip path" in dd.inspect("demo/1.0.0/x.zip", tmp_path / "work")["error"]
    monkeypatch.setattr(dd, "_get", lambda url, limit=0: plain_zip({"readme.txt": b"x"}))
    assert "no package.json" in dd.inspect("demo/1.0.0/x.zip", tmp_path / "work")["error"]


def test_sample_since_skip_and_tagged_batches(tmp_path):
    assert dd.sample_date("pkg/1.0.0/2025-02-14-pkg-v1.0.0.zip") == "2025-02-14"
    assert dd.sample_date("pkg/1.0.0/no-date.zip") == ""

    paths = [
        "old/1.0.0/2024-12-31-old-v1.0.0.zip",
        "seen/1.0.0/2025-03-01-seen-v1.0.0.zip",
        "new1/1.0.0/2025-01-01-new1-v1.0.0.zip",
        "new2/1.0.0/2026-02-12-new2-v1.0.0.zip",
        "nodate/1.0.0/nodate.zip",
    ]
    picked = dd.sample(paths, count=10, seed=1, since="2025-01-01", skip=frozenset({paths[1]}))
    assert set(picked) == {paths[2], paths[3]}

    def runner(command, input, **_kwargs):
        return CompletedProcess(command, 0, "\n".join(json.dumps({"path": line}) for line in input.splitlines()), "")

    out = dd.run_batch(1, [paths[2], paths[3]], out_dir=tmp_path, runner=runner, tag="v2")
    assert out == tmp_path / "candidates-v2-batch-001.jsonl"
    assert dd.run_batch(1, [paths[2], paths[3]], out_dir=tmp_path, runner=runner, tag="v2") is None
    (tmp_path / "candidates-batch-001.jsonl").write_text(json.dumps({"path": paths[1]}) + "\n", encoding="utf-8")
    assert dd.inspected_tag("v2", tmp_path) == frozenset({paths[2], paths[3]})
    assert dd.inspected(tmp_path) == frozenset({paths[1], paths[2], paths[3]})
