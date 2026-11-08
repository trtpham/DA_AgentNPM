import csv

import pytest

from data.scripts.dedupe_labels import dedupe, load_hashes
from experiments.dataset import FIELDS


def row(row_id, name, cluster, version="1.0.0", label="benign", split="dev"):
    return {"id": row_id, "name": name, "version": version, "label": label, "behavior_main": "b", "technique": "t",
            "file": "a.js", "lines": "1", "source": "s", "split": split, "cluster": cluster}


def test_exact_duplicates_keep_the_first_table():
    labels = [row("L1", "pkg", "fam")]
    proposals = [row("P1", "pkg", "pkg"), row("P2", "other", "other")]
    result = dedupe([labels, proposals], {})
    assert [item["id"] for item in result["rows"]] == ["L1", "P2"]
    assert result["dropped"] == [{"id": "P1", "rule": "same name@version", "kept": "L1"}]


def test_same_tarball_under_two_names_is_one_sample():
    hashes = {("a", "1.0.0"): {"tarball_sha256": "t1", "install_hash": ""},
              ("b", "1.0.0"): {"tarball_sha256": "t1", "install_hash": ""}}
    result = dedupe([[row("1", "a", "a"), row("2", "b", "b")]], hashes)
    assert [item["id"] for item in result["rows"]] == ["1"] and result["dropped"][0]["rule"] == "same tarball sha256"


def test_look_alike_install_code_merges_clusters_transitively():
    hashes = {("a", "1.0.0"): {"tarball_sha256": "1", "install_hash": "h1"},
              ("b", "1.0.0"): {"tarball_sha256": "2", "install_hash": "h1"},
              ("c", "1.0.0"): {"tarball_sha256": "3", "install_hash": "h2"},
              ("d", "1.0.0"): {"tarball_sha256": "4", "install_hash": "h2"},
              ("e", "1.0.0"): {"tarball_sha256": "5", "install_hash": ""}}
    rows = [row("1", "a", "fa"), row("2", "b", "fb"), row("3", "c", "fb"), row("4", "d", "fd"), row("5", "e", "fe")]
    result = dedupe([rows], hashes)
    clusters = {item["id"]: item["cluster"] for item in result["rows"]}
    assert clusters == {"1": "fa", "2": "fa", "3": "fa", "4": "fa", "5": "fe"}
    assert {item["id"] for item in result["merged"]} == {"2", "3", "4"}


def test_cluster_cap_keeps_reviewed_labels_first_and_reports_leakage():
    labels = [row("L1", "x1", "big", split="test")]
    proposals = [row(f"P{i}", f"p{i}", "big", split="dev") for i in range(5)]
    result = dedupe([labels, proposals], {}, cap=3)
    assert [item["id"] for item in result["rows"]] == ["L1", "P0", "P1"]
    assert sum(item["rule"] == "cluster cap 3" for item in result["dropped"]) == 3
    assert result["leakage"] == ["big"] and result["summary"]["leaking_clusters"] == 1


def test_load_hashes_reads_triage_columns(tmp_path):
    path = tmp_path / "triage.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, ["package", "version", "tarball_sha256", "install_hash"])
        writer.writeheader()
        writer.writerow({"package": "a", "version": "1.0.0", "tarball_sha256": "t", "install_hash": "h"})
    assert load_hashes([path, tmp_path / "missing.csv"]) == {("a", "1.0.0"): {"tarball_sha256": "t", "install_hash": "h"}}


def test_output_rows_keep_the_label_contract():
    result = dedupe([[row("1", "a", "a")]], {})
    assert list(result["rows"][0]) == list(FIELDS)
