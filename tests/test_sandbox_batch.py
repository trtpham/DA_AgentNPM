import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from experiments import run_batch as batch
from experiments import run_isolated as iso
from experiments import sandbox_batch as sb
from sandbox.run import docker_command

FULL = {"ok": True, "error": None, "data": {
    "returncode": 0, "outcome": "ok", "trace_complete": True, "canary_touched": ["ssh"],
    "behavior": {"connects": [], "persistence_writes": [], "process_tree": []},
    "by_actor": {"package": {"files_outside_package": ["/home/agent/.ssh/id_rsa"]}, "npm": {"files": ["x"]}},
    "stdout": {"untrusted": True, "content": "stolen"}, "strace": {"untrusted": True, "content": "raw"}}}


def test_volume_mount_is_read_only_subpath_and_names_are_checked():
    command = docker_command(None, volume="agentnpm-abc123")
    assert "type=volume,source=agentnpm-abc123,target=/input,readonly,volume-subpath=pkg" in command
    # 2026-11-20: the dependency cache from the prepare step is mounted read-only too.
    assert "type=volume,source=agentnpm-abc123,target=/cache,readonly,volume-subpath=npm-cache" in command
    assert "--network" in command and command[command.index("--network") + 1] == "none"
    for bad in ("other", "agentnpm-../x", "agentnpm-A"):
        with pytest.raises(ValueError):
            docker_command(None, volume=bad)
    with pytest.raises(ValueError):
        docker_command(Path("/pkg"), volume="agentnpm-a")


def test_prepare_container_writes_only_to_the_volume():
    command = iso.container_command(prepare_volume="agentnpm-a1")
    assert "--read-only" in command and "ALL" in command and "--prepare" in command
    assert "type=volume,source=agentnpm-a1,target=/home/runner" in command
    assert all(part.endswith(",readonly") for part in command if part.startswith("type=bind"))


def test_compact_drops_raw_text_keeps_what_the_agent_reads():
    out = sb.compact(FULL)
    assert out["ok"] and out["data"]["canary_touched"] == ["ssh"]
    assert out["data"]["by_actor"] == {"package": {"files_outside_package": ["/home/agent/.ssh/id_rsa"]}}
    assert "stdout" not in out["data"] and "strace" not in out["data"]
    assert sb.compact({"ok": False, "data": None, "error": "Docker failed"}) == {"ok": False, "data": None,
                                                                                 "error": "Docker failed"}


def test_run_creates_and_always_removes_volumes_and_resumes(tmp_path):
    calls = []

    def docker(command, **kwargs):
        calls.append(command[:3] if command[1] == "volume" else ["prepare"])
        if command[1] == "volume":
            return CompletedProcess(command, 0, "", "")
        row = json.loads(kwargs["input"])["row"]
        ok = row["name"] != "broken"
        return CompletedProcess(command, 0, json.dumps({"ok": ok, "error": None if ok else "source: bad"}), "")

    rows = [{"name": "a", "version": "1.0.0"}, {"name": "broken", "version": "1.0.0"}]
    cached = []
    cache = lambda volume: cached.append(volume) or {"ok": False, "error": "npm exit 1: E404"}
    counts = sb.run("sbx-1", rows, tmp_path, docker, sandbox=lambda volume: FULL, cache=cache)
    assert counts["done"] == 2 and counts["prepare_failed"] == 1 and counts["canary"] == 1
    # The cache step runs only after a good prepare; its failure is recorded and the sandbox still runs.
    assert cached == [sb.volume_name("sbx-1", "a@1.0.0")] and counts["cache_failed"] == 1
    assert [c for c in calls if c[0] == "docker" and c[2] == "rm"].__len__() == 2
    saved = json.loads((tmp_path / "sbx-1" / "sandbox" / "a@1.0.0.json").read_text())
    assert saved["ok"] and "strace" not in saved["data"]
    assert saved["dependencies"] == {"ok": False, "error": "npm exit 1: E404"}
    assert json.loads((tmp_path / "sbx-1" / "sandbox" / "broken@1.0.0.json").read_text())["ok"] is False
    assert sb.run("sbx-1", rows, tmp_path, docker, sandbox=lambda volume: FULL, cache=cache)["skipped"] == 2


def test_run_removes_volume_even_when_sandbox_raises(tmp_path):
    removed = []

    def docker(command, **kwargs):
        if command[1:3] == ["volume", "rm"]:
            removed.append(command[-1])
        out = json.dumps({"ok": True, "error": None}) if command[1] != "volume" else ""
        return CompletedProcess(command, 0, out, "")

    def boom(volume):
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        sb.run("sbx-2", [{"name": "a", "version": "1.0.0"}], tmp_path, docker, sandbox=boom,
               cache=lambda volume: {"ok": True})
    assert removed == [sb.volume_name("sbx-2", "a@1.0.0")]


def test_sandbox_results_reach_container_jobs_and_missing_ones_block(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "run_meta", lambda run_id, config, inputs, labels: {"config": config})
    results = tmp_path / "sbres"
    results.mkdir()
    (results / "a@1.0.0.json").write_text(json.dumps(sb.compact(FULL)))
    rows = [{"name": "a", "version": "1.0.0", "source": "s"}, {"name": "b", "version": "1.0.0", "source": "s"}]
    seen = []

    class Sampler:
        peaks = {}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

    def runner(command, input, **_):
        jobs = [json.loads(line) for line in input.splitlines()]
        seen.extend(jobs)
        return CompletedProcess(command, 0, "\n".join(json.dumps({"result": {"package": f"{j['row']['name']}@1.0.0",
                                                                             "status": "ok"}, "trace": None})
                                                     for j in jobs), "")

    iso.run("sbx-run", "A-TLM-XS", rows, tmp_path, runner, sampler=Sampler(), sandbox_results=results)
    assert seen[0]["sandbox"]["data"]["canary_touched"] == ["ssh"] and seen[1]["sandbox"] is None
    with pytest.raises(ValueError, match="sandbox"):
        iso.run("sbx-run2", "A-TLM-XS", rows, tmp_path, runner, sampler=Sampler())
    with pytest.raises(ValueError, match="sandbox"):
        iso.run("sbx-run3", "A-TLM-X", rows, tmp_path, runner, sampler=Sampler(), sandbox_results=results)
    kwargs = batch.sandbox_kwargs({"sandbox_result": None}, {"sandbox": True})
    assert kwargs["sandbox_recorded"]["ok"] is False
    assert batch.sandbox_kwargs({"sandbox_result": FULL}, {}) == {}


def test_recorded_result_is_accepted_outside_fixtures_but_a_runner_is_not(tmp_path):
    from agent.run import analyze
    with pytest.raises(ValueError, match="tests/fixtures"):
        analyze(str(tmp_path), "fake", sandbox=True, sandbox_runner=lambda _p: FULL)
    with pytest.raises(ValueError, match="either"):
        analyze(str(tmp_path), "fake", sandbox=True, sandbox_runner=lambda _p: FULL, sandbox_recorded=FULL)


def test_cache_step_has_network_but_never_runs_package_scripts():
    from sandbox.run import ROOT_DIR, cache_command
    command = cache_command("agentnpm-a1")
    assert "--network" not in command  # needs the registry; the sandbox step is the offline one
    assert "--read-only" in command and command[command.index("--cap-drop") + 1] == "ALL"
    assert "type=volume,source=agentnpm-a1,target=/vol" in command and not any("CANARY" in p for p in command)
    assert command[-1] == "/usr/local/bin/cache_deps.sh"
    script = (ROOT_DIR / "cache_deps.sh").read_text(encoding="utf-8")
    assert "npm install --ignore-scripts" in script and "/vol/npm-cache" in script
    with pytest.raises(ValueError):
        cache_command("agentnpm-../x")


def test_cache_dependencies_reads_exit_and_output():
    import base64
    from sandbox.run import cache_dependencies

    def runner(stdout, code=0):
        return lambda command, **_: CompletedProcess(command, code, stdout, "boom")
    ok = cache_dependencies("agentnpm-a1", runner("EXIT=0\nOUTPUT=\n"))
    assert ok == {"ok": True, "error": None}
    text = base64.b64encode(b"npm error code E404").decode()
    failed = cache_dependencies("agentnpm-a1", runner(f"EXIT=1\nOUTPUT={text}\n"))
    assert not failed["ok"] and "E404" in failed["error"]
    assert not cache_dependencies("agentnpm-a1", runner("", 125))["ok"]
    assert not cache_dependencies("agentnpm-a1", runner("EXIT=0\n"))["ok"]


def test_sandbox_installs_the_package_as_a_dependency_of_an_empty_project():
    from sandbox.run import ROOT_DIR
    script = (ROOT_DIR / "run_install.sh").read_text(encoding="utf-8")
    assert "npm install --offline --foreground-scripts" in script and "/work/package.tgz" in script
    assert 'cd /work/project' in script and "--cache \"$cache\"" in script
    assert "head -c" in script and "tail -c" in script  # long traces keep head and tail
