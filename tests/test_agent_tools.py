"""A11: per-model tool sets, hit lines counted as seen, blind tool results, L3 decoded evidence."""

import json

import pytest

from agent.run import (ALL_TOOLS, DEFAULT_TOOLS, EXPLORE_HINT, SYSTEM, TOOLS, _tool, analyze, tool_schemas)
from agent.semantics import BLIND_ALIAS
from agent.trace import TraceWriter
from experiments import run_batch as batch


def _package(tmp_path, setup: str, extra: dict | None = None):
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "tools-fixture", "version": "1.0.0", "scripts": {"postinstall": "node setup.js"}
    }, indent=2), encoding="utf-8")
    (tmp_path / "setup.js").write_text(setup, encoding="utf-8")
    for name, content in (extra or {}).items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    return str(tmp_path)


def _verdict(lines: str, technique: str, label: str = "suspicious") -> dict:
    return {"package": "x", "label": label, "confidence": 0.6, "description": "Install script loads a module by name",
            "behaviors": [{"behavior": "Loads a module", "technique": technique, "severity": "low",
                           "evidence": {"file": "setup.js", "lines": lines}, "analysis": "Cited line.",
                           "impact": "Local only."}],
            "action": "review", "remediation": ["Review the install script"]}


def _call(name: str, **arguments) -> dict:
    return {"role": "assistant", "tool_calls": [{"function": {"name": name, "arguments": arguments}}]}


def _decision(writer: TraceWriter) -> dict:
    return next(event for event in map(json.loads, writer.path.read_text(encoding="utf-8").splitlines())
                if event["type"] == "decision")


def test_default_tool_set_is_unchanged():
    assert tool_schemas() == TOOLS
    assert [item["function"]["name"] for item in tool_schemas(ALL_TOOLS)] == list(ALL_TOOLS)
    with pytest.raises(ValueError):
        tool_schemas(("read_file", "run_package"))
    with pytest.raises(ValueError):
        analyze("unused", "fake", tools=["no_such_tool"])


def test_dispatcher_allows_only_enabled_tools_with_strict_arguments(tmp_path):
    package = _package(tmp_path, "console.log('hi');\n")
    assert _tool(package, "list_files", {})["error"] == "invalid tool call"  # not enabled by default
    assert _tool(package, "list_files", {}, ALL_TOOLS)["ok"]
    assert _tool(package, "decode_literal", {"file": "setup.js", "line": 1}, ALL_TOOLS)["ok"]
    assert _tool(package, "decode_literal", {"file": "setup.js", "line": True}, ALL_TOOLS)["error"] == "invalid tool call"
    assert _tool(package, "decode_literal", {"file": "setup.js"}, ALL_TOOLS)["error"] == "invalid tool call"
    assert _tool(package, "search_code", {"text": "hi", "extra": 1}, ALL_TOOLS)["error"] == "invalid tool call"
    assert _tool(package, "search_code", "text", ALL_TOOLS)["error"] == "invalid tool call"


def test_search_hit_counts_as_seen_line_and_results_are_blind(tmp_path):
    package = _package(tmp_path, "const label = 'fixture';\nrequire('child_process').execFileSync('echo', [label]);\n",
                       {"README.md": "tools-fixture runs echo\n"})
    replies = iter([_call("read_file", file="setup.js", start=1, end=1), _call("search_code", text="execFileSync"),
                    _call("search_code", text="runs echo"),
                    {"role": "assistant", "content": json.dumps(_verdict("1-2", "execute-process"))}])
    seen = []

    def chat(_model, messages, final=False):
        seen.append(messages)
        return next(replies)

    writer = TraceWriter(tmp_path / "reports" / "run-1", "tools-fixture@1.0.0")
    analyze(package, "fake", chat=chat, trace=writer, tools=DEFAULT_TOOLS + ("search_code",))
    assert EXPLORE_HINT in seen[0][0]["content"] and seen[0][0]["content"] == SYSTEM + EXPLORE_HINT
    readme_hit = [message for message in seen[-1] if message.get("tool_name") == "search_code"][-1]["content"]
    assert "tools-fixture" not in readme_hit and BLIND_ALIAS in readme_hit
    checks = _decision(writer)["evidence_checks"]
    assert checks[0]["exists"] is True  # line 2 was seen only through the search hit


def test_without_hit_the_same_citation_is_unread(tmp_path):
    package = _package(tmp_path, "const label = 'fixture';\nrequire('child_process').execFileSync('echo', [label]);\n")
    replies = iter([_call("read_file", file="setup.js", start=1, end=1),
                    {"role": "assistant", "content": json.dumps(_verdict("1-2", "execute-process"))},
                    {"role": "assistant", "content": json.dumps(_verdict("1", "other"))}])
    seen = []

    def chat(_model, messages, final=False):
        seen.append(list(messages))  # the session trims repair turns from its own list later
        return next(replies)

    analyze(package, "fake", chat=chat)
    assert seen[0][0]["content"] == SYSTEM  # default prompt unchanged
    assert "unread evidence lines: setup.js:1-2" in seen[-1][-1]["content"]


@pytest.mark.parametrize("tools, decoded", [(None, False), (DEFAULT_TOOLS + ("decode_literal",), True)])
def test_l3_accepts_technique_shown_by_decoded_literal_only_with_decode_tool(tmp_path, tools, decoded):
    package = _package(tmp_path, "const m = require(Buffer.from('Y2hpbGRfcHJvY2Vzcw==', 'base64').toString());\n")
    replies = iter([_call("read_file", file="setup.js"),
                    {"role": "assistant", "content": json.dumps(_verdict("1", "execute-process"))},
                    {"role": "assistant", "content": json.dumps(_verdict("1", "execute-process"))}])
    writer = TraceWriter(tmp_path / "reports" / "run-1", "tools-fixture@1.0.0")
    analyze(package, "fake", chat=lambda *_args, **_kwargs: next(replies), trace=writer, tools=tools)
    check = _decision(writer)["evidence_checks"][0]
    assert check["exists"] is decoded and check.get("decoded", False) is decoded


def test_config_tools_field_is_optional_and_checked(tmp_path):
    base = "name: X\nmodel: m\nmax_steps: 15\ndeny_threshold: 0.8\napprove_threshold: 0.8\n"
    (tmp_path / "X.yaml").write_text(base, encoding="utf-8")
    assert "tools" not in batch.load_config("X", tmp_path)
    (tmp_path / "Y.yaml").write_text(base + "tools: [read_manifest, read_file, search_code]\n", encoding="utf-8")
    assert batch.load_config("Y", tmp_path)["tools"] == ["read_manifest", "read_file", "search_code"]
    (tmp_path / "Z.yaml").write_text(base + "tools: [read_file, run_it]\n", encoding="utf-8")
    with pytest.raises(ValueError):
        batch.load_config("Z", tmp_path)
    assert batch.variants(tmp_path) == ["X", "Y", "Z"]
    for variant in ("A-LLM", "A-SLM", "A-TLM"):
        assert "tools" not in batch.load_config(variant)  # shipped configs keep the original four tools


def test_run_one_passes_tools_only_when_configured(tmp_path):
    calls = []

    def fake(package, model, max_steps, trace, **kwargs):
        calls.append(kwargs)
        raise RuntimeError("stop")

    (tmp_path / "p").mkdir()
    package = _package(tmp_path / "p", "1;\n")
    item = {"package": "tools-fixture@1.0.0", "dir": package}
    config = {"name": "X", "model": "m", "max_steps": 3, "deny_threshold": 0.8, "approve_threshold": 0.8, "options": {}}
    batch.run_one(item, tmp_path / "run", config, None, fake)
    batch.run_one(item, tmp_path / "run2", {**config, "tools": ["read_file"]}, None, fake)
    assert "tools" not in calls[0] and calls[1]["tools"] == ["read_file"]


def test_large_exploration_result_is_shortened_not_replaced_by_an_error(tmp_path):
    package = _package(tmp_path, "1;\n", {f"file{i:03}.txt": "x\n" for i in range(250)})
    replies = iter([_call("list_files"), _call("read_file", file="setup.js"),
                    {"role": "assistant", "content": json.dumps(_verdict("1", "other"))}])
    sent = []

    def chat(_model, messages, final=False):
        sent.append(list(messages))
        return next(replies)

    analyze(package, "fake", chat=chat, tools=DEFAULT_TOOLS + ("list_files",))
    listed = json.loads([message for message in sent[1] if message.get("tool_name") == "list_files"][0]["content"])
    assert listed["ok"] and listed["data"]["truncated"] and 0 < len(listed["data"]["files"]) < 252
    assert len(json.dumps(listed)) <= 16000


def test_exploration_tool_crash_is_an_error_result(tmp_path, monkeypatch):
    from agent import run

    def boom(_package):
        raise RecursionError("deep")

    monkeypatch.setitem(run.EXPLORE_TOOLS, "list_files", run.EXPLORE_TOOLS["list_files"][:3] + (boom,))
    assert _tool(_package(tmp_path, "1;\n"), "list_files", {}, ALL_TOOLS) == {
        "ok": False, "data": None, "error": "tool failed: RecursionError"}
