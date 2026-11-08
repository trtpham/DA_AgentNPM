import base64
import hashlib
import io
import json
import tarfile
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from data.scripts import triage_candidates as triage_module
from data.scripts.triage_candidates import container_command, inspect, run_batch, summarize, triage

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("folder, group", [
    ("corpus/twin-safe", "A"),        # writes a marker inside the package only
    ("corpus/native-gyp", "A"),       # node-gyp native build is not "code from outside"
    ("corpus/twin-evil", "B"),
    ("corpus/inline-fetch-eval", "B"),
    ("corpus/hex-obfuscated", "B"),
    ("corpus/binary-prebuilt", "B"),  # benign, but a reviewer must read the download
    ("packages/no-hook-package", "C"),
])
def test_groups_on_fixtures(folder, group):
    result = triage(str(FIXTURES / folder))
    assert result["group"] == group, result["reasons"]
    assert (result["group"] == "A") == (result["reasons"] == [])


def test_reasons_name_what_to_read():
    reasons = " | ".join(triage(str(FIXTURES / "corpus" / "twin-evil"))["reasons"])
    assert "risky indicators" in reasons and "secret/env flow" in reasons and "endpoint" in reasons


def _tgz(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, body in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
    return buffer.getvalue()


ROW = {"package": "demo", "version": "1.0.0", "source_url": "https://registry.npmjs.org/demo/1.0.0"}
PACKAGE = {"package/package.json": json.dumps({"name": "demo", "version": "1.0.0",
                                               "scripts": {"postinstall": "node setup.js"}}).encode(),
           "package/setup.js": b"console.log('built');\n"}


def _registry(monkeypatch, tarball: bytes, name: str = "demo", integrity: bytes | None = None):
    digest = base64.b64encode(hashlib.sha512(tarball if integrity is None else integrity).digest()).decode()
    meta = {"name": name, "version": "1.0.0",
            "dist": {"tarball": "https://registry.npmjs.org/demo/-/demo-1.0.0.tgz", "integrity": f"sha512-{digest}"}}
    monkeypatch.setattr(triage_module, "_download",
                        lambda url: json.dumps(meta).encode() if url.endswith("/1.0.0") else tarball)


def test_inspect_verifies_integrity_and_cleans_up(monkeypatch, tmp_path):
    tarball = _tgz(PACKAGE)
    _registry(monkeypatch, tarball)
    result = inspect(ROW, tmp_path / "work")
    assert result["group"] == "A" and result["tarball_sha256"] == hashlib.sha256(tarball).hexdigest()
    assert not (tmp_path / "work").exists()
    _registry(monkeypatch, tarball, integrity=b"other")
    assert inspect(ROW, tmp_path / "work")["reasons"] == ["ValueError: tarball does not match registry integrity"]
    _registry(monkeypatch, tarball, name="other")
    assert inspect(ROW, tmp_path / "work")["group"] == "C"


def test_inspect_rejects_path_traversal_and_other_hosts(monkeypatch, tmp_path):
    with pytest.raises(ValueError):
        triage_module._download("https://example.invalid/x.tgz")
    with pytest.raises(ValueError):
        triage_module._download("http://registry.npmjs.org/demo")
    _registry(monkeypatch, _tgz({**PACKAGE, "package/../escape.js": b"x"}))
    result = inspect(ROW, tmp_path / "work")
    assert result["group"] == "C" and "unsafe tar path" in result["reasons"][0]
    assert not (tmp_path / "escape.js").exists()


def test_container_is_disposable_read_only_and_runs_no_package_code():
    command = container_command()
    assert command[:4] == ["docker", "run", "--rm", "-i"] and "--read-only" in command
    assert "ALL" in command and "no-new-privileges" in command and "--privileged" not in command
    assert all(part.endswith(",readonly") for part in command if part.startswith("type=bind"))
    assert "npm" not in command and "node" not in command


def test_batches_resume_and_summary(tmp_path):
    rows = [ROW, {**ROW, "package": "demo2"}]
    calls = []

    def runner(command, input, **_kwargs):
        calls.append(command)
        items = [{"package": json.loads(line)["package"], "version": "1.0.0", "group": "A", "reasons": []}
                 for line in input.splitlines()]
        return CompletedProcess(command, 0, "\n".join(map(json.dumps, items)), "")

    assert run_batch(1, rows, tmp_path, runner) is not None
    assert run_batch(1, rows, tmp_path, runner) is None and len(calls) == 1  # resumed, not rerun
    with pytest.raises(RuntimeError):
        run_batch(2, rows, tmp_path, lambda command, **_: CompletedProcess(command, 0, json.dumps(ROW), ""))
    assert summarize(tmp_path, tmp_path / "summary.csv") == {"rows": 2, "groups": {"A": 2}}


def test_shell_script_and_inline_hooks_need_a_reader(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"name": "s", "version": "1.0.0",
                                                       "scripts": {"postinstall": "sh moon.sh"}}), encoding="utf-8")
    (tmp_path / "moon.sh").write_text("#!/bin/sh\nenv\n", encoding="utf-8")
    result = triage(str(tmp_path))
    assert result["group"] == "B" and "shell script on the install path: moon.sh" in result["reasons"]
    inline = triage(str(FIXTURES / "corpus" / "inline-thanks"))
    assert inline["group"] == "B" and "inline code in a lifecycle hook" in inline["reasons"]


def test_entries_point_to_where_reading_starts():
    assert triage(str(FIXTURES / "corpus" / "twin-safe"))["entries"] == [
        {"hook": "postinstall", "file": "setup.js", "lines": 5}]
    inline = triage(str(FIXTURES / "corpus" / "inline-thanks"))["entries"]
    assert inline[0]["file"] == "package.json" and isinstance(inline[0]["line"], int)
