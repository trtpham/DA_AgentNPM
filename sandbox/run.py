"""Execute only inside a restricted, offline Docker container."""

import argparse
import base64
import binascii
import json
import re
import subprocess
import tempfile
from pathlib import Path

IMAGE = "agent-npm-sandbox:local"
CANARY = json.loads((Path(__file__).parent / "canary" / "manifest.json").read_text(encoding="utf-8"))
OPEN = re.compile(r'\bopen(?:at|at2)?\([^"\n]*"([^"\n]+)"[^\n]*\)\s+=\s+\d+')


def _field(output: str, key: str) -> str:
    values = [part[len(key) + 1:] for part in output.splitlines() if part.startswith(key + "=")]
    if len(values) != 1:
        raise ValueError(f"invalid sandbox {key} output")
    return values[0]


def _decode(output: str, key: str) -> str:
    value = _field(output, key)
    if len(value) > 2_700_000:
        raise ValueError(f"invalid sandbox {key} output")
    return base64.b64decode(value, validate=True).decode("utf-8", errors="replace")


def run_sandbox(package: Path) -> dict:
    try:
        root = package.resolve(strict=True)
        if not root.is_dir() or not (root / "package.json").is_file():
            raise ValueError("package directory required")
        result = subprocess.run([
            "docker", "run", "--rm", "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--cap-add", "SYS_PTRACE",
            "--security-opt", "no-new-privileges",
            "--pids-limit", "64", "--memory", "256m", "--cpus", "1",
            "--user", "10001:10001", "--tmpfs", "/work:rw,exec,nosuid,size=64m,uid=10001,gid=10001",
            "--tmpfs", "/home/agent:rw,noexec,nosuid,size=1m,uid=10001,gid=10001",
            "--mount", f"type=bind,source={root},target=/input,readonly",
            "--env", f"CANARY_ENV={CANARY['environment']}",
            IMAGE, "/usr/local/bin/run_install.sh",
        ], capture_output=True, text=True, timeout=120, check=False)
        if result.returncode:
            raise RuntimeError(f"Docker failed: {result.stderr[-300:]}")
        status = int(_field(result.stdout, "EXIT"))
        trace_truncated = _field(result.stdout, "TRACE_TRUNCATED")
        if trace_truncated not in ("0", "1"):
            raise ValueError("invalid sandbox TRACE_TRUNCATED output")
        trace = _decode(result.stdout, "TRACE")
        stdout = _decode(result.stdout, "STDOUT")
        stderr = _decode(result.stdout, "STDERR")
        trace_complete = trace_truncated == "0" and bool(trace.strip())
        opened = set(OPEN.findall(trace))
        touched = [item["name"] for item in CANARY["files"] if item["path"] in opened]
        if CANARY["environment"] in stdout or CANARY["environment"] in stderr:
            touched.append("environment")
        lines = trace.splitlines()
        return {"ok": status == 0 and trace_complete, "data": {
            "returncode": status,
            "stdout": {"untrusted": True, "content": stdout},
            "stderr": {"untrusted": True, "content": stderr},
            "strace": {"untrusted": True, "content": trace,
                       "truncated": trace_truncated == "1"},
            "processes": [line[:300] for line in lines if "execve(" in line][:20],
            "files_outside_package": sorted(path for path in opened if path.startswith("/")
                                            and not path.startswith("/work/"))[:50],
            "network_attempts": [line[:300] for line in lines if "connect(" in line][:20],
            "canary_touched": touched,
        }, "error": "sandbox trace incomplete" if not trace_complete else None if status == 0 else "sandbox execution failed"}
    except (OSError, ValueError, KeyError, RuntimeError, binascii.Error,
            subprocess.SubprocessError) as error:
        return {"ok": False, "data": None, "error": str(error)[:300]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a harmless fixture in the offline sandbox")
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    result = run_sandbox(args.package)
    if result["data"]:
        output_root = Path(__file__).parent / "out"
        output_root.mkdir(exist_ok=True)
        output = Path(tempfile.mkdtemp(prefix="trace-", dir=output_root)) / "strace.log"
        output.write_text(result["data"]["strace"]["content"], encoding="utf-8")
        result["data"]["strace"]["path"] = str(output)
        result["data"]["strace"].pop("content")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
