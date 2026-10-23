"""Execute only inside a restricted, offline Docker container."""

import subprocess
from pathlib import Path


def run_sandbox(package: Path) -> dict:
    try:
        root = package.resolve(strict=True)
        if not root.is_dir() or not (root / "package.json").is_file():
            raise ValueError("package directory required")
        result = subprocess.run([
            "docker", "run", "--rm", "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", "64", "--memory", "256m", "--cpus", "1",
            "--user", "10001:10001", "--tmpfs", "/work:rw,exec,nosuid,size=64m,uid=10001,gid=10001",
            "--mount", f"type=bind,source={root},target=/input,readonly",
            "node:22-alpine", "sh", "-c",
            "cp -R /input/. /work/ && cd /work && npm install --offline --no-audit --no-fund",
        ], capture_output=True, text=True, timeout=120, check=False)
        return {"ok": result.returncode == 0, "data": {
            "returncode": result.returncode,
            "stdout": {"untrusted": True, "content": result.stdout[-4000:]},
            "stderr": {"untrusted": True, "content": result.stderr[-4000:]},
        }, "error": None if result.returncode == 0 else "sandbox execution failed"}
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return {"ok": False, "data": None, "error": str(error)[:300]}
