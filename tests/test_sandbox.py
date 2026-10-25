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
