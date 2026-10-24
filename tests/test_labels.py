import csv

import pytest

from data.prepare_labels import prepare_labels
from experiments.dataset import FIELDS, load_labels


def test_labels_deduplicate_and_split(tmp_path):
    source = tmp_path / "source.csv"
    header = ",".join(FIELDS) + "\n"
    row = "case-1,fixture,1.0.0,benign,local setup,none,package/install.js,1-3,https://example.invalid/fixture,,fixture\n"
    second = "case-2,fixture,2.0.0,benign,local setup,none,package/install.js,1-3,https://example.invalid/fixture,,fixture\n"
    source.write_text(header + row + second, encoding="utf-8")
    assert len(load_labels(source)) == 2

    output = tmp_path / "labels.csv"
    assert prepare_labels(source, output) == 2
    with output.open(encoding="utf-8") as stream:
        splits = [record["split"] for record in csv.DictReader(stream)]
    assert splits[0] == splits[1] and splits[0] in {"dev", "test"}

    source.write_text(header + row + second + row, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        prepare_labels(source, output)


def test_labels_reject_wrong_contract(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("package,version,label\nfixture,1.0.0,benign\n", encoding="utf-8")
    with pytest.raises(ValueError, match="columns"):
        load_labels(source)

    source.write_text(",".join(FIELDS) + "\n" + ",".join(["x"] * (len(FIELDS) + 1)) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="row"):
        load_labels(source)


def test_split_is_stratified_and_keeps_clusters_together(tmp_path):
    source = tmp_path / "source.csv"
    rows = []
    for label in ("benign", "suspicious", "malicious"):
        for index in range(5):
            rows.append({
                "id": f"{label}-{index}", "name": f"{label}-{index}", "version": "1.0.0",
                "label": label, "behavior_main": "fixture", "technique": "none", "file": "package.json",
                "lines": "1", "source": "https://example.invalid", "split": "", "cluster": f"{label}-{index}",
            })
    rows.append(rows[0] | {"id": "benign-copy", "name": "benign-copy"})
    with source.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    output = tmp_path / "labels.csv"
    assert prepare_labels(source, output) == len(rows)
    with output.open(encoding="utf-8") as stream:
        result = list(csv.DictReader(stream))
    assert {row["label"] for row in result if row["split"] == "test"} == {
        "benign", "suspicious", "malicious"}
    assert all(len({row["split"] for row in result if row["cluster"] == cluster}) == 1
               for cluster in {row["cluster"] for row in result})
    assert all(sum(row["split"] == "test" for row in result if row["label"] == label) == 1
               for label in ("benign", "suspicious", "malicious"))


def test_split_rejects_mixed_label_cluster(tmp_path):
    source = tmp_path / "source.csv"
    with source.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        for label in ("benign", "malicious"):
            writer.writerow({"id": label, "name": label, "version": "1.0.0", "label": label,
                             "behavior_main": "fixture", "technique": "none", "file": "package.json",
                             "lines": "1", "source": "https://example.invalid", "split": "", "cluster": "shared"})
    with pytest.raises(ValueError, match="mixed labels"):
        prepare_labels(source, tmp_path / "labels.csv")
