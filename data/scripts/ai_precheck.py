"""Automatic pre-check of a review round (PO decision 08/11/2026, option 1). Never a review.

    py -3.14 -m data.scripts.ai_precheck 10          # after review_evidence 10

For each row, the cited excerpt is scanned with the agent's technique signs (agent.semantics) and
compared with the proposed label. The result is a hint for the human reviewer:
  khớp      the excerpt shows signs that fit the proposed label
  cần xem   some signs fit, some do not, or the signs are ambiguous: read those lines
  nghi ngờ  the excerpt does not support the label, or the evidence step reported a problem
It is written to data/review_rounds/ai-precheck/round-N.csv and shown in the evidence page, always
attributed to Claude. The review sheet itself is left for the person, who decides and signs.
"""

import argparse
import base64
import csv
import json
import re
import sys
from pathlib import Path

from agent.semantics import TECHNIQUES

EVIDENCE_DIR = Path("data/review_rounds/evidence")
OUT_DIR = Path("data/review_rounds/ai-precheck")
NEUTRAL = {"print-output", "read-package-file", "write-package-file", "native-build", "other"}



FIELDS = ("id", "ai_check", "ai_signals", "ai_note")


# Narrow, specific signs. The agent's technique families (agent.semantics) are deliberately broad
# for one cited line; over a 150-line excerpt they fire on most benign installers (mkdir, /tmp,
# URLs in comments), so a strong verdict here needs one of these.
STRONG = {
    "secret_path": r"\.npmrc|\.ssh/|id_rsa|id_ed25519|\.aws/credentials|\.docker/config|\.kube/config"
                   r"|\.git-credentials|\.config/gh|wallet\.dat|solana/id\.json",
    "persistence": r"\.bashrc|\.zshrc|\.bash_profile|\.profile\b|crontab|LaunchAgents|\.config/autostart|systemd/",
    "dynamic_eval": r"\beval\s*\(|\bnew\s+Function\s*\(|\bvm\.runIn",
    "pipe_to_shell": r"(?:curl|wget)[^|\n]{0,200}\|\s*(?:sh|bash)\b",
    "env_dump": r"Object\.(?:entries|keys)\(\s*process\.env\s*\)|JSON\.stringify\(\s*process\.env\s*\)|\bprintenv\b",
    "exec_call": r"\b(?:exec|execSync|execFile|execFileSync|spawn|spawnSync|fork)\s*\(",
    "host_info": r"\bos\.(?:hostname|userInfo|networkInterfaces|platform|type|release)\s*\(|\bwhoami\b"
                 r"|process\.env\.(?:USER|USERNAME|HOME|COMPUTERNAME)\b",
    "obfuscation": r"[A-Za-z0-9+/]{120,}={0,2}|(?:\\x[0-9a-fA-F]{2}){12,}|\b_0x[0-9a-f]{4,}",
    "network": r"\bhttps?\.(?:request|get)\s*\(|\bfetch\s*\(|\bnet\.connect|\.connect\s*\(\s*\d|\bdns\.(?:resolve|lookup)"
               r"|axios|XMLHttpRequest|WebSocket",
}


def signals(excerpt: list[dict]) -> dict[str, list[int]]:
    """Sign -> excerpt lines: the narrow STRONG signs, then the agent's broad technique families."""
    found: dict[str, list[int]] = {}
    for line in excerpt:
        for name, pattern in STRONG.items():
            if re.search(pattern, line["text"], re.I):
                found.setdefault(name, []).append(line["line"])
        for family, pattern in TECHNIQUES.items():
            if family in NEUTRAL or pattern is None:
                continue
            if re.search(pattern, line["text"], re.I):
                found.setdefault(family, []).append(line["line"])
    return found


def assess(label: str, found: dict[str, list[int]], problems: list[str]) -> tuple[str, str]:
    if problems:
        return "nghi ngờ", "bước bằng chứng báo: " + "; ".join(problems)[:200]
    signs = set(found)
    strong = bool(signs & {"dynamic_eval", "persistence", "pipe_to_shell", "env_dump"}) or \
        {"secret_path", "network"} <= signs
    # Typical install-time malware: collect host data or run a command, and reach the network.
    recon = "network" in signs and bool(signs & {"host_info", "exec_call", "obfuscation"})
    specific = bool(signs & {"exec_call", "network", "secret_path", "host_info", "obfuscation"})
    if label == "malicious":
        if strong or recon:
            return "khớp", "đoạn trích có dấu hiệu độc cụ thể"
        if specific:
            return "cần xem", "có lệnh/gọi mạng nhưng chưa thấy chuỗi độc rõ"
        return "nghi ngờ", "đoạn trích không thấy dấu hiệu; có thể hành vi nằm ngoài đoạn trích"
    if label == "benign":
        if strong:
            return "nghi ngờ", "đoạn trích có dấu hiệu cụ thể không hợp với nhãn lành"
        if specific:
            return "cần xem", "có lệnh/gọi mạng: xem có giải thích được bằng mục đích gói không"
        return "khớp", "không thấy lệnh, gọi mạng hay đường dẫn secret trong đoạn trích"
    return ("khớp", "có dấu hiệu rủi ro") if strong or specific else ("cần xem", "không thấy dấu hiệu rủi ro")


def describe(found: dict[str, list[int]]) -> str:
    parts = [f"{family} (dòng {', '.join(map(str, lines[:4]))}{'…' if len(lines) > 4 else ''})"
             for family, lines in sorted(found.items(), key=lambda item: item[1][0])]
    return "; ".join(parts[:6]) or "không có"


def precheck(items: list[dict]) -> list[dict]:
    rows = []
    for item in items:
        excerpt = [{"line": line["line"], "text": base64.b64decode(line["b64"]).decode("utf-8", "replace")}
                   for line in item.get("excerpt", [])]
        found = signals(excerpt)
        check, note = assess(item["label"], found, item.get("problems", []))
        rows.append({"id": item["id"], "ai_check": check, "ai_signals": describe(found), "ai_note": note})
    return rows


def run(round_number: int, evidence_dir: Path = EVIDENCE_DIR, out_dir: Path = OUT_DIR) -> dict:
    items = json.loads((evidence_dir / f"round-{round_number}.json").read_text(encoding="utf-8"))
    rows = precheck(items)
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / f"round-{round_number}.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    from data.scripts.review_evidence import to_html
    (evidence_dir / f"round-{round_number}.html").write_text(
        to_html(round_number, items, {row["id"]: row for row in rows}), encoding="utf-8")
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["ai_check"]] = counts.get(row["ai_check"], 0) + 1
    return {"round": round_number, "rows": len(rows), "checks": counts}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Automatic pre-check of a review round (a hint, never a review)")
    parser.add_argument("rounds", type=int, nargs="+")
    args = parser.parse_args()
    for number in args.rounds:
        print(json.dumps(run(number), ensure_ascii=False))


if __name__ == "__main__":
    main()
