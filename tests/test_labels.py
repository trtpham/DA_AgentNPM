import csv

import pytest

from data.prepare_labels import prepare_labels


def test_labels_deduplicate_and_split(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("package,version,label,source,source_url,reviewer,split\n"
                      "fixture,1.0.0,benign,synthetic,https://example.invalid/fixture,reviewer,\n"
                      "fixture,2.0.0,benign,synthetic,https://example.invalid/fixture,reviewer,\n", encoding="utf-8")
    output = tmp_path / "labels.csv"
    assert prepare_labels(source, output) == 2
    with output.open(encoding="utf-8") as stream:
        splits = [row["split"] for row in csv.DictReader(stream)]
    assert splits[0] == splits[1] and splits[0] in {"dev", "test"}
    source.write_text(source.read_text(encoding="utf-8") +
                      "fixture,1.0.0,benign,synthetic,https://example.invalid/fixture,reviewer,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        prepare_labels(source, output)
