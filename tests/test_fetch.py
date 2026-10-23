import io
import json
import tarfile
from subprocess import CompletedProcess
from unittest.mock import patch

from tools.fetch import fetch_package


def test_fetch_uses_pack_without_scripts_and_rejects_traversal(tmp_path):
    def fake_run(command, **kwargs):
        assert command[:4] == ["npm", "pack", "example@1.0.0", "--ignore-scripts"]
        tarball = tmp_path / "example-1.0.0.tgz"
        with tarfile.open(tarball, "w:gz") as archive:
            payload = b"{}"
            item = tarfile.TarInfo("package/../../escape.json")
            item.size = len(payload)
            archive.addfile(item, io.BytesIO(payload))
        assert (kwargs["capture_output"], kwargs["timeout"], kwargs["check"]) == (True, 120, True)
        destination = command[-1]
        import shutil
        shutil.copyfile(tarball, f"{destination}/example-1.0.0.tgz")
        return CompletedProcess(command, 0, json.dumps([{"filename": "example-1.0.0.tgz"}]), "")

    download = tmp_path / "download"
    download.mkdir()
    with patch("tools.fetch.tempfile.mkdtemp", return_value=str(download)), patch("tools.fetch.subprocess.run", side_effect=fake_run):
        result = fetch_package("example", "1.0.0")
    assert result["ok"] is False
    assert "unsafe tar path" in result["error"]


def test_fetch_rejects_package_spec_injection():
    assert not fetch_package("example --script-shell=sh", "1.0.0")["ok"]


def test_extract_rejects_windows_separator_and_links(tmp_path):
    from tools.fetch import _extract

    for name, kind in (("package/..\\escape", tarfile.REGTYPE), ("package/C:/escape", tarfile.REGTYPE),
                       ("package/link", tarfile.SYMTYPE)):
        archive_path = tmp_path / "bad.tgz"
        with tarfile.open(archive_path, "w:gz") as archive:
            item = tarfile.TarInfo(name)
            item.type = kind
            if kind == tarfile.SYMTYPE:
                item.linkname = "../../outside"
                archive.addfile(item)
            else:
                item.size = 1
                archive.addfile(item, io.BytesIO(b"x"))
        import pytest
        with pytest.raises(ValueError):
            _extract(archive_path, tmp_path / "out")


def test_extract_regular_package(tmp_path):
    from tools.fetch import _extract

    archive_path = tmp_path / "good.tgz"
    with tarfile.open(archive_path, "w:gz") as archive:
        item = tarfile.TarInfo("package/package.json")
        item.size = 2
        archive.addfile(item, io.BytesIO(b"{}"))
    assert _extract(archive_path, tmp_path / "out") == ["package.json"]
    assert (tmp_path / "out" / "package.json").read_text() == "{}"
