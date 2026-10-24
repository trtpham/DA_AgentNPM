import csv
import io
import json
import tarfile
import zipfile

from data.filter_datadog import filter_archives


def test_filter_archives_keeps_hooks_and_deduplicates_synthetic_clusters(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    for name, url in (("one", "https://one.example.invalid"), ("two", "https://two.example.invalid")):
        manifest = {"name": name, "version": "1.0.0", "scripts": {"install": f"echo {url}"}}
        with zipfile.ZipFile(source / f"{name}.zip", "w") as archive:
            archive.writestr("package/package.json", json.dumps(manifest))
    with zipfile.ZipFile(source / "no-hook.zip", "w") as archive:
        archive.writestr("package/package.json", json.dumps({"name": "no-hook", "version": "1.0.0"}))
    tar_bytes = io.BytesIO()
    with tarfile.open(fileobj=tar_bytes, mode="w:gz") as tar:
        manifest = json.dumps({"name": "native", "version": "1.0.0"}).encode()
        info = tarfile.TarInfo("package/package.json")
        info.size = len(manifest)
        tar.addfile(info, io.BytesIO(manifest))
        info = tarfile.TarInfo("package/binding.gyp")
        info.size = 2
        tar.addfile(info, io.BytesIO(b"{}"))
    with zipfile.ZipFile(source / "native.zip", "w") as archive:
        archive.writestr("package.tgz", tar_bytes.getvalue())
    with zipfile.ZipFile(source / "native-other.zip", "w") as archive:
        archive.writestr("package/package.json", json.dumps({"name": "native-other", "version": "1.0.0"}))
        archive.writestr("package/binding.gyp", '{"targets": [1]}')
    (source / "broken.zip").write_bytes(b"not a zip")

    output = tmp_path / "candidates.csv"
    counts = filter_archives(source, output)
    with output.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert counts == {"scanned": 6, "matching_before_dedup": 4, "candidates": 3, "failed": 1}
    assert {row["name"] for row in rows} == {"one", "native", "native-other"}
    assert all(len(row["sha256"]) == 64 and len(row["cluster"]) == 64 for row in rows)
