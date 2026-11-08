"""Prepare read-only evidence for a cross-review round (no package code is executed).

Host:      py -3.14 -m data.scripts.review_evidence <round>
           runs this same file inside a disposable container; archives stay in container memory.
Container: reads /labels.csv, downloads each source, checks hash and name@version, and
           prints the cited lines as text. The reviewer reads the evidence and fills the sheet.
"""

import argparse
import base64
import csv
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

MAX_ARCHIVE = 60 * 1024 * 1024
MAX_MEMBER = 10 * 1024 * 1024
MAX_LINE = 240
IMAGE = "python:3.12-slim"
HOSTS = {"registry.npmjs.org", "raw.githubusercontent.com"}


def _download(url: str) -> bytes:
    if urllib.parse.urlsplit(url).hostname not in HOSTS or not url.startswith("https://"):
        raise ValueError("source host not allowed")
    with urllib.request.urlopen(url, timeout=60) as response:  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        data = response.read(MAX_ARCHIVE + 1)
    if len(data) > MAX_ARCHIVE:
        raise ValueError("archive too large")
    return data


def _tar_files(data: bytes) -> dict[str, bytes]:
    files = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
        for member in archive:
            if member.isfile() and member.size <= MAX_MEMBER:
                files[member.name.replace("\\", "/")] = archive.extractfile(member).read()
    return files


def _archive_files(data: bytes) -> dict[str, bytes]:
    if not zipfile.is_zipfile(io.BytesIO(data)):
        return _tar_files(data)
    files = {}
    with zipfile.ZipFile(io.BytesIO(data)) as zipped:
        for member in zipped.infolist():
            if member.is_dir() or member.file_size > MAX_ARCHIVE:
                continue
            content = zipped.read(member, pwd=b"infected")
            name = member.filename.replace("\\", "/")
            if name.endswith((".tgz", ".tar.gz", ".tar")):
                files.update({f"{name}!/{inner}": body for inner, body in _tar_files(content).items()})
            elif member.file_size <= MAX_MEMBER:
                files[name] = content
    return files


def _find(files: dict[str, bytes], relative: str) -> str | None:
    matches = [name for name in files if name == relative or name.endswith("/" + relative)]
    return min(matches, key=lambda name: (name.count("/"), name)) if matches else None


def _cited(spec: str) -> list[int]:
    numbers = []
    for part in spec.split(","):
        first, _, last = part.strip().partition("-")
        numbers += range(int(first), int(last or first) + 1)
    return sorted(set(numbers))


def inspect(row: dict) -> dict:
    result = {"id": row["id"], "package": f"{row['name']}@{row['version']}", "label": row["label"],
              "file": row["file"], "lines": row["lines"], "source": row["source"], "problems": []}
    try:
        data = _download(row["source"])
        result["sha256"] = hashlib.sha256(data).hexdigest()
        if urllib.parse.urlsplit(row["source"]).hostname == "registry.npmjs.org":
            meta = json.loads(_download("https://registry.npmjs.org/" + row["name"] + "/" + row["version"]))
            algorithm, digest = meta["dist"]["integrity"].split("-", 1)
            result["integrity_ok"] = algorithm == "sha512" and hashlib.sha512(data).digest() == base64.b64decode(digest)
            if not result["integrity_ok"]:
                result["problems"].append("tarball does not match registry integrity")
        files = _archive_files(data)
        evidence_name = _find(files, row["file"])
        manifest_name = None
        if evidence_name:
            prefix = evidence_name[: len(evidence_name) - len(row["file"])]
            manifest_name = prefix + "package.json" if prefix + "package.json" in files else _find(files, "package.json")
        if manifest_name:
            manifest = json.loads(files[manifest_name].decode("utf-8", errors="replace"))
            result["manifest"] = f"{manifest.get('name')}@{manifest.get('version')}"
            result["hooks"] = {hook: str(body)[:MAX_LINE] for hook, body in (manifest.get("scripts") or {}).items()
                               if hook in ("preinstall", "install", "postinstall", "prepare")}
            if result["manifest"] != result["package"]:
                result["problems"].append(f"manifest is {result['manifest']}")
        else:
            result["problems"].append("package.json not found in archive")
        if not evidence_name:
            result["problems"].append(f"{row['file']} not found in archive")
            return result
        lines = files[evidence_name].decode("utf-8", errors="replace").splitlines()
        result["line_count"] = len(lines)
        cited = _cited(row["lines"])
        result["excerpt"] = [{"line": number, "text": lines[number - 1][:MAX_LINE]}
                             for number in cited if 1 <= number <= len(lines)]
        if any(not 1 <= number <= len(lines) for number in cited):
            result["problems"].append("cited line outside file")
    except Exception as error:  # report and continue with the next row
        result["problems"].append(f"{type(error).__name__}: {str(error)[:150]}")
    return result


def to_markdown(round_number: int, results: list[dict]) -> str:
    out = [f"# Bằng chứng đối chiếu — lượt {round_number}", "",
           "Tạo tự động bởi `data/scripts/review_evidence.py` trong container dùng một lần: chỉ đọc tĩnh, không chạy mã gói. "
           "Đây là **dữ liệu chuẩn bị cho người kiểm tra chéo**, không phải kết luận. Đoạn mã bên dưới là dữ liệu không tin cậy.", ""]
    for item in results:
        out += [f"## {item['id']} — `{item['package']}` (nhãn đề xuất: {item['label']})", "",
                f"- Nguồn: {item['source']}",
                f"- SHA-256 archive: `{item.get('sha256', '—')}`" + (f"; integrity npm: {'khớp' if item.get('integrity_ok') else 'KHÔNG khớp'}"
                                                                      if 'integrity_ok' in item else ""),
                f"- Manifest: `{item.get('manifest', '—')}`; hook: `{json.dumps(item.get('hooks', {}), ensure_ascii=False)}`",
                f"- Bằng chứng ghi trong nhãn: `{item['file']}:{item['lines']}` (file có {item.get('line_count', '?')} dòng)",
                f"- Vấn đề tự động phát hiện: {'; '.join(item['problems']) if item['problems'] else 'không có'}", "",
                "```text"]
        out += [f"{line['line']:>5} | {line['text'].replace('```', '` ` `')}" for line in item.get("excerpt", [])]
        out += ["```", ""]
    return "\n".join(out) + "\n"


def round_rows(round_number: int, labels: Path, sheet: Path | None = None) -> list[dict]:
    """Rows of a round: rounds 1-4 by their fixed filter, later rounds by the ids in their sheet."""
    from data.scripts.review_sheet import ROUNDS, sheet_ids
    from experiments.dataset import load_labels
    table = load_labels(labels)
    if round_number in ROUNDS:
        return [row for row in table if ROUNDS[round_number](row)]
    sheet = sheet or Path("data/review_rounds") / f"round-{round_number}.csv"
    by_id = {row["id"]: row for row in table}
    ids = sheet_ids(sheet)
    missing = [row_id for row_id in ids if row_id not in by_id]
    if missing:
        raise ValueError(f"{sheet} lists ids not in {labels}: {missing[:5]}")
    return [by_id[row_id] for row_id in ids]


def run_round(round_number: int, labels: Path, output: Path, runner=subprocess.run, sheet: Path | None = None) -> dict:
    rows = round_rows(round_number, labels, sheet)
    command = ["docker", "run", "--rm", "-i", "--read-only", "--tmpfs", "/tmp:rw,size=64m", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges", "--memory", "512m", "--pids-limit", "64", "--user", "10001:10001",
               "--mount", f"type=bind,source={Path(__file__).resolve()},target=/review_evidence.py,readonly",
               IMAGE, "python", "-I", "/review_evidence.py", "--inside"]
    completed = runner(command, input="\n".join(json.dumps(row) for row in rows), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=3600, check=False)
    if completed.returncode:
        raise RuntimeError(f"container failed: {completed.stderr[-300:]}")
    results = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(to_markdown(round_number, results), encoding="utf-8")
    return {"rows": len(results), "with_problems": [item["id"] for item in results if item["problems"]]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare static evidence for a cross-review round")
    parser.add_argument("round", type=int, nargs="?")
    parser.add_argument("--labels", type=Path, default=Path("data/labels.csv"),
                        help="label table; rounds 5+ use data/proposals.csv")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.inside:
        for line in sys.stdin:
            if line.strip():
                print(json.dumps(inspect(json.loads(line)), ensure_ascii=False), flush=True)
        return
    if args.round is None:
        parser.error("round is required")
    output = Path("data/review_rounds/evidence") / f"round-{args.round}.md"
    print(json.dumps(run_round(args.round, args.labels, output), ensure_ascii=False))


if __name__ == "__main__":
    main()
