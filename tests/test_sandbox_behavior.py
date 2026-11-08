"""C2 canaries, C4 behavior from strace logs, C6 opt-in hardening, C7 sandbox in the agent (fake runner).

Nothing here starts Docker: logs are hand-written or recorded fixtures, and the runner is a stub.
"""

import base64
import json
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from agent.run import analyze, tool_schemas
from agent.trace import TraceWriter
from sandbox.run import CANARY, behavior_events, docker_command, run_sandbox, touched_canaries

FIXTURES = Path(__file__).parent / "fixtures"
CANARY_DIR = Path(__file__).parents[1] / "sandbox" / "canary"


def _log(name: str) -> str:
    return (FIXTURES / "strace" / name).read_text(encoding="utf-8")


# C2

def test_every_canary_file_exists_is_fake_and_unique():
    values = []
    for item in CANARY["files"]:
        path = CANARY_DIR / item["path"].removeprefix("/home/agent/")
        text = path.read_text(encoding="utf-8")
        assert "CANARY_" in text, item["name"]
        values.append(next(word for word in text.replace('"', " ").replace("@", " ").replace(":", " ").split()
                           if "CANARY_" in word))
    values += list(CANARY["environment_vars"].values())
    assert len(set(values)) == len(values) == 11
    assert all("FAKE" in value for value in values)


def test_env_canary_in_output_or_process_arguments_is_touched():
    value = CANARY["environment_vars"]["NPM_TOKEN"]
    assert touched_canaries(set(), "", f"token={value}", "") == ["env:NPM_TOKEN"]
    trace = f'7 execve("/bin/sh", ["sh", "-c", "echo {value}"], 0x1 /* 3 vars */) = 0'
    assert touched_canaries({"/home/agent/.kube/config"}, trace, "", "") == ["kube", "env:NPM_TOKEN"]
    assert touched_canaries(set(), "", "nothing", "") == []


def test_docker_command_keeps_core_flags_and_passes_fake_env():
    command = docker_command(Path("/pkg"))
    assert command[command.index("--network") + 1] == "none"
    assert command[command.index("--memory") + 1] == "256m"
    assert "size=1m" in command[command.index("--tmpfs", command.index("--tmpfs") + 1) + 1]
    assert f"NPM_TOKEN={CANARY['environment_vars']['NPM_TOKEN']}" in command
    assert "--ulimit" not in command  # C6 is opt-in


def test_hardening_adds_limits_only_when_asked():
    command = docker_command(Path("/pkg"), hardening=True)
    assert "nofile=256:256" in command and command[command.index("--memory-swap") + 1] == "256m"
    assert not any(part.startswith("/tmp") for part in command)  # a /tmp tmpfs would loosen --read-only
    assert command[-2:] == ["agent-npm-sandbox:local", "/usr/local/bin/run_install.sh"]


# C4

def test_behavior_events_from_hand_written_log():
    behavior = behavior_events(_log("persist.log"))
    assert [(item["ip"], item["port"], item["actor"], item["dns"]) for item in behavior["connects"]] == [
        ("203.0.113.40", 4444, "package", False), ("192.0.2.53", 53, "package", True), ("2001:db8::1", 443, "npm", False)]
    assert [(item["path"], item["result"], item["actor"]) for item in behavior["persistence_writes"]] == [
        ("/home/agent/.bashrc", "ok", "package"), ("/etc/profile.d/sim.sh", "EROFS", "package"),
        ("/home/agent/.zshrc", "ok", "package")]
    tree = behavior["process_tree"]
    assert [(item["pid"], item["ppid"], item["actor"]) for item in tree] == [(101, 100, "package"), (102, 101, "package"),
                                                                            (100, None, "npm")]
    assert tree[1]["argv"] == ["node", "warm.js"]


@pytest.mark.parametrize("name", ["benign.log", "canary.log", "no-hook.log"])
def test_recorded_harmless_logs_have_no_persistence(name):
    assert behavior_events(_log(name))["persistence_writes"] == []


def test_run_sandbox_reports_behavior(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    encoded = base64.b64encode(_log("persist.log").encode()).decode()
    output = f"EXIT=0\nTRACE_TRUNCATED=0\nTRACE={encoded}\nSTDOUT=\nSTDERR=\n"
    with patch("sandbox.run.subprocess.run", return_value=CompletedProcess([], 0, output, "")):
        data = run_sandbox(tmp_path)["data"]
    assert data["behavior"]["persistence_writes"][0]["path"] == "/home/agent/.bashrc"
    assert data["by_actor"]["package"]["network_count"] == 1  # unchanged W5-3 field: connect() only


# C7

def _fake_result(canaries=(), writes=(), ok=True, outcome="ok"):
    return {"ok": ok, "error": None if ok else "sandbox timed out", "data": {
        "outcome": outcome, "canary_touched": list(canaries),
        "behavior": {"connects": [], "process_tree": [],
                     "persistence_writes": [{"path": path, "result": "ok", "actor": "package"} for path in writes]},
        "by_actor": {"package": {"files_outside_package": []}}}}


def _benign(file="postinstall.js", lines="2", technique="write-package-file"):
    return {"role": "assistant", "content": json.dumps({
        "package": "x", "label": "benign", "confidence": 0.95, "description": "Writes a build marker next to the package",
        "behaviors": [{"behavior": "Writes a marker", "technique": technique, "severity": "low",
                       "evidence": {"file": file, "lines": lines}, "analysis": "Local file.", "impact": "None."}],
        "action": "approve", "remediation": []})}


def _run(tmp_path, runner, replies, **kwargs):
    replies = iter(replies)
    seen = []

    def chat(_model, messages, final=False):
        seen.append(list(messages))
        return next(replies)

    writer = TraceWriter(tmp_path / "reports" / "run-1", "benign-package")
    result, _ = analyze(str(FIXTURES / "packages" / "benign-package"), "fake", chat=chat, trace=writer, sandbox=True,
                        sandbox_runner=runner, **kwargs)
    events = [json.loads(line) for line in writer.path.read_text(encoding="utf-8").splitlines()]
    return result, next(event for event in events if event["type"] == "decision"), seen


READ = {"role": "assistant", "tool_calls": [{"function": {"name": "read_file", "arguments": {"file": "postinstall.js"}}}]}
REPORT = {"role": "assistant", "tool_calls": [{"function": {"name": "sandbox_report", "arguments": {}}}]}


def test_canary_touched_in_sandbox_denies_even_a_benign_verdict(tmp_path):
    result, decision, _ = _run(tmp_path, lambda _package: _fake_result(canaries=["npmrc"]), [READ, _benign()])
    assert (result.label, result.action, decision["rule"]) == ("malicious", "deny", "R1")


def test_startup_file_write_blocks_approval(tmp_path):
    _, decision, _ = _run(tmp_path, lambda _package: _fake_result(writes=["/home/agent/.bashrc"]), [READ, _benign()])
    assert decision["rule"] == "R7_sandbox" and ".bashrc" in decision["reasons"][0]


def test_clean_sandbox_keeps_approval_and_report_is_readable(tmp_path):
    result, decision, seen = _run(tmp_path, lambda _package: _fake_result(), [READ, REPORT, _benign()])
    assert (result.action, decision["rule"]) == ("approve", "R7")
    report = [message for message in seen[-1] if message.get("tool_name") == "sandbox_report"][0]["content"]
    assert '"untrusted": true' in report and '"outcome": "ok"' in report


def test_failed_sandbox_blocks_approval_and_runner_error_is_contained(tmp_path):
    _, decision, _ = _run(tmp_path, lambda _package: _fake_result(ok=False, outcome="timeout"), [READ, _benign()])
    assert decision["rule"] == "R7_review" and "sandbox run incomplete" in decision["reasons"][0]

    def broken(_package):
        raise OSError("docker missing")

    _, decision, _ = _run(tmp_path / "b", broken, [READ, _benign()])
    assert decision["rule"] == "R7_review"


def test_sandbox_is_off_by_default_and_only_for_fixtures(tmp_path):
    assert "sandbox_report" not in [item["function"]["name"] for item in tool_schemas()]
    with pytest.raises(ValueError, match="tests/fixtures"):
        analyze(str(tmp_path), "fake", sandbox=True, sandbox_runner=lambda _package: _fake_result())
    # The simulated-malicious corpus is never run in a container (Gate B0 2026-11-07, plan Q1).
    with pytest.raises(ValueError, match="tests/fixtures/packages"):
        analyze(str(FIXTURES / "corpus" / "twin-safe"), "fake", sandbox=True,
                sandbox_runner=lambda _package: _fake_result())
    with pytest.raises(ValueError, match="sandbox=True"):
        analyze(str(FIXTURES / "corpus" / "twin-safe"), "fake", tools=["read_file", "sandbox_report"])
