"""Run the agent over a set of packages with resume and run metadata (TV1-8).

Results go to reports/<run_id>/<package>.json plus run_meta.json. A package that fails is
recorded and the batch continues. Labels are used only to choose which rows may be
fetched on this host; they never reach the prompt.
"""

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from http.client import HTTPConnection
from pathlib import Path

from agent import run as agent_run
from agent.trace import TraceWriter, trace_filename
from experiments.dataset import load_labels
from tools.actions import apply_decision
from tools.fetch import fetch_package
from tools.static import read_manifest

CONFIGS = Path("experiments/configs")
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


# num_gpu: layers Ollama puts on the GPU; its own estimate left A-LLM half on CPU (W5-8).
OPTION_TYPES = {"num_ctx": int, "temperature": float, "num_gpu": int}


def load_config(variant: str, configs: Path = CONFIGS) -> dict:
    """Read the flat YAML subset used by experiments/configs (AGENTS §6.7), with one `options:` block."""
    values, options, section = {}, {}, None
    for line in (configs / f"{variant}.yaml").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, _, value = line.strip().partition(":")
        value = value.strip().strip('"')
        if not line.startswith((" ", "	")):
            section = key if not value else None
            if value:
                values[key] = value
        elif section == "options":
            if key not in OPTION_TYPES:
                raise ValueError(f"{variant}: unknown option {key}")
            options[key] = OPTION_TYPES[key](value)
    config = {"name": values["name"], "model": values["model"], "max_steps": int(values["max_steps"]),
              "deny_threshold": float(values["deny_threshold"]), "approve_threshold": float(values["approve_threshold"]),
              "options": options}
    # Optional keys are added only when present, so older configs (and run_meta of older runs) stay equal.
    for key, parse in FEATURE_TYPES.items():
        if key in values:
            config[key] = parse(variant, key, values[key])
    return config


def _tool_list(variant: str, key: str, value: str) -> list[str]:
    match = re.fullmatch(r"\[(.*)\]", value)
    names = [name.strip().strip("'\"") for name in match.group(1).split(",")] if match else []
    if not names or any(name not in agent_run.ALL_TOOLS for name in names) or len(set(names)) != len(names):
        raise ValueError(f"{variant}: {key} must be a list of known tools, got {value}")
    return names


def _flag(variant: str, key: str, value: str) -> bool:
    if value not in ("true", "false"):
        raise ValueError(f"{variant}: {key} must be true or false")
    return value == "true"


def _small_int(variant: str, key: str, value: str) -> int:
    if not re.fullmatch(r"[1-9]", value):
        raise ValueError(f"{variant}: {key} must be an integer 1-9")
    return int(value)


# Per-model agent features (plan A11, B1, B3, B5, C7); each maps to an `analyze` keyword.
FEATURE_TYPES = {"tools": _tool_list, "self_check": _flag, "guided_reading": _flag, "repeat_limit": _small_int,
                 "sandbox": _flag}


def variants(configs: Path = CONFIGS) -> list[str]:
    return sorted(path.stem for path in configs.glob("*.yaml"))


def result_name(package: str) -> str:
    return package.replace("/", "__") + ".json"


def _ollama(path: str) -> dict | None:
    connection = HTTPConnection("127.0.0.1", 11434, timeout=10)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return json.load(response) if response.status == 200 else None
    except (OSError, ValueError):
        return None
    finally:
        connection.close()


def run_meta(run_id: str, config: dict, inputs: list[dict], labels: Path | None) -> dict:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, timeout=10).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        commit, dirty = None, None
    tags = _ollama("/api/tags") or {}
    model = next((item for item in tags.get("models", []) if item.get("name") == config["model"]), {})
    return {
        "run_id": run_id, "started_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": commit, "git_dirty": dirty,
        "python": platform.python_version(), "platform": platform.platform(),
        "ollama_version": (_ollama("/api/version") or {}).get("version"),
        "model": config["model"], "model_digest": model.get("digest"),
        "config": config, "chat_options": {**agent_run.CHAT_OPTIONS, **config["options"]},
        "labels_sha256": hashlib.sha256(labels.read_bytes()).hexdigest() if labels else None,
        "inputs": [item["package"] for item in inputs],
    }


def select_inputs(labels: Path | None, split: str | None, names: list[str], dirs: list[Path],
                  isolated: bool) -> list[dict]:
    inputs = []
    for directory in dirs:
        manifest = read_manifest(str(directory))
        if not manifest["ok"]:
            raise ValueError(f"{directory}: {manifest['error']}")
        inputs.append({"package": f"{manifest['data']['name']}@{manifest['data']['version']}", "dir": directory})
    if labels:
        for row in load_labels(labels):
            if split and row["split"] != split or names and row["name"] not in names:
                continue
            # Suspicious and malicious archives are only read inside an isolated VM/container.
            if row["label"] != "benign" and not isolated:
                raise ValueError(f"{row['name']}@{row['version']} is not benign; run with --isolated only inside a VM")
            inputs.append({"package": f"{row['name']}@{row['version']}", "name": row["name"], "version": row["version"]})
    return inputs


def sandbox_kwargs(item: dict, config: dict) -> dict:
    """A sandbox result recorded by experiments.sandbox_batch, for configs with `sandbox: true`.

    A missing result is an incomplete sandbox run, which blocks automatic approval (never an approve)."""
    if not config.get("sandbox") or "sandbox_result" not in item:
        return {}
    recorded = item["sandbox_result"] or {"ok": False, "data": None, "error": "no sandbox result recorded"}
    return {"sandbox_recorded": recorded}


def run_one(item: dict, run_dir: Path, config: dict, contexts: Path | None, analyze=agent_run.analyze) -> dict:
    started = time.monotonic()
    result = {"package": item["package"], "variant": config["name"], "model": config["model"]}
    fetched = None
    try:
        if "dir" in item:
            package_dir = str(item["dir"])
        else:
            fetched = fetch_package(item["name"], item["version"])
            if not fetched["ok"]:
                raise RuntimeError(f"fetch failed: {fetched['error']}")
            package_dir = fetched["data"]["dir"]
        context = item.get("context")  # run_isolated sends the host-built context with the row
        if contexts:
            path = contexts / result_name(item["package"])
            context = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
        writer = TraceWriter(run_dir, item["package"])
        result["trace"] = writer.path.name
        try:
            verdict, steps = analyze(package_dir, config["model"], config["max_steps"], trace=writer,
                                     deny_threshold=config["deny_threshold"],
                                     approve_threshold=config["approve_threshold"], context=context,
                                     options=config["options"],
                                     **sandbox_kwargs(item, config),
                                     **{key: config[key] for key in FEATURE_TYPES if key in config})
            result.update(status="ok", steps=steps, verdict=verdict.model_dump())
        except Exception as error:  # the trace already holds the R2 fallback decision
            result.update(status="error", error=str(error)[:300])
        events = [json.loads(line) for line in writer.path.read_text(encoding="utf-8").splitlines()]
        decision = next((event for event in reversed(events) if event["type"] == "decision"), None)
        end = next((event for event in reversed(events) if event["type"] == "run_end"), {})
        result["steps"] = end.get("steps", result.get("steps"))
        result["errors"] = [event["kind"] for event in events if event["type"] == "error"]
        if decision:
            result["decision"] = {"label": decision["final_label"], "action": decision["final_action"],
                                  "rule": decision["rule"], "reasons": decision["reasons"]}
            planned = apply_decision(package_dir, item["package"], {"action": decision["final_action"],
                                                                    "rule": decision["rule"]})
            result["planned_command"] = planned["data"]["command"] if planned["ok"] else None
    except Exception as error:  # fetch or setup failure; keep the batch going
        result.update(status="error", error=str(error)[:300])
    finally:
        if fetched and fetched["ok"]:
            shutil.rmtree(Path(fetched["data"]["dir"]).parent, ignore_errors=True)
    result["elapsed_s"] = round(time.monotonic() - started, 1)
    return result


def run_batch(run_id: str, variant: str, inputs: list[dict], reports: Path = Path("reports"),
              labels: Path | None = None, contexts: Path | None = None, analyze=agent_run.analyze) -> dict:
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("invalid run id")
    config = load_config(variant)
    run_dir = reports / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    meta_path = run_dir / "run_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else run_meta(run_id, config, inputs, labels)
    if meta["config"] != config:
        raise ValueError("run_id was started with a different config; use a new run id")
    meta.setdefault("resumed_at", [])
    if meta_path.is_file():
        meta["resumed_at"].append(datetime.now(timezone.utc).isoformat())
    counts = {"done": 0, "skipped": 0, "errors": 0}
    for item in inputs:
        output = run_dir / result_name(item["package"])
        if output.is_file():
            counts["skipped"] += 1
            continue
        trace = run_dir / trace_filename(item["package"])
        if trace.is_file():
            trace.unlink()  # an interrupted attempt left a partial trace; rerun it from the start
        result = run_one(item, run_dir, config, contexts, analyze)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        counts["done"] += 1
        counts["errors"] += result["status"] == "error"
        print(json.dumps({key: result.get(key) for key in ("package", "status", "steps", "decision", "elapsed_s")},
                         ensure_ascii=False), flush=True)
    meta.update(finished_at=datetime.now(timezone.utc).isoformat(), last_counts=counts)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return counts


def main() -> None:
    # Model text and reasons are not limited to the console code page (cp1252 on Windows); a
    # character it cannot show must not stop a batch (2026-11-08: '→' did).
    sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Run the agent over packages; resumes an existing run id")
    parser.add_argument("run_id")
    parser.add_argument("variant", choices=variants())
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--split", choices=("dev", "test"))
    parser.add_argument("--name", action="append", default=[], help="limit to these package names")
    parser.add_argument("--dir", action="append", type=Path, default=[], help="already extracted package directory")
    parser.add_argument("--contexts", type=Path, help="directory of tools.intel context JSON files")
    parser.add_argument("--isolated", action="store_true", help="allow non-benign rows; only inside an isolated VM")
    parser.add_argument("--reports", type=Path, default=Path("reports"))
    args = parser.parse_args()
    inputs = select_inputs(args.labels, args.split, args.name, args.dir, args.isolated)
    if not inputs:
        sys.exit("no packages selected")
    print(json.dumps(run_batch(args.run_id, args.variant, inputs, args.reports, args.labels, args.contexts)))


if __name__ == "__main__":
    main()
