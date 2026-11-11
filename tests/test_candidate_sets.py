import csv

from data.scripts import collect_public_candidates as collect
from data.scripts.dedupe_labels import DEFAULT_HASHES


def test_new_set_skips_packages_of_every_earlier_set(tmp_path):
    for name, packages in (("450", ["a", "b"]), ("b2", ["c"])):
        folder = tmp_path / f"review_{name}"
        folder.mkdir()
        with (folder / f"public_candidates_{name}.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, ["package", "version"])
            writer.writeheader()
            writer.writerows({"package": p, "version": "1.0.0"} for p in packages)
    assert collect.already_seen(tmp_path) == {"a", "b", "c"}
    assert collect.set_paths("b2").as_posix().endswith("data/review_b2/public_candidates_b2.csv")


def test_first_set_hashes_stay_first():
    assert DEFAULT_HASHES[0].as_posix() == "data/review_450/triage_450.csv"
