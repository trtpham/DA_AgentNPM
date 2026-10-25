"""Collect npm manifest metadata only; never download or execute package code."""

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
OUTPUT = Path(__file__).with_name("public_candidates_450.csv")
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


def main():
    if OUTPUT.exists():
        raise SystemExit(f"Refusing to replace {OUTPUT}")
    rows, seen = [], set()
    with ThreadPoolExecutor(max_workers=8) as pool:
        for term in TERMS:
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
                        if row is not None and len(rows) < TARGET:
                            rows.append(row)
                    print(f"{term} offset={offset}: {len(rows)}/{TARGET}", flush=True)
                    if len(rows) == TARGET:
                        break
                if len(rows) == TARGET or not results:
                    break
            if len(rows) == TARGET:
                break
    if len(rows) != TARGET or len({row["package"] for row in rows}) != TARGET:
        raise SystemExit(f"Collected {len(rows)} unique packages; no CSV written")
    with OUTPUT.open("x", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {TARGET} metadata candidates to {OUTPUT}")


if __name__ == "__main__":
    main()
