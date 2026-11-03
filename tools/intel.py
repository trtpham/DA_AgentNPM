"""Context signals for one package version (week 4).

Network lookups send only `name@version` to two fixed HTTPS hosts and run as a separate
step that writes JSON; the agent reads that file and never calls the network itself.
Context is a hint for the decision rules, never evidence for a label.
"""

import argparse
import json
import re
import ssl
import urllib.parse
from http.client import HTTPSConnection
from pathlib import Path

from tools.static import LIFECYCLE, extract_indicators, install_targets, read_manifest

NAME = re.compile(r"^(?:@[a-z0-9._-]+/)?[a-z0-9._-]+$")
VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
HOSTS = {"api.osv.dev", "registry.npmjs.org"}
MAX_BYTES = 30 * 1024 * 1024


def _https_json(url: str, body: dict | None = None, accept: str = "application/json") -> dict:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in HOSTS:
        raise ValueError("lookup host not allowed")
    data = json.dumps(body).encode() if body is not None else None
    # Certificate and hostname checks come from the default context (Python 3.14, see requirements.txt).
    connection = HTTPSConnection(parsed.hostname, timeout=30, context=ssl.create_default_context())  # nosemgrep: python.lang.security.audit.httpsconnection-detected.httpsconnection-detected
    try:
        connection.request("POST" if data else "GET", parsed.path or "/", data,
                           {"Accept": accept, "Content-Type": "application/json"})
        response = connection.getresponse()
        raw = response.read(MAX_BYTES + 1)
        if response.status != 200:
            raise OSError(f"HTTP {response.status} from {parsed.hostname}")
    finally:
        connection.close()
    if len(raw) > MAX_BYTES:
        raise ValueError("lookup response too large")
    return json.loads(raw)


def _check(name: str, version: str) -> None:
    if not NAME.fullmatch(name) or not VERSION.fullmatch(version):
        raise ValueError("invalid package name or version")


def _semver_key(version: str) -> tuple:
    core, _, pre = version.partition("+")[0].partition("-")
    numbers = tuple(int(part) for part in core.split("."))
    return numbers + ((1,) if not pre else (0, pre))


def osv_lookup(name: str, version: str, fetch=_https_json) -> dict:
    try:
        _check(name, version)
        reply = fetch("https://api.osv.dev/v1/query",
                      {"package": {"name": name, "ecosystem": "npm"}, "version": version})
        vulns = [{"id": str(item.get("id", "")), "summary": str(item.get("summary", ""))[:200]}
                 for item in reply.get("vulns", [])]
        return {"ok": True, "data": {"untrusted": True, "vulns": vulns,
                                      "malicious": any(item["id"].startswith("MAL-") for item in vulns)}, "error": None}
    except (OSError, ValueError, TypeError, AttributeError) as error:
        return {"ok": False, "data": None, "error": str(error)[:300]}


def registry_metadata(name: str, version: str, fetch=_https_json) -> dict:
    try:
        _check(name, version)
        base = "https://registry.npmjs.org/" + name  # NAME already limits it to URL-safe characters
        listing = fetch(base, accept="application/vnd.npm.install-v1+json")
        versions = sorted((item for item in listing.get("versions", {}) if VERSION.fullmatch(item)), key=_semver_key)
        if version not in versions:
            raise ValueError("version not found in registry")
        older = [item for item in versions[:versions.index(version)] if "-" not in item]
        previous = older[-1] if older else None
        current = fetch(f"{base}/{version}")

        def hooks(document: dict) -> dict:
            scripts = document.get("scripts") or {}
            return {hook: scripts[hook] for hook in LIFECYCLE if isinstance(scripts.get(hook), str)}

        now = hooks(current)
        before = hooks(fetch(f"{base}/{previous}")) if previous else None
        return {"ok": True, "data": {
            "untrusted": True,
            "versions": len(versions),
            "previous_version": previous,
            "lifecycle": now,
            "hooks_changed_since_previous": None if before is None else now != before,
            "new_hooks": None if before is None else sorted(set(now) - set(before)),
            "maintainers": len(current.get("maintainers") or []),
            "deprecated": bool(current.get("deprecated")),
            "integrity": (current.get("dist") or {}).get("integrity"),
        }, "error": None}
    except (OSError, ValueError, TypeError, AttributeError) as error:
        return {"ok": False, "data": None, "error": str(error)[:300]}


def diff_versions(old_package: str, new_package: str) -> dict:
    """Static comparison of the install path of two extracted versions; nothing is executed."""
    try:
        sides = []
        for package in (old_package, new_package):
            manifest = read_manifest(package)
            indicators = extract_indicators(package)
            if not manifest["ok"] or not indicators["ok"]:
                raise ValueError(manifest["error"] or indicators["error"])
            scripts = manifest["data"]["scripts"]["content"]
            sides.append({
                "hooks": {hook: scripts[hook] for hook in LIFECYCLE if hook in scripts},
                "targets": install_targets(package, scripts, manifest["data"]["has_binding_gyp"]),
                "indicators": {item["type"] for item in indicators["data"]["indicators"]},
            })
        old, new = sides
        return {"ok": True, "data": {"untrusted": True,
            "hooks_added": sorted(set(new["hooks"]) - set(old["hooks"])),
            "hooks_removed": sorted(set(old["hooks"]) - set(new["hooks"])),
            "hooks_changed": sorted(hook for hook in set(old["hooks"]) & set(new["hooks"])
                                    if old["hooks"][hook] != new["hooks"][hook]),
            "targets_added": sorted(new["targets"] - old["targets"]),
            "indicator_types_added": sorted(new["indicators"] - old["indicators"]),
        }, "error": None}
    except (OSError, ValueError) as error:
        return {"ok": False, "data": None, "error": str(error)[:300]}


def build_context(name: str, version: str, fetch=_https_json) -> dict:
    return {"package": f"{name}@{version}", "osv": osv_lookup(name, version, fetch),
            "registry": registry_metadata(name, version, fetch)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Look up OSV and npm Registry context for one package version")
    parser.add_argument("name")
    parser.add_argument("version")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    context = json.dumps(build_context(args.name, args.version), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(context, encoding="utf-8")
    print(context)


if __name__ == "__main__":
    main()
