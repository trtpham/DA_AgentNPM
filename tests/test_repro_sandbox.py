from experiments.repro_sandbox import fingerprint, host_values, leaked
from sandbox.run import CANARY


def test_host_values_skip_short_loopback_and_canary_values():
    environ = {"SHORT": "abc", "LOOP": "127.0.0.1", "CANARY": CANARY["environment_vars"]["NPM_TOKEN"],
               "SECRETISH": "abcdefghijk", "FLAG": "true"}
    assert host_values(environ) == {"SECRETISH": "abcdefghijk"}


def test_leak_names_only_and_fingerprint_fields():
    result = {"ok": True, "data": {"outcome": "ok", "canary_touched": ["ssh", "aws"],
                                   "strace": {"content": "openat(... abcdefghijk ...)"}, "stdout": {"content": ""},
                                   "stderr": {"content": ""},
                                   "by_actor": {"package": {"network_count": 2, "processes": ["a", "b"]}},
                                   "behavior": {"persistence_writes": [{"path": "/etc/x", "actor": "package"},
                                                                       {"path": "/etc/y", "actor": "npm"}]}}}
    assert leaked(result, {"SECRETISH": "abcdefghijk", "OTHER": "zzzzzzzzzz"}) == ["SECRETISH"]
    assert fingerprint(result) == {"ok": True, "outcome": "ok", "canary_touched": ["aws", "ssh"], "package_network": 2,
                                   "package_processes": 2, "persistence": ["/etc/x"]}
