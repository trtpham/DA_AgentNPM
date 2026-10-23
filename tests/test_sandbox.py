from subprocess import CompletedProcess
from unittest.mock import patch

from sandbox.run import run_sandbox


def test_sandbox_command_is_offline_and_read_only(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    with patch("sandbox.run.subprocess.run", return_value=CompletedProcess([], 0, "ok", "")) as run:
        assert run_sandbox(tmp_path)["ok"]
    command = run.call_args.args[0]
    assert command[:3] == ["docker", "run", "--rm"]
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command and "--cap-drop" in command
    assert "target=/input,readonly" in command[command.index("--mount") + 1]
