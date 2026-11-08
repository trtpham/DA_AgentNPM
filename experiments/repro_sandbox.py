"""W5-4: is the sandbox reproducible, and does it never carry a host secret? Fixtures only.

Runs every harmless fixture (6 limit probes + 3 package fixtures) N times in the offline container,
compares outcome, canaries touched and per-actor counts, and checks that no value of the host's
environment appears in any trace or output. Only variable names are reported, never values.

    py -3.14 -m experiments.repro_sandbox --runs 3 [--hardening]
"""

import argparse
import ipaddress
import json
import os
import subprocess
import sys
from pathlib import Path

from sandbox.run import CANARY, IMAGE, run_sandbox

FIXTURES = Path("tests/fixtures")
NAMES = ["sandbox-limits/network", "sandbox-limits/processes", "sandbox-limits/memory", "sandbox-limits/timeout",
         "sandbox-limits/write-outside", "sandbox-limits/canary-all", "packages/benign-package",
         "packages/canary-package", "packages/no-hook-package"]
# Values too short or too common to mean anything when found in a trace.
IGNORED_VALUES = {"1", "0", "true", "false", "C:\\", "/", "Windows_NT"}


def fingerprint(result: dict) -> dict:
    """The fields that must be equal across runs of the same fixture."""
    data = result.get("data") or {}
    actors = data.get("by_actor") or {}
    behavior = data.get("behavior") or {}
    return {"ok": result.get("ok"), "outcome": data.get("outcome"),
            "canary_touched": sorted(data.get("canary_touched") or []),
            "package_network": (actors.get("package") or {}).get("network_count"),
            "package_processes": len((actors.get("package") or {}).get("processes", [])),
            "persistence": sorted(item["path"] for item in behavior.get("persistence_writes", [])
                                  if item.get("actor") == "package")}


def _loopback(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def host_values(environ: dict[str, str] | None = None) -> dict[str, str]:
    """Host environment values worth searching for; loopback addresses (127.0.0.1) are in every npm trace."""
    canaries = {CANARY["environment"], *CANARY.get("environment_vars", {}).values()}
    return {name: value for name, value in (os.environ if environ is None else environ).items()
            if len(value) >= 8 and value not in IGNORED_VALUES and value not in canaries and not _loopback(value)}


def leaked(result: dict, values: dict[str, str]) -> list[str]:
    data = result.get("data") or {}
    text = "\n".join(str((data.get(key) or {}).get("content", "")) for key in ("strace", "stdout", "stderr"))
    return sorted(name for name, value in values.items() if value in text)


def image_digest() -> str | None:
    try:
        output = subprocess.run(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"],
                                capture_output=True, text=True, timeout=30, check=False)
        return output.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def main() -> None:
    sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Run the harmless sandbox fixtures several times")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--hardening", action="store_true")
    args = parser.parse_args()
    values = host_values()
    report = {"image": image_digest(), "hardening": args.hardening, "runs": args.runs,
              "host_values_checked": len(values), "fixtures": {}}
    for name in NAMES:
        prints, leaks = [], set()
        for _ in range(args.runs):
            result = run_sandbox(FIXTURES / name, hardening=args.hardening)
            prints.append(fingerprint(result))
            leaks.update(leaked(result, values))
        report["fixtures"][name] = {"same": all(item == prints[0] for item in prints), "first": prints[0],
                                    "differences": [item for item in prints[1:] if item != prints[0]],
                                    "host_value_names_found": sorted(leaks)}
        row = report["fixtures"][name]
        print(f"{name:32} same={row['same']} outcome={prints[0]['outcome']:10} "
              f"canaries={len(prints[0]['canary_touched'])} leaks={len(leaks)}", flush=True)
    report["all_same"] = all(row["same"] for row in report["fixtures"].values())
    report["no_host_leak"] = not any(row["host_value_names_found"] for row in report["fixtures"].values())
    out = Path("reports") / f"repro-sandbox{'-hardening' if args.hardening else ''}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("image", "all_same", "no_host_leak", "host_values_checked")}))


if __name__ == "__main__":
    main()
