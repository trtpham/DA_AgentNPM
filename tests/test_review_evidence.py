import io
import json
import tarfile
import zipfile

from data.scripts import review_evidence as evidence


def tgz(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, body in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
    return buffer.getvalue()


ROW = {"id": "x", "name": "demo", "version": "1.0.0", "label": "malicious", "file": "index.js", "lines": "2,4-5",
       "source": "https://raw.githubusercontent.com/example/sample.zip"}
FILES = {"package/package.json": json.dumps({"name": "demo", "version": "1.0.0",
                                             "scripts": {"postinstall": "node index.js"}}).encode(),
         "package/index.js": b"a\nb\nc\nd\ne\n"}


def test_zip_with_nested_tarball_gives_cited_lines(monkeypatch):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.writestr("sample/demo-1.0.0.tgz", tgz(FILES))
    monkeypatch.setattr(evidence, "_download", lambda _url: buffer.getvalue())
    result = evidence.inspect(ROW)
    assert result["problems"] == [] and result["manifest"] == "demo@1.0.0"
    assert result["hooks"] == {"postinstall": "node index.js"}
    assert [line["line"] for line in result["excerpt"]] == [2, 4, 5] and result["excerpt"][0]["text"] == "b"
    assert "`demo@1.0.0`" in evidence.to_markdown(2, [result])


def test_problems_are_reported_not_raised(monkeypatch):
    monkeypatch.setattr(evidence, "_download", lambda _url: tgz({"package/package.json": b'{"name": "other", "version": "1.0.0"}',
                                                                  "package/index.js": b"one\n"}))
    problems = evidence.inspect(ROW)["problems"]
    assert "manifest is other@1.0.0" in problems and "cited line outside file" in problems
    monkeypatch.setattr(evidence, "_download", lambda _url: (_ for _ in ()).throw(OSError("offline")))
    assert evidence.inspect(ROW)["problems"] == ["OSError: offline"]
