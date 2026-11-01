"""Recheck npm metadata without downloading package code or assigning labels."""

import csv
import http.client
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from data.collect_public_candidates import HOOKS, NAME, VERSION, get_json

SOURCE = Path(__file__).with_name("review_450") / "public_candidates_450.csv"
OUTPUT = Path(__file__).with_name("review_450") / "metadata_review_450.csv"
FIELDS = ("package", "version", "source_label", "install_hook", "source_url",
          "review_status", "search_term", "observed_at")
EXTRA = ("metadata_status", "metadata_detail", "integrity_present", "label_decision", "reviewed_at",
         "hook_commands")


def review_row(row: dict[str, str], fetch=get_json) -> dict[str, str]:
    package, version = row["package"], row["version"]
    path = f"/{quote(package, safe='')}/{quote(version, safe='')}"
    result = dict(row, metadata_status="invalid_input", metadata_detail="invalid_source_or_hook",
                  integrity_present="unknown", label_decision="needs_code_review", hook_commands="")
    if (not NAME.fullmatch(package) or not VERSION.fullmatch(version)
            or row["source_url"] != "https://registry.npmjs.org" + path
            or not row["install_hook"]
            or any(hook not in HOOKS for hook in row["install_hook"].split(";"))):
        return result
    try:
        data = fetch(path)
    except (OSError, ValueError, http.client.HTTPException) as error:
        result["metadata_status"] = "unavailable" if "registry HTTP 404" in str(error) else "fetch_error"
        result["metadata_detail"] = type(error).__name__
        return result
    if not isinstance(data, dict) or data.get("name") != package or data.get("version") != version:
        result.update(metadata_status="mismatch", metadata_detail="name_or_version")
        return result
    scripts = data.get("scripts") or {}
    if not isinstance(scripts, dict):
        result.update(metadata_status="mismatch", metadata_detail="invalid_scripts")
        return result
    result["hook_commands"] = json.dumps(
        {hook: scripts[hook] for hook in HOOKS if isinstance(scripts.get(hook), str)}, ensure_ascii=False)
    actual = ";".join(hook for hook in HOOKS if isinstance(scripts.get(hook), str))
    result["integrity_present"] = "yes" if isinstance(data.get("dist"), dict) and data["dist"].get("integrity") else "no"
    result.update(metadata_status="verified" if actual == row["install_hook"] else "mismatch",
                  metadata_detail="hook_confirmed" if actual == row["install_hook"] else "hook_changed")
    return result


def main() -> None:
    with SOURCE.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("invalid candidate columns")
        rows = list(reader)
    if any(None in row or None in row.values() for row in rows):
        raise ValueError("invalid candidate row")
    if len(rows) != 450 or len({(row["package"], row["version"]) for row in rows}) != 450:
        raise ValueError("expected 450 unique package versions")
    if OUTPUT.exists():
        raise FileExistsError(OUTPUT)
    today = datetime.now(timezone(timedelta(hours=7))).date().isoformat()
    with ThreadPoolExecutor(max_workers=8) as pool:
        reviewed = list(pool.map(review_row, rows))
    with OUTPUT.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, FIELDS + EXTRA)
        writer.writeheader()
        writer.writerows(dict(row, reviewed_at=today) for row in reviewed)
    print(f"Reviewed metadata for {len(reviewed)} candidates; no labels assigned: {OUTPUT}")


if __name__ == "__main__":
    main()
