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
