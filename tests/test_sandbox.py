import base64
from subprocess import CompletedProcess
from unittest.mock import patch

from sandbox.run import run_sandbox


def test_sandbox_command_is_offline_and_read_only(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    trace = '1 execve("/usr/bin/node", [], []) = 0\n1 openat(AT_FDCWD, "/home/agent/.ssh/id_rsa", O_RDONLY) = 3\n1 connect(3, 0, 0) = -1 ENETUNREACH\n'
    encoded = lambda value: base64.b64encode(value.encode()).decode()
    output = f"EXIT=0\nTRACE_TRUNCATED=0\nTRACE={encoded(trace)}\nSTDOUT={encoded('fixture')}\nSTDERR=\n"
    with patch("sandbox.run.subprocess.run", return_value=CompletedProcess([], 0, output, "")) as run:
        result = run_sandbox(tmp_path)
    assert result["ok"]
    assert result["data"]["canary_touched"] == ["ssh"]
    assert result["data"]["network_attempts"]
    assert result["data"]["processes"]
    command = run.call_args.args[0]
    assert command[:3] == ["docker", "run", "--rm"]
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command and "--cap-drop" in command
    assert "target=/input,readonly" in command[command.index("--mount") + 1]
    assert "SYS_PTRACE" in command and "agent-npm-sandbox:local" in command


def test_sandbox_rejects_invalid_trace_protocol(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    with patch("sandbox.run.subprocess.run", return_value=CompletedProcess([], 0, "EXIT=0\nTRACE=bad\n", "")):
        result = run_sandbox(tmp_path)
    assert not result["ok"] and result["data"] is None


def test_sandbox_rejects_duplicate_trace_field(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    output = "EXIT=0\nTRACE_TRUNCATED=0\nTRACE=\nTRACE=\nSTDOUT=\nSTDERR=\n"
    with patch("sandbox.run.subprocess.run", return_value=CompletedProcess([], 0, output, "")):
        result = run_sandbox(tmp_path)
    assert not result["ok"] and result["data"] is None


def test_sandbox_cannot_pass_with_truncated_trace(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    trace = base64.b64encode(b'1 openat(AT_FDCWD, "/work/file", O_RDONLY) = 3\n').decode()
    output = f"EXIT=0\nTRACE_TRUNCATED=1\nTRACE={trace}\nSTDOUT=\nSTDERR=\n"
    with patch("sandbox.run.subprocess.run", return_value=CompletedProcess([], 0, output, "")):
        result = run_sandbox(tmp_path)
    assert not result["ok"] and result["error"] == "sandbox trace incomplete"


# --- W5-2: outcome -------------------------------------------------------------------------------
from pathlib import Path

import pytest

from sandbox.run import attribute_events, classify_outcome

STRACE = Path(__file__).parent / "fixtures" / "strace"


def _output(status: int, trace: str, truncated: str = "0") -> str:
    encoded = base64.b64encode(trace.encode()).decode()
    return f"EXIT={status}\nTRACE_TRUNCATED={truncated}\nTRACE={encoded}\nSTDOUT=\nSTDERR=\n"


@pytest.mark.parametrize("status, trace, outcome, error", [
    (0, '1 openat(AT_FDCWD, "/work/a", O_RDONLY) = 3\n', "ok", None),
    (124, '1 openat(AT_FDCWD, "/work/a", O_RDONLY) = 3\n', "timeout", "sandbox timed out"),
    (137, '1 openat(AT_FDCWD, "/work/a", O_RDONLY) = 3\n', "oom", "sandbox out of memory"),
    (0, "7 clone(child_stack=NULL, flags=SIGCHLD) = -1 EAGAIN (Resource temporarily unavailable)\n",
     "pids_limit", "sandbox process limit reached"),
    (1, "7 <... vfork resumed>) = -1 EAGAIN (Resource temporarily unavailable)\n",
     "pids_limit", "sandbox process limit reached"),
    (1, '1 openat(AT_FDCWD, "/work/a", O_RDONLY) = 3\n', "failed", "sandbox execution failed"),
])
def test_outcome_names_why_the_run_stopped(tmp_path, status, trace, outcome, error):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    with patch("sandbox.run.subprocess.run", return_value=CompletedProcess([], 0, _output(status, trace), "")):
        result = run_sandbox(tmp_path)
    assert result["data"]["outcome"] == outcome
    assert result["error"] == error
    assert result["ok"] is (outcome == "ok")


def test_ok_needs_a_complete_trace_even_when_outcome_is_ok(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    output = _output(0, '1 openat(AT_FDCWD, "/work/a", O_RDONLY) = 3\n', truncated="1")
    with patch("sandbox.run.subprocess.run", return_value=CompletedProcess([], 0, output, "")):
        result = run_sandbox(tmp_path)
    assert result["data"]["outcome"] == "ok" and not result["data"]["trace_complete"]
    assert not result["ok"] and result["error"] == "sandbox trace incomplete"


def test_thread_creation_failing_with_enosys_is_not_a_process_limit():
    trace = "17 clone3({flags=CLONE_VM}, 88) = -1 ENOSYS (Function not implemented)\n"
    assert classify_outcome(0, trace) == "ok"


# --- W5-3: actor ---------------------------------------------------------------------------------
def _attribute(name: str) -> dict:
    return attribute_events((STRACE / f"{name}.log").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["benign", "no-hook", "canary"])
def test_npm_own_network_calls_are_not_charged_to_the_package(name):
    """Real traces from the sandbox fixtures: npm's nscd/DNS lookups belong to npm, not the package."""
    actors = _attribute(name)
    assert actors["package"]["network_count"] == 0
    assert actors["npm"]["network_count"] == 4
    assert all("nscd" in line or "htons(53)" in line for line in actors["npm"]["network_attempts"])
    assert actors["unknown"]["network_count"] == 0 and not actors["unknown"]["processes"]


def test_lifecycle_script_and_its_children_are_the_package():
    actors = _attribute("benign")
    commands = " ".join(actors["package"]["processes"])
    assert '"sh", "-c", "node postinstall.js"' in commands and '["node", "postinstall.js"]' in commands
    assert not any("postinstall" in line for line in actors["npm"]["processes"])


def test_no_hook_package_has_no_package_actor():
    actors = _attribute("no-hook")
    assert actors["package"] == {"processes": [], "network_attempts": [], "network_count": 0,
                                 "files_outside_package": []}


def test_canary_read_is_charged_to_the_package():
    actors = _attribute("canary")
    assert "/home/agent/.ssh/id_rsa" in actors["package"]["files_outside_package"]
    assert "/home/agent/.ssh/id_rsa" not in actors["npm"]["files_outside_package"]


def test_child_lines_before_parent_resume_and_threads_are_attributed():
    trace = "\n".join([
        '10 execve("/usr/local/bin/npm", ["npm", "install", "--offline"], 0x1 /* 8 vars */) = 0',
        "10 clone(child_stack=NULL, flags=SIGCHLD) = 20",
        '20 execve("/usr/bin/sh", ["sh", "-c", "node x.js"], 0x2 /* 3 vars */) = 0',
        "20 vfork( <unfinished ...>",
        '21 execve("/usr/local/bin/node", ["node", "x.js"], 0x3 /* 3 vars */ <unfinished ...>',
        "20 <... vfork resumed>) = 21",
        "21 <... execve resumed>) = 0",
        "21 clone(child_stack=0x1, flags=CLONE_VM|CLONE_THREAD) = 22",
        '22 connect(18, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("203.0.113.9")}, 16) = -1 ENETUNREACH',
        '99 connect(3, {sa_family=AF_INET, sin_port=htons(80), sin_addr=inet_addr("203.0.113.8")}, 16) = -1 ENETUNREACH',
    ])
    actors = attribute_events(trace)
    assert actors["package"]["network_count"] == 1 and "203.0.113.9" in actors["package"]["network_attempts"][0]
    assert any('["node", "x.js"]' in line for line in actors["package"]["processes"])
    # 99 has no known parent (cut from a truncated trace): never silently charged to npm.
    assert actors["unknown"]["network_count"] == 1 and actors["npm"]["network_count"] == 0


def test_orphan_exec_in_truncated_trace_is_not_taken_as_npm():
    trace = '50 execve("/bin/sleep", ["sleep", "5"], 0x1 /* 3 vars */) = 0\n50 connect(3, {}, 16) = -1 ENETUNREACH\n'
    actors = attribute_events(trace)
    assert actors["npm"]["network_count"] == 0 and actors["unknown"]["network_count"] == 1


def test_demo_table_row_reads_outcome_actor_and_canary():
    from experiments.demo_sandbox import row, table

    result = {"ok": False, "error": "sandbox timed out", "data": {
        "outcome": "timeout", "returncode": 124, "canary_touched": ["ssh"],
        "stdout": {"untrusted": True,
                   "content": "noise\nW5RESULT allocated_mb=32\nW5RESULT allocated_mb=64 waiting=120\n"},
        "by_actor": {"npm": {"network_count": 4}, "package": {"network_count": 0}, "unknown": {"network_count": 0}}}}
    assert row("timeout", result)[2:] == ("allocated_mb=64 waiting=120", "timeout", "✘", "124", "4/0/0", "ssh")
    assert row("network", {"ok": False, "error": "Docker failed", "data": None})[3] == "lỗi: Docker failed"
    assert "outcome" in table([row("timeout", result)]).splitlines()[0]
