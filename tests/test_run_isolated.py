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


class _FakeSampler:
    def __init__(self, peaks):
        self.peaks = peaks

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None


def _echo_runner(seen):
    def runner(command, input, **_kwargs):
        outputs = []
        for line in input.splitlines():
            job = json.loads(line)
            seen.append(job)
            outputs.append({"result": {"package": f"{job['row']['name']}@1.0.0", "status": "ok",
                                       "container_peak_mb": 300.0 + len(seen)}, "trace": None})
        return CompletedProcess(command, 0, "\n".join(map(json.dumps, outputs)), "")
    return runner


def test_contexts_are_built_on_host_once_and_osv_failures_are_not_cached(tmp_path):
    rows = [{"name": "a", "version": "1.0.0"}, {"name": "b", "version": "1.0.0"}]
    calls = []

    def build(name, version):
        calls.append(name)
        return {"package": f"{name}@{version}", "osv": {"ok": name == "a", "data": {}, "error": None},
                "registry": {"ok": False, "data": None, "error": "HTTP 404"}}

    first = iso.ensure_contexts(rows, tmp_path / "ctx", build)
    assert first == {"built": 1, "cached": 0, "failed": ["b@1.0.0"]}
    assert (tmp_path / "ctx" / "a@1.0.0.json").is_file() and not (tmp_path / "ctx" / "b@1.0.0.json").exists()
    assert iso.ensure_contexts(rows, tmp_path / "ctx", build)["cached"] == 1 and calls == ["a", "b", "b"]


def test_run_sends_context_into_container_and_records_resources(tmp_path, monkeypatch):
    from experiments import run_batch as batch
    monkeypatch.setattr(batch, "run_meta", lambda run_id, config, inputs, labels: {"config": config})
    contexts = tmp_path / "ctx"
    contexts.mkdir()
    (contexts / "a@1.0.0.json").write_text(json.dumps({"osv": {"ok": True, "data": {"malicious": True}}}))
    rows = [{"name": "a", "version": "1.0.0", "source": "s"}, {"name": "b", "version": "1.0.0", "source": "s"}]
    seen = []
    sampler = _FakeSampler({"qwen3.5:0.8b": {"size_mb": 900.0, "vram_mb": 900.0}})
    iso.run("iso-ctx", "A-TLM", rows, tmp_path, _echo_runner(seen), contexts=contexts, sampler=sampler)
    assert seen[0]["context"]["osv"]["data"]["malicious"] is True and seen[1]["context"] is None
    meta = json.loads((tmp_path / "iso-ctx" / "run_meta.json").read_text())
    assert meta["contexts"] == str(contexts) and meta["contexts_missing"] == ["b@1.0.0"]
    assert meta["resources"]["container_peak_mb"] == 302.0
    assert meta["resources"]["ollama"]["qwen3.5:0.8b"]["size_mb"] == 900.0
    with pytest.raises(ValueError, match="contexts"):
        iso.run("iso-ctx", "A-TLM", rows, tmp_path, _echo_runner([]), contexts=None, sampler=sampler)


def test_inside_passes_context_to_agent_and_reports_container_peak(monkeypatch, tmp_path):
    from experiments import resources, run_batch as batch
    got = {}

    def fake_run_one(item, run_dir, config, contexts):
        got.update(item)
        return {"package": item["package"], "status": "ok"}

    monkeypatch.setattr(batch, "run_one", fake_run_one)
    monkeypatch.setattr(iso, "materialize", lambda row, work: tmp_path)
    monkeypatch.setattr(resources, "container_peak_mb", lambda: 123.4)
    out = iso.inside({"row": {"name": "a", "version": "1.0.0"}, "config": {"name": "A-TLM", "model": "m"},
                      "context": {"osv": {"ok": True}}})
    assert got["context"] == {"osv": {"ok": True}} and out["result"]["container_peak_mb"] == 123.4
