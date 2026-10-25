"""Probe local Ollama tool calls with a harmless synthetic tool."""

import argparse
import json
from http.client import HTTPConnection, HTTPException
from pathlib import Path

TOOL = {"type": "function", "function": {"name": "lookup_constant",
        "description": "Read a fixed synthetic constant",
        "parameters": {"type": "object", "properties": {"key": {"type": "string"}},
                       "required": ["key"]}}}
FORMAT = {"type": "object", "properties": {"value": {"type": "integer"}},
          "required": ["value"], "additionalProperties": False}


def _request(model: str, messages: list[dict], *, tools=None, format=None) -> dict:
    payload = {"model": model, "messages": messages, "stream": False, "think": False,
               "options": {"temperature": 0, "num_predict": 128}}
    if tools is not None:
        payload["tools"] = tools
    if format is not None:
        payload["format"] = format
    connection = HTTPConnection("127.0.0.1", 11434, timeout=120)
    try:
        connection.request("POST", "/api/chat", json.dumps(payload).encode(),
                           {"Content-Type": "application/json"})
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError(f"Ollama HTTP {response.status}")
        return json.load(response)
    finally:
        connection.close()


def probe_model(model: str, attempts: int = 20, request=_request) -> dict:
    if attempts < 1:
        raise ValueError("attempts must be positive")
    calls = valid_json = errors = tokens = duration_ns = 0
    for _ in range(attempts):
        messages = [{"role": "system", "content": "Call lookup_constant with key alpha. Then return JSON containing value 7."},
                    {"role": "user", "content": "What is the synthetic constant for alpha?"}]
        try:
            first = request(model, messages, tools=[TOOL])
            tokens += first.get("eval_count") or 0
            duration_ns += first.get("eval_duration") or 0
            message = first["message"]
            tool_calls = message.get("tool_calls") or []
            function = tool_calls[0].get("function", {}) if len(tool_calls) == 1 else {}
            if function.get("name") != "lookup_constant" or function.get("arguments") != {"key": "alpha"}:
                continue
            calls += 1
            messages.extend([message, {"role": "tool", "tool_name": "lookup_constant", "content": '{"value":7}'}])
            second = request(model, messages, format=FORMAT)
            tokens += second.get("eval_count") or 0
            duration_ns += second.get("eval_duration") or 0
            valid_json += json.loads(second["message"]["content"]) == {"value": 7}
        except (OSError, TimeoutError, HTTPException, RuntimeError, KeyError, ValueError, TypeError):
            errors += 1
    return {"model": model, "attempts": attempts, "tool_calls_ok": calls,
            "json_ok": valid_json, "errors": errors,
            "tokens_per_s": round(tokens * 1e9 / duration_ns, 2) if duration_ns else None}


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe local Ollama without package code")
    parser.add_argument("--attempts", type=int, default=20)
    args = parser.parse_args()
    print("config\tmodel\ttool_calls_ok\tjson_ok\terrors\ttokens_per_s")
    for path in sorted(Path("experiments/configs").glob("A-*.yaml")):
        values = dict(line.split(": ", 1) for line in path.read_text(encoding="utf-8").splitlines() if ": " in line)
        model = values["model"].strip('"\'')
        result = probe_model(model, args.attempts)
        print(f"{path.stem}\t{model}\t{result['tool_calls_ok']}/{args.attempts}\t"
              f"{result['json_ok']}/{args.attempts}\t{result['errors']}\t{result['tokens_per_s']}", flush=True)


if __name__ == "__main__":
    main()
