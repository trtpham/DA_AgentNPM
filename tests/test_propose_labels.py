import csv
import json

import pytest

from data.scripts.propose_labels import cluster_of, draft, propose
from data.scripts.review_evidence import round_rows
from data.scripts.review_sheet import build_sheet, check_sheet, sheet_ids
from data.scripts.triage_candidates import FIELDS as TRIAGE_FIELDS
from experiments.dataset import FIELDS, load_labels


def triage_row(name, group="A", entries=None, version="1.0.0"):
    return {"package": name, "version": version, "group": group, "reasons": "", "hooks": "{}", "external": "",
            "risky": "{}", "hosts": "", "flows": "", "files": "1",
            "entries": json.dumps(entries if entries is not None else [{"hook": "postinstall", "file": "a.js", "lines": 400}]),
            "tarball": f"https://registry.npmjs.org/{name}/-/x-{version}.tgz", "tarball_sha256": "0" * 64}


def write(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)


def test_draft_cites_entry_and_caps_lines():
    row = draft(triage_row("@scope/pkg"))
    assert (row["file"], row["lines"], row["label"], row["split"]) == ("a.js", "1-150", "benign", "pending")
    assert row["id"] == "cand-scope-pkg-1.0.0" and row["cluster"] == "@scope"
    inline = draft(triage_row("x", entries=[{"hook": "preinstall", "file": "package.json", "line": 7}]))
    assert (inline["file"], inline["lines"]) == ("package.json", "7")
    assert draft(triage_row("y", entries=[])) is None
    assert cluster_of("plain") == "plain"


def test_propose_only_group_a_skips_known_and_caps_clusters(tmp_path):
    triage, labels, proposals = tmp_path / "t.csv", tmp_path / "labels.csv", tmp_path / "proposals.csv"
    rows = [triage_row("@s/a"), triage_row("@s/b"), triage_row("@s/c"), triage_row("known"),
            triage_row("risky", group="B"), triage_row("broken", group="C")]
    write(triage, TRIAGE_FIELDS, rows)
    write(labels, FIELDS, [{**{field: "x" for field in FIELDS}, "name": "known", "version": "1.0.0", "cluster": "known"}])
    added = propose(triage, labels, proposals, limit=10, cap=2)
    assert [row["name"] for row in added] == ["@s/a", "@s/b"]  # cap 2 for @s, known skipped, B/C never
    assert propose(triage, labels, proposals, limit=10, cap=2) == []  # nothing new on a second run
    assert len(load_labels(proposals)) == 2


def test_new_round_sheet_and_evidence_rows_come_from_ids(tmp_path):
    proposals = tmp_path / "proposals.csv"
    write(proposals, FIELDS, [draft(triage_row(name)) for name in ("a", "b", "c")])
    sheet = tmp_path / "round-5.csv"
    assert build_sheet(proposals, 5, sheet, ["cand-c-1.0.0", "cand-a-1.0.0"]) == 2
    assert sheet_ids(sheet) == ["cand-c-1.0.0", "cand-a-1.0.0"]
    assert [row["name"] for row in round_rows(5, proposals, sheet)] == ["c", "a"]
    assert check_sheet(sheet)["decisions"] == {"pending": 2}
    with pytest.raises(ValueError):
        build_sheet(proposals, 6, tmp_path / "round-6.csv")  # rounds 5+ need ids
    with pytest.raises(ValueError):
        build_sheet(proposals, 6, tmp_path / "round-6.csv", ["missing"])
