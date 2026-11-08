import io
import json
import zipfile
from subprocess import CompletedProcess

import pytest

from experiments import run_isolated as iso


def test_container_is_disposable_and_only_reaches_local_ollama():
    command = iso.container_command()
    assert "--read-only" in command and "ALL" in command and "no-new-privileges" in command
    assert "AGENT_OLLAMA_HOST=host.docker.internal" in command
    assert all(part.endswith(",readonly") for part in command if part.startswith("type=bind"))
    with pytest.raises(ValueError):
        iso._get("https://example.invalid/x.tgz")


def test_ollama_host_accepts_only_local_names(monkeypatch):
    from agent.run import ollama_host
    monkeypatch.delenv("AGENT_OLLAMA_HOST", raising=False)
    assert ollama_host() == "127.0.0.1"
    monkeypatch.setenv("AGENT_OLLAMA_HOST", "host.docker.internal")
    assert ollama_host() == "host.docker.internal"
    monkeypatch.setenv("AGENT_OLLAMA_HOST", "api.example.com")
    with pytest.raises(RuntimeError):
        ollama_host()


def test_materialize_zip_sources(monkeypatch, tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.writestr("demo-1.0.0/package.json", json.dumps({"name": "demo", "version": "1.0.0"}))
        zipped.writestr("demo-1.0.0/i.js", "1;\n")
    monkeypatch.setattr(iso, "_get", lambda url: buffer.getvalue())
    row = {"name": "demo", "version": "1.0.0", "source": "https://raw.githubusercontent.com/DataDog/x.zip"}
    target = iso.materialize(row, tmp_path / "work")
    assert (target / "i.js").read_text() == "1;\n"


def test_run_writes_reports_layout_and_resumes(tmp_path, monkeypatch):
    from experiments import run_batch as batch
    monkeypatch.setattr(batch, "run_meta", lambda run_id, config, inputs, labels: {"config": config})
    rows = [{"name": "a", "version": "1.0.0", "source": "s"}, {"name": "b", "version": "1.0.0", "source": "s"}]
    calls = []

    def runner(command, input, **_kwargs):
        calls.append(len(input.splitlines()))
        outputs = [{"result": {"package": f"{json.loads(line)['row']['name']}@1.0.0", "status": "ok", "trace": "t.jsonl"},
                    "trace": '{"type": "run_start"}'} for line in input.splitlines()]
        return CompletedProcess(command, 0, "\n".join(map(json.dumps, outputs)), "")

    assert iso.run("iso-1", "A-TLM", rows, tmp_path, runner) == {"done": 2, "skipped": 0, "errors": 0}
    assert (tmp_path / "iso-1" / "a@1.0.0.json").is_file() and (tmp_path / "iso-1" / "t.jsonl").is_file()
    assert iso.run("iso-1", "A-TLM", rows, tmp_path, runner)["skipped"] == 2 and calls == [2]


def test_guarddog_mode_uses_its_image_without_ollama_and_writes_baseline_layout(tmp_path):
    command = iso.container_command(guarddog=True)
    assert iso.GUARDDOG_IMAGE in command and "--guarddog" in command
    assert not any("AGENT_OLLAMA_HOST" in part for part in command)

    def runner(command, input, **_kwargs):
        rows = [json.loads(line)["row"] for line in input.splitlines()]
        outputs = [{"result": {"ok": True, "data": {"issues": 0, "rules": []}, "error": None,
                               "package": f"{row['name']}@{row['version']}"}, "trace": None} for row in rows]
        return CompletedProcess(command, 0, "\n".join(map(json.dumps, outputs)), "")

    rows = [{"name": "a", "version": "1.0.0", "source": "s"}]
    assert iso.run_guarddog("gd-1", rows, tmp_path, runner) == {"done": 1, "skipped": 0, "errors": 0}
    assert (tmp_path / "gd-1" / "guarddog" / "a@1.0.0.json").is_file()
    assert (tmp_path / "gd-1" / "guarddog" / "guarddog_meta.json").is_file()


def test_guarddog_findings_keep_location_but_not_code():
    result = {"ok": True, "error": None, "data": {"issues": 1, "rules": ["shady-links"], "errors": {},
              "results": {"shady-links": [{"location": "a.js:7", "code": "const u = 'https://x';", "message": "m"}],
                          "other": []}}}
    stripped = iso.strip_code(result)
    assert stripped["data"]["results"]["shady-links"] == [{"location": "a.js:7", "message": "m"}]
    assert stripped["data"]["issues"] == 1 and iso.strip_code({"ok": False, "data": None}) == {"ok": False, "data": None}


def test_metrics_lists_unreadable_files_instead_of_stopping(tmp_path, monkeypatch):
    from pathlib import Path
    from experiments.metrics import load_results
    (tmp_path / "a@1.json").write_text('{"package": "a@1"}', encoding="utf-8")
    (tmp_path / "b@1.json").write_text('{"package": "b@1"}', encoding="utf-8")
    original = Path.read_text

    def blocked(self, *args, **kwargs):
        if self.name == "b@1.json":
            raise OSError(22, "Invalid argument")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", blocked)
    unreadable = []
    assert load_results(tmp_path, unreadable) == [{"package": "a@1"}] and unreadable == ["b@1.json"]
