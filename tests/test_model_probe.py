from experiments.model_probe import probe_model


def test_probe_counts_tool_json_and_missing_runtime_metrics():
    def request(_model, messages, *, tools=None, format=None):
        if tools:
            return {"message": {"role": "assistant", "tool_calls": [{"function": {
                "name": "lookup_constant", "arguments": {"key": "alpha"}, "index": 0}}]},
                "eval_count": 10, "eval_duration": 1_000_000_000}
        assert format and messages[-1]["role"] == "tool"
        return {"message": {"content": '{"value":7}'},
                "eval_count": 5, "eval_duration": 500_000_000}

    assert probe_model("fake", 2, request) == {
        "model": "fake", "attempts": 2, "tool_calls_ok": 2,
        "json_ok": 2, "errors": 0, "tokens_per_s": 10.0}
    assert probe_model("fake", 1, lambda *_args, **_kwargs: {"message": {"content": "none"}}) == {
        "model": "fake", "attempts": 1, "tool_calls_ok": 0,
        "json_ok": 0, "errors": 0, "tokens_per_s": None}
