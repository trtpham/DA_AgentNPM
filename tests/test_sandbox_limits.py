"""W5-1: harmless fixtures that each try to cross one sandbox limit, run only inside Docker.

Opt in with RUN_SANDBOX_TESTS=1 after `docker build -t agent-npm-sandbox:local sandbox`;
the timeout fixture alone takes about a minute.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

from sandbox.run import IMAGE, run_sandbox

FIXTURES = Path(__file__).parent / "fixtures" / "sandbox-limits"


def _image_ready() -> bool:
    try:
        return subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


pytestmark = pytest.mark.skipif(os.environ.get("RUN_SANDBOX_TESTS") != "1" or not _image_ready(),
                                reason="set RUN_SANDBOX_TESTS=1 and build agent-npm-sandbox:local")


def run(name: str) -> tuple[dict, dict[str, str]]:
    result = run_sandbox(FIXTURES / name)
    assert result["data"] is not None, result["error"]
    stdout = result["data"]["stdout"]["content"]
    values = {}
    for line in stdout.splitlines():
        if line.startswith("W5RESULT "):
            values.update(re.findall(r"(\S+)=(\S+)", line))
    return result, values


def test_network_is_unreachable():
    result, values = run("network")
    assert values["dns"] != "resolved" and values["https"] != "connected"
    assert result["data"]["network_attempts"], "attempts must still be recorded"
    # W5-3: the package's own attempts are separated from npm's nscd/DNS lookups.
    assert result["data"]["by_actor"]["package"]["network_count"] > 0
    assert result["data"]["outcome"] == "ok"


def test_process_limit_refuses_children():
    result, values = run("processes")
    assert int(values["refused"]) > 0
    assert result["data"]["outcome"] == "pids_limit" and not result["ok"]


def test_memory_limit_stops_the_script():
    result, values = run("memory")
    assert "memory" not in values and not result["ok"]
    assert int(values.get("allocated_mb", "0")) < 512
    assert result["data"]["outcome"] == "oom" and result["error"] == "sandbox out of memory"


def test_timeout_stops_a_long_script():
    result, values = run("timeout")
    assert values["waiting"] == "120" and "timeout" not in values
    assert result["data"]["returncode"] == 124 and not result["ok"]
    assert result["data"]["outcome"] == "timeout"


def test_writes_outside_the_package_fail_or_are_recorded():
    result, values = run("write-outside")
    assert values["/input/w5-marker"] == "EROFS"
    assert values["/etc/w5-marker"] in ("EROFS", "EACCES")
    assert values["/usr/local/w5-marker"] in ("EROFS", "EACCES")
    # $HOME is a small writable tmpfs inside the container; the write must at least be visible.
    assert "/home/agent/w5-marker" in result["data"]["files_outside_package"]


def test_every_fake_canary_is_detected():
    result, values = run("canary-all")
    assert {values[".npmrc"], values[".ssh/id_rsa"], values[".aws/credentials"]} == {"ok"}
    assert set(result["data"]["canary_touched"]) >= {"npmrc", "ssh", "aws", "environment"}
    package_files = result["data"]["by_actor"]["package"]["files_outside_package"]
    assert {"/home/agent/.npmrc", "/home/agent/.ssh/id_rsa", "/home/agent/.aws/credentials"} <= set(package_files)


@pytest.mark.parametrize("name", ["benign-package", "no-hook-package"])
def test_harmless_fixtures_have_no_package_network(name):
    result = run_sandbox(Path(__file__).parent / "fixtures" / "packages" / name)
    assert result["ok"] and result["data"]["outcome"] == "ok"
    actors = result["data"]["by_actor"]
    assert actors["package"]["network_count"] == 0 and actors["npm"]["network_count"] > 0
