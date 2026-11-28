import csv
import json
from pathlib import Path

from data.scripts.build_labels_v2 import (
    V2_FIELDS,
    annotate_osv,
    build_draft,
    load_benign_triaged,
    load_datadog_v2,
    render_stats_md,
    split_clusters_three_way,
    time_split_flag,
)
from experiments.dataset import FIELDS


def _write_v1(path: Path) -> None:
    rows = [
        {"id": "v1-b1", "name": "already-in-v1", "version": "1.0.0", "label": "benign", "behavior_main": "ok",
         "technique": "reviewed", "file": "index.js", "lines": "1", "source": "https://registry.npmjs.org/x",
         "split": "test", "cluster": "already-in-v1"},
        {"id": "v1-s1", "name": "susp-dev", "version": "1.0.0", "label": "suspicious", "behavior_main": "check",
         "technique": "reviewed", "file": "setup.js", "lines": "2", "source": "https://registry.npmjs.org/s1",
         "split": "dev", "cluster": "susp-dev"},
        {"id": "v1-s2", "name": "susp-test", "version": "1.0.0", "label": "suspicious", "behavior_main": "check",
         "technique": "reviewed", "file": "setup.js", "lines": "3", "source": "https://registry.npmjs.org/s2",
         "split": "test", "cluster": "susp-test"},
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def test_time_split_flag():
    assert time_split_flag("2026-03-03") == "after"
    assert time_split_flag("2026-03-02") == "before"
    assert time_split_flag("2025-11-10") == "before"
    assert time_split_flag("") == "unknown"
    assert time_split_flag("bad-date") == "unknown"


def test_split_clusters_disjoint_and_blocks_v1_test_from_train():
    rows = [
        {"id": f"m{i}", "name": f"mal{i}", "version": "1.0.0", "label": "malicious",
         "cluster": f"c{i // 2}"}
        for i in range(10)
    ]
    out = split_clusters_three_way(rows, blocked_train_clusters=frozenset({"c0"}))
    by_cluster = {}
    for r in out:
        by_cluster.setdefault(r["cluster"], set()).add(r["split"])
    assert all(len(splits) == 1 for splits in by_cluster.values())
    assert by_cluster["c0"] <= {"dev", "test"}


def test_load_datadog_v2_skips_unreadable_batch(tmp_path, monkeypatch):
    dd_dir = tmp_path / "datadog"
    dd_dir.mkdir()
    good = dd_dir / "candidates-v2-batch-001.jsonl"
    bad = dd_dir / "candidates-v2-batch-002.jsonl"
    item = {
        "path": "ok/1.0.0/2025-05-01-ok-v1.0.0.zip", "name": "ok", "version": "1.0.0", "manifest": "ok@1.0.0",
        "archive": "https://raw.githubusercontent.com/x/ok.zip", "zip_sha256": "s1", "has_hook": True,
        "install_hash": "h1", "entries": [{"hook": "postinstall", "file": "i.js", "lines": 5}],
    }
    good.write_text(json.dumps(item) + "\n", encoding="utf-8")
    bad.write_text("placeholder\n", encoding="utf-8")

    orig_read_text = Path.read_text

    def guarded_read(self, *args, **kwargs):
        if self.name == "candidates-v2-batch-002.jsonl":
            raise OSError(22, "Invalid argument")
        return orig_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read)
    rows = load_datadog_v2(dd_dir)
    assert [r["name"] for r in rows] == ["ok"]


def test_source_kind_and_v1_test_name_blocked_from_train(tmp_path):
    v1_path = tmp_path / "labels-v1.csv"
    _write_v1(v1_path)
    t_pop = tmp_path / "triage_v2.csv"
    t_search = tmp_path / "triage_450.csv"
    cols = ["package", "version", "group", "entries", "tarball", "tarball_sha256", "install_hash"]
    for path, pkg, ver, sha, ih in [
        (t_pop, "already-in-v1", "2.0.0", "tb-pop", "ih-pop"),
        (t_search, "search-pkg", "1.0.0", "tb-srch", "ih-srch"),
    ]:
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, cols)
            writer.writeheader()
            writer.writerow({
                "package": pkg, "version": ver, "group": "A",
                "entries": json.dumps([{"hook": "install", "file": "i.js", "lines": 3}]),
                "tarball": f"https://registry.npmjs.org/{pkg}.tgz",
                "tarball_sha256": sha, "install_hash": ih,
            })

    ben_rows = load_benign_triaged([t_pop, t_search])
    by_name = {r["name"]: r for r in ben_rows}
    assert by_name["already-in-v1"]["source_kind"] == "npm-popular"
    assert by_name["search-pkg"]["source_kind"] == "npm-search"

    draft = build_draft(v1_path, [], ben_rows)
    pop_row = next(r for r in draft if r["name"] == "already-in-v1")
    assert pop_row["split"] != "train"


def test_build_draft_dedupes_v1_filters_osv_and_keeps_suspicious(tmp_path):
    v1_path = tmp_path / "labels-v1.csv"
    _write_v1(v1_path)

    dd_dir = tmp_path / "datadog"
    dd_dir.mkdir()
    dd_items = [
        {"path": "old/1.0.0/2024-06-01-old-v1.0.0.zip", "name": "old", "version": "1.0.0", "manifest": "old@1.0.0",
         "archive": "https://raw.githubusercontent.com/x/old.zip", "zip_sha256": "s0", "has_hook": True,
         "install_hash": "h0", "entries": [{"hook": "postinstall", "file": "i.js", "lines": 5}]},
        {"path": "evil1/1.0.0/2025-05-01-evil1-v1.0.0.zip", "name": "evil1", "version": "1.0.0", "manifest": "evil1@1.0.0",
         "archive": "https://raw.githubusercontent.com/x/e1.zip", "zip_sha256": "s1", "has_hook": True,
         "install_hash": "h1", "entries": [{"hook": "postinstall", "file": "i.js", "lines": 5}]},
        {"path": "evil2/1.0.0/2026-04-01-evil2-v1.0.0.zip", "name": "evil2", "version": "1.0.0", "manifest": "evil2@1.0.0",
         "archive": "https://raw.githubusercontent.com/x/e2.zip", "zip_sha256": "s2", "has_hook": True,
         "install_hash": "h2", "entries": [{"hook": "postinstall", "file": "i.js", "lines": 5}]},
    ]
    (dd_dir / "candidates-v2-batch-001.jsonl").write_text(
        "\n".join(json.dumps(x) for x in dd_items) + "\n", encoding="utf-8"
    )
    dd_rows = load_datadog_v2(dd_dir)
    assert [r["name"] for r in dd_rows] == ["evil1", "evil2"]  # 2024 excluded

    triage = tmp_path / "triage_v2.csv"
    with triage.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, ["package", "version", "group", "entries", "tarball", "tarball_sha256", "install_hash"])
        writer.writeheader()
        writer.writerows([
            {"package": "already-in-v1", "version": "1.0.0", "group": "A",
             "entries": json.dumps([{"hook": "install", "file": "i.js", "lines": 3}]),
             "tarball": "https://registry.npmjs.org/x.tgz", "tarball_sha256": "tb1", "install_hash": "ih1"},
            {"package": "osv-mal-ben", "version": "1.0.0", "group": "A",
             "entries": json.dumps([{"hook": "install", "file": "i.js", "lines": 3}]),
             "tarball": "https://registry.npmjs.org/y.tgz", "tarball_sha256": "tb2", "install_hash": "ih2"},
            {"package": "good-pop", "version": "2.0.0", "group": "B",
             "entries": json.dumps([{"hook": "postinstall", "file": "i.js", "lines": 10}]),
             "tarball": "https://registry.npmjs.org/z.tgz", "tarball_sha256": "tb3", "install_hash": "ih3"},
        ])
    ben_rows = load_benign_triaged([triage])
    osv_mal = annotate_osv(dd_rows + ben_rows, tmp_path / "osv.json",
                           checker=lambda n, v: {"ok": True, "data": {"malicious": n == "osv-mal-ben", "vulns": []}})
    draft = build_draft(v1_path, dd_rows, ben_rows, osv_mal=osv_mal)
    names = {r["name"] for r in draft}
    assert names == {"susp-dev", "susp-test", "evil1", "evil2", "good-pop"}
    assert all(set(r) == set(V2_FIELDS) for r in draft)
    susp_test = next(r for r in draft if r["name"] == "susp-test")
    assert susp_test["split"] != "train"
    evil2 = next(r for r in draft if r["name"] == "evil2")
    assert evil2["time_split"] == "after"
    assert "after" in render_stats_md(draft)
