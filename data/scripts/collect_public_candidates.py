"""Collect npm manifest metadata only; never download or execute package code."""

import argparse
import csv
import http.client
import json
import re
import ssl
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode


TARGET = 450
OUTPUT = Path(__file__).resolve().parents[1] / "review_450" / "public_candidates_450.csv"
HOOKS = ("preinstall", "install", "postinstall")
TERMS = ("postinstall", "preinstall", "install script", "node-gyp", "native addon")
NAME = re.compile(r"^(?:@[a-z0-9._~-]+/)?[a-z0-9._~-]+$")
VERSION = re.compile(r"^[0-9][a-zA-Z0-9.+_-]*$")


def get_json(path):
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("registry path required")
    for attempt in range(3):
        connection = http.client.HTTPSConnection(  # nosemgrep: python.lang.security.audit.httpsconnection-detected.httpsconnection-detected
            "registry.npmjs.org", timeout=15, context=ssl.create_default_context())
        try:
            connection.request("GET", path, headers={"User-Agent": "DA-AgentNPM-metadata/1"})
            response = connection.getresponse()
            if response.status != 200:
                if response.status not in (429, 500, 502, 503, 504):
                    raise ValueError(f"registry HTTP {response.status}")
                raise OSError(f"registry HTTP {response.status}")
            data = response.read(5_000_001)
            if len(data) > 5_000_000:
                raise ValueError("metadata response too large")
            return json.loads(data)
        except (OSError, http.client.HTTPException) as exc:
            if attempt == 2:
                raise exc
            time.sleep(1 + attempt)
        finally:
            connection.close()


def manifest(candidate):
    package, version, term = candidate
    path = f"/{quote(package, safe='')}/{quote(version, safe='')}"
    try:
        data = get_json(path)
    except (OSError, http.client.HTTPException, ValueError):
        return None
    if data.get("name") != package or data.get("version") != version:
        return None
    scripts = data.get("scripts") or {}
    if not isinstance(scripts, dict):
        return None
    hooks = [name for name in HOOKS if isinstance(scripts.get(name), str)]
    if not hooks:
        return None
    return {"package": package, "version": version, "source_label": "unlabeled",
            "install_hook": ";".join(hooks), "source_url": "https://registry.npmjs.org" + path,
            "review_status": "needs_independent_review", "search_term": term,
            "observed_at": datetime.now(timezone.utc).date().isoformat()}


def set_paths(name: str) -> Path:
    """data/review_<name>/public_candidates_<name>.csv (the first set is "450")."""
    return OUTPUT.parents[1] / f"review_{name}" / f"public_candidates_{name}.csv"


def already_seen(data_dir: Path) -> set[str]:
    """Package names of every earlier candidate set, so a new set never repeats them."""
    seen = set()
    for path in data_dir.glob("review_*/public_candidates_*.csv"):
        with path.open(newline="", encoding="utf-8") as stream:
            seen |= {row["package"] for row in csv.DictReader(stream)}
    return seen


def main():
    parser = argparse.ArgumentParser(description=f"Collect npm manifests with install hooks (metadata only; "
                                     f"refuses to replace an existing set)")
    parser.add_argument("--set", default="450", help="set name; files go to data/review_<set>/")
    parser.add_argument("--target", type=int, default=TARGET)
    parser.add_argument("--terms", nargs="+", default=list(TERMS), help="npm search terms")
    args = parser.parse_args()
    output, target, terms = set_paths(args.set), args.target, tuple(args.terms)
    if output.exists():
        raise SystemExit(f"Refusing to replace {output}")
    rows, seen = [], already_seen(output.parents[1])
    with ThreadPoolExecutor(max_workers=8) as pool:
        for term in terms:
            for offset in range(0, 3000, 250):
                path = "/-/v1/search?" + urlencode(
                    {"text": term, "size": 250, "from": offset})
                results = get_json(path).get("objects", [])
                candidates = []
                for item in results:
                    info = item.get("package", {})
                    package, version = info.get("name", ""), info.get("version", "")
                    if not NAME.fullmatch(package) or not VERSION.fullmatch(version) or package in seen:
                        continue
                    seen.add(package)
                    candidates.append((package, version, term))
                for start in range(0, len(candidates), 50):
                    for row in pool.map(manifest, candidates[start:start + 50]):
                        if row is not None and len(rows) < target:
                            rows.append(row)
                    print(f"{term} offset={offset}: {len(rows)}/{target}", flush=True)
                    if len(rows) == target:
                        break
                if len(rows) == target or not results:
                    break
            if len(rows) == target:
                break
    if len(rows) != target or len({row["package"] for row in rows}) != target:
        raise SystemExit(f"Collected {len(rows)} unique packages; no CSV written")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {target} metadata candidates to {output}")


if __name__ == "__main__":
    main()
