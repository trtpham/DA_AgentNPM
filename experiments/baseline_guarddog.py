"""GuardDog baseline (TV3-4): static scan of extracted packages in an offline container.

GuardDog's semgrep rules do not run natively on Windows (semgrep exits with code 2 and
paths containing "tests" are skipped), so the scan runs in experiments/guarddog/Dockerfile.
Build once: docker build -t agent-npm-guarddog:2.6.0 experiments/guarddog
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from experiments.run_batch import RUN_ID, result_name, select_inputs
from tools.fetch import fetch_package

IMAGE = "agent-npm-guarddog:2.6.0"


def scan_command(package_dir: Path, image: str = IMAGE) -> list[str]:
    return ["docker", "run", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,size=256m",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "1g", "--pids-limit", "128",
            "--mount", f"type=bind,source={package_dir.resolve(strict=True)},target=/scan,readonly",
            image, "npm", "scan", "/scan", "--output-format", "json"]


def scan(package_dir: Path, image: str = IMAGE, runner=subprocess.run) -> dict:
    try:
        completed = runner(scan_command(package_dir, image), capture_output=True, text=True, timeout=600, check=False)
        report = json.loads(completed.stdout)
        if not isinstance(report, dict) or "issues" not in report:
            raise ValueError("unexpected GuardDog output")
        rules = sorted(rule for rule, findings in (report.get("results") or {}).items() if findings)
        return {"ok": not report.get("errors"), "data": {"issues": report["issues"], "rules": rules,
                                                          "errors": report.get("errors") or {},
                                                          "results": report.get("results") or {}},
                "error": "; ".join(f"{key}: {value}"[:200] for key, value in (report.get("errors") or {}).items()) or None}
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return {"ok": False, "data": None, "error": str(error)[:300]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan packages with GuardDog in an offline container")
    parser.add_argument("run_id")
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--split", choices=("dev", "test"))
    parser.add_argument("--name", action="append", default=[])
    parser.add_argument("--dir", action="append", type=Path, default=[])
    parser.add_argument("--isolated", action="store_true", help="allow non-benign rows; only inside an isolated VM")
    parser.add_argument("--reports", type=Path, default=Path("reports"))
    parser.add_argument("--image", default=IMAGE)
    args = parser.parse_args()
    if not RUN_ID.fullmatch(args.run_id):
        sys.exit("invalid run id")
    inputs = select_inputs(args.labels, args.split, args.name, args.dir, args.isolated)
    out = args.reports / args.run_id / "guarddog"
    out.mkdir(parents=True, exist_ok=True)
    image_id = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", args.image],
                              capture_output=True, text=True, timeout=60).stdout.strip()
    meta = {"tool": "guarddog", "version": args.image.rsplit(":", 1)[-1], "image": args.image, "image_id": image_id,
            "command": scan_command(Path("."), args.image)[:-5] + ["npm", "scan", "/scan", "--output-format", "json"],
            "started_at": datetime.now(timezone.utc).isoformat(), "inputs": [item["package"] for item in inputs]}
    for item in inputs:
        target = out / result_name(item["package"])
        if target.is_file():
            continue
        fetched = None
        if "dir" in item:
            result = scan(Path(item["dir"]), args.image)
        else:
            fetched = fetch_package(item["name"], item["version"])
            result = scan(Path(fetched["data"]["dir"]), args.image) if fetched["ok"] else fetched
            if fetched["ok"]:
                shutil.rmtree(Path(fetched["data"]["dir"]).parent, ignore_errors=True)
        result["package"] = item["package"]
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"package": item["package"], "ok": result["ok"],
                          "issues": (result["data"] or {}).get("issues"), "rules": (result["data"] or {}).get("rules")}))
    meta["finished_at"] = datetime.now(timezone.utc).isoformat()
    (out / "guarddog_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
