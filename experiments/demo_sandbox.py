"""Demo: run the harmless sandbox fixtures and print one readable table (W5-11).

Only team-written fixtures under tests/fixtures run, and only inside the offline container
(`sandbox.run.run_sandbox`). Never point this at a real or malicious package on the host.

    py -3.14 -m experiments.demo_sandbox            # all 9 fixtures (about 90 s; timeout takes 60 s)
    py -3.14 -m experiments.demo_sandbox network canary-all
"""

import argparse
import re
import sys
from pathlib import Path

from sandbox.run import run_sandbox

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
CASES = {
    "network": ("sandbox-limits/network", "gọi HTTPS + DNS ra ngoài"),
    "processes": ("sandbox-limits/processes", "sinh 200 tiến trình"),
    "memory": ("sandbox-limits/memory", "cấp phát ~512 MB"),
    "timeout": ("sandbox-limits/timeout", "ngủ 120 giây"),
    "write-outside": ("sandbox-limits/write-outside", "ghi /input, /etc, $HOME"),
    "canary-all": ("sandbox-limits/canary-all", "đọc 3 file canary + biến môi trường"),
    "benign": ("benign-package", "gói lành có postinstall"),
    "no-hook": ("no-hook-package", "gói không có hook"),
    "canary": ("canary-package", "đọc khóa SSH giả"),
}
HEADER = ("Fixture", "Script cố làm", "Script tự báo", "outcome", "ok", "mã", "mạng npm/gói/?", "canary chạm")


def row(name: str, result: dict) -> tuple[str, ...]:
    """One table row from a run_sandbox result; pure, so it is unit-tested."""
    data = result.get("data") or {}
    actors = data.get("by_actor") or {}
    network = "/".join(str(actors.get(actor, {}).get("network_count", "-")) for actor in ("npm", "package", "unknown"))
    stdout = (data.get("stdout") or {}).get("content", "")
    # Probes print "W5RESULT key=value"; a repeated key keeps its last value (memory before the kill).
    values: dict[str, str] = {}
    for line in stdout.splitlines():
        if line.startswith("W5RESULT "):
            for pair in re.findall(r"(\S+)=(\S+)", line.replace("read ", "").replace("write ", "")):
                key = pair[0].removesuffix("/w5-marker").replace("/home/agent", "$HOME")
                values[key.removeprefix("$HOME/") if key != "$HOME" else key] = pair[1]
    reported = " ".join(f"{key}={value}" for key, value in values.items())
    return (name, CASES[name][1], reported[:60] or "—", str(data.get("outcome", "lỗi: " + str(result.get("error")))),
            "✔" if result.get("ok") else "✘", str(data.get("returncode", "-")), network,
            ", ".join(data.get("canary_touched") or []) or "—")


def table(rows: list[tuple[str, ...]]) -> str:
    widths = [max(len(item[index]) for item in [HEADER, *rows]) for index in range(len(HEADER))]
    line = lambda item: " | ".join(cell.ljust(width) for cell, width in zip(item, widths))
    return "\n".join([line(HEADER), "-+-".join("-" * width for width in widths), *map(line, rows)])


def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252
        stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Show sandbox limits on harmless fixtures")
    parser.add_argument("cases", nargs="*", help=f"subset of: {', '.join(CASES)}")
    names = parser.parse_args().cases or list(CASES)
    if unknown := [name for name in names if name not in CASES]:
        parser.error(f"unknown case {unknown}; choose from {list(CASES)}")
    rows = []
    for name in names:
        print(f"… chạy {name} trong container (--network none)", file=sys.stderr, flush=True)
        rows.append(row(name, run_sandbox(FIXTURES / CASES[name][0])))
    print(table(rows))


if __name__ == "__main__":
    main()
