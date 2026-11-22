import base64
import csv
import json

import pytest

from data.scripts.blind_review import (blind_html, cohen_kappa, draw, evidence_index, fleiss_kappa, score_sheets,
                                       write_sample)


def rows(n_per=6):
    out = []
    for split in ("dev", "test"):
        for label in ("benign", "malicious", "suspicious"):
            for i in range(n_per):
                out.append({"id": f"{label}-{split}-{i}", "name": f"p{split}{label[0]}{i}", "version": "1.0.0",
                            "label": label, "split": split})
    return out


QUOTA = {("dev", "benign"): 2, ("dev", "malicious"): 2, ("dev", "suspicious"): 1,
         ("test", "benign"): 2, ("test", "malicious"): 2, ("test", "suspicious"): 1}


def test_draw_is_stratified_and_reproducible():
    table = rows()
    first = draw(table, {r["id"] for r in table}, QUOTA, seed=7)
    again = draw(table, {r["id"] for r in table}, QUOTA, seed=7)
    assert [r["id"] for r in first] == [r["id"] for r in again]
    for (split, label), count in QUOTA.items():
        assert sum(r["split"] == split and r["label"] == label for r in first) == count


def test_draw_skips_rows_without_evidence_and_fails_when_short():
    table = rows(2)
    available = {r["id"] for r in table if not r["id"].endswith("-1")}
    with pytest.raises(ValueError):
        draw(table, available, QUOTA, seed=1)


def item(row_id, package, label, code):
    return {"id": row_id, "package": package, "label": label, "file": "setup.js", "lines": "1-2",
            "source": "https://example.invalid/dd-source", "problems": [], "line_count": 2,
            "hooks_b64": base64.b64encode(json.dumps({"postinstall": "node setup.js"}).encode()).decode(),
            "excerpt": [{"line": 1, "b64": base64.b64encode(code.encode()).decode()}]}


def test_blind_page_hides_label_id_source_and_raw_code():
    page = blind_html([{"id": "dd-fixture-1"}], {"dd-fixture-1": item("dd-fixture-1", "fixture@1.0.0", "malicious",
                                                                       "MARKER_RAW_CODE()")})
    assert page.count("malicious") == 1  # only in the instructions: benign, malicious hoặc suspicious
    for leaked in ("dd-fixture-1", "example.invalid", "MARKER_RAW_CODE", "đề xuất", "Kiểm tự động"):
        assert leaked not in page
    assert "S01" in page and "fixture@1.0.0" in page


def test_sample_writes_blank_sheets_and_key_outside_sheets(tmp_path):
    table = rows()
    labels = tmp_path / "labels.csv"
    with labels.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "name", "version", "label", "behavior_main", "technique",
                                                    "file", "lines", "source", "split", "cluster"])
        writer.writeheader()
        for r in table:
            writer.writerow({**r, "behavior_main": "", "technique": "", "file": "", "lines": "", "source": "",
                             "cluster": r["id"]})
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "round-1.json").write_text(json.dumps(
        [item(r["id"], f"{r['name']}@1.0.0", r["label"], "x") for r in table]), encoding="utf-8")
    import data.scripts.blind_review as module
    original = module.QUOTA
    module.QUOTA = QUOTA
    try:
        out = write_sample(labels, evidence, tmp_path / "sheets")
    finally:
        module.QUOTA = original
    assert out["rows"] == 10
    sheet = (tmp_path / "sheets" / "phieu-Phuoc.csv").read_text(encoding="utf-8")
    assert "benign" not in sheet and "malicious" not in sheet and "suspicious" not in sheet
    assert (evidence / "blind-v1-key.csv").exists() and not (tmp_path / "sheets" / "blind-v1-key.csv").exists()
    with pytest.raises(FileExistsError):
        write_sample(labels, evidence, tmp_path / "sheets")


def test_kappas_on_known_values():
    assert cohen_kappa(["benign", "malicious"] * 5, ["benign", "malicious"] * 5) == 1.0
    assert cohen_kappa(["benign"] * 5 + ["malicious"] * 5, ["malicious"] * 5 + ["benign"] * 5) == -1.0
    assert fleiss_kappa([["benign"] * 3, ["malicious"] * 3, ["suspicious"] * 3]) == 1.0
    assert fleiss_kappa([]) is None


def test_score_reads_sheets_and_reports_disagreements(tmp_path):
    key = tmp_path / "key.csv"
    key.write_text("ma,id,split,label\nS01,a,dev,benign\nS02,b,dev,malicious\n", encoding="utf-8")
    for name, labels in (("Phuoc", ("benign", "malicious")), ("Thien", ("benign", "suspicious")),
                         ("Triet", ("benign", "malicious"))):
        (tmp_path / f"phieu-{name}.csv").write_text(
            "ma,goi,nhan,ly_do,phut\n" + "".join(f"S0{i},p@1,{lab},,\n" for i, lab in enumerate(labels, 1)),
            encoding="utf-8")
    out = score_sheets(tmp_path, key)
    assert out["vs_labels_v1"]["Phuoc"]["agreement"] == 1.0
    assert out["vs_labels_v1"]["Thien"]["disagree"] == ["S02"]
    assert out["fleiss_items"] == 2


def test_invalid_label_is_rejected(tmp_path):
    key = tmp_path / "key.csv"
    key.write_text("ma,id,split,label\nS01,a,dev,benign\n", encoding="utf-8")
    (tmp_path / "phieu-Phuoc.csv").write_text("ma,goi,nhan,ly_do,phut\nS01,p@1,lanh,,\n", encoding="utf-8")
    with pytest.raises(ValueError):
        score_sheets(tmp_path, key)


def test_evidence_index_prefers_later_rounds(tmp_path):
    (tmp_path / "round-2.json").write_text(json.dumps([{"id": "a", "v": 2}]), encoding="utf-8")
    (tmp_path / "round-10.json").write_text(json.dumps([{"id": "a", "v": 10}]), encoding="utf-8")
    assert evidence_index(tmp_path)["a"]["v"] == 10
