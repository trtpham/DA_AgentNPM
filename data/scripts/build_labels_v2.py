"""Build data/labels-v2-draft.csv for labels-v2 (T2 steps 4-7, Gate B0 pha 1 2026-11-22).

Collects already-inspected Datadog 2025-2026 hook samples, already-triaged benign npm candidates,
and the 30 suspicious rows of labels-v1; checks OSV (name@version only), removes duplicates with
labels-v1, prevents labels-v1 test packages from entering v2 train, splits clusters into
train (~50%) / dev (~20%) / test (~30%), assigns `time_split` relative to --cutoff (default
2026-03-02), and writes data/labels-v2-draft.csv + stats README. Never overwrites labels-v1.csv
or freezes labels-v2.csv (freezing requires a separate Gate).
"""

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from data.scripts.datadog_container import dataset_name, sample_date
from data.scripts.propose_labels import cluster_of
from experiments.dataset import FIELDS, load_labels
from tools.intel import osv_lookup

V2_FIELDS = FIELDS + ("source_date", "time_split", "source_kind")
DEFAULT_CUTOFF = "2026-03-02"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CAP = 12


def time_split_flag(source_date: str, cutoff: str = DEFAULT_CUTOFF) -> str:
    """`after` if strictly after cutoff, `before` if on/before cutoff, `unknown` if missing/invalid."""
    text = (source_date or "").strip()
    if not DATE_RE.fullmatch(text):
        return "unknown"
    return "after" if text > cutoff else "before"


def _cite_from_entries(entries: list[dict]) -> tuple[str, str, str] | None:
    if not entries:
        return None
    entry = entries[0]
    if entry.get("file") == "package.json" and entry.get("line"):
        return "package.json", str(entry["line"]), f"{entry['hook']} runs an inline command"
    if entry.get("lines"):
        return entry["file"], f"1-{min(int(entry['lines']), 150)}", f"{entry['hook']} runs {entry['file']}"
    return None


def load_datadog_v2(datadog_dir: Path, *, min_date: str = "2025-01-01") -> list[dict]:
    """Read inspected Datadog v2 JSONL batches; keeps only clean samples with install hooks."""
    rows = []
    for path in sorted(datadog_dir.glob("candidates-v2-batch-*.jsonl")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"[warn] skipping unreadable datadog batch {path.name}: {exc}", file=sys.stderr)
            continue
        for line in text.splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("error") or not item.get("has_hook") or not item.get("install_hash"):
                continue
            sdate = sample_date(item.get("path", ""))
            if min_date and (not sdate or sdate < min_date):
                continue
            cited = _cite_from_entries(item.get("entries") or [])
            if not cited:
                continue
            file, lines, action = cited
            name, _, version = (item.get("manifest") or "").rpartition("@")
            if not name or version != item.get("version"):
                name, version = dataset_name(item["name"]), item["version"]
            slug = re.sub(r"[^a-z0-9.]+", "-", name.lower()).strip("-")
            rows.append({
                "id": f"dd2-{slug}-{version}",
                "name": name,
                "version": version,
                "label": "malicious",
                "behavior_main": f"Datadog malicious_intent ({sdate}); {action}",
                "technique": "datadog-source",
                "file": file,
                "lines": lines,
                "source": item["archive"],
                "split": "",
                "cluster": "dd-" + item["install_hash"][:12],
                "source_date": sdate,
                "source_kind": "datadog",
                "_install_hash": item["install_hash"],
                "_tarball_sha256": item.get("zip_sha256", ""),
            })
    return rows


def load_benign_triaged(triage_paths: list[Path], *, source_kind: str | None = None,
                        allow_groups: tuple[str, ...] = ("A", "B")) -> list[dict]:
    """Read triaged public npm candidates (never group C); keeps rows with valid tarball + cite."""
    rows = []
    for path in triage_paths:
        if not path.is_file():
            continue
        kind = source_kind or ("npm-popular" if ("v2" in path.stem or "popular" in path.stem) else "npm-search")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for item in csv.DictReader(stream):
                if item.get("group") not in allow_groups or not item.get("tarball"):
                    continue
                entries = json.loads(item.get("entries") or "[]")
                cited = _cite_from_entries(entries)
                if not cited:
                    continue
                file, lines, action = cited
                slug = re.sub(r"[^a-z0-9.]+", "-", item["package"].lower()).strip("-")
                rows.append({
                    "id": f"ben2-{slug}-{item['version']}",
                    "name": item["package"],
                    "version": item["version"],
                    "label": "benign",
                    "behavior_main": f"npm package ({item['group']}); {action}",
                    "technique": f"triage-{item['group'].lower()}",
                    "file": file,
                    "lines": lines,
                    "source": item["tarball"],
                    "split": "",
                    "cluster": cluster_of(item["package"]),
                    "source_date": "",
                    "source_kind": kind,
                    "_install_hash": item.get("install_hash", ""),
                    "_tarball_sha256": item.get("tarball_sha256", ""),
                })
    return rows


def annotate_osv(rows: list[dict], cache_path: Path, checker=osv_lookup, max_workers: int = 8) -> dict[tuple[str, str], bool]:
    """Look up OSV MAL status by name@version only, cached in JSON so runs resume."""
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.is_file() else {}
    pending = []
    seen_pending = set()
    for row in rows:
        pkg = f"{row['name']}@{row['version']}"
        if pkg not in cache and pkg not in seen_pending:
            seen_pending.add(pkg)
            pending.append((pkg, row["name"], row["version"]))
    dirty = False
    if pending:
        with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
            results = list(pool.map(lambda item: (item[0], checker(item[1], item[2])), pending))
        for pkg, res in results:
            if res.get("ok") and res.get("data") is not None:
                cache[pkg] = {
                    "malicious": bool(res["data"].get("malicious")),
                    "ids": [v.get("id") for v in (res["data"].get("vulns") or []) if v.get("id")][:5],
                }
                dirty = True
            else:
                cache[pkg] = {"malicious": None, "ids": []}
    mal_map = {
        (row["name"], row["version"]): bool(cache.get(f"{row['name']}@{row['version']}", {}).get("malicious"))
        for row in rows
    }
    if dirty:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return mal_map


def split_clusters_three_way(rows: list[dict], ratios: tuple[float, float, float] = (0.5, 0.2, 0.3),
                             blocked_train_clusters: frozenset[str] = frozenset()) -> list[dict]:
    """Assign train/dev/test by cluster per label without cluster leakage.

    Clusters in `blocked_train_clusters` (e.g. containing labels-v1 test rows) go only to dev/test.
    """
    r_train, r_dev, r_test = ratios
    if abs((r_train + r_dev + r_test) - 1.0) > 1e-6:
        raise ValueError("split ratios must sum to 1.0")

    labels_per_cluster: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        labels_per_cluster[row["cluster"]].add(row["label"])
    out = []
    for row in rows:
        copy = dict(row)
        if len(labels_per_cluster[copy["cluster"]]) > 1:
            copy["cluster"] = f"{copy['cluster']}/{copy['label']}"
        out.append(copy)

    by_label_cluster: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in out:
        by_label_cluster[row["label"]][row["cluster"]].append(row)

    for label, cmap in by_label_cluster.items():
        groups = sorted(
            cmap.items(),
            key=lambda item: (hashlib.sha256(f"v2:{item[0]}".encode("utf-8")).hexdigest(), item[0]),
        )
        total = sum(len(g) for _, g in groups)
        targets = {"train": total * r_train, "dev": total * r_dev, "test": total * r_test}
        counts = {"train": 0, "dev": 0, "test": 0}
        # Assign blocked clusters first (only dev or test), then assign remaining clusters greedily
        # to whichever split has the largest remaining deficit toward its target count.
        def is_blocked(cluster_name: str) -> bool:
            return cluster_name in blocked_train_clusters or cluster_name.partition("/")[0] in blocked_train_clusters

        ordered = [item for item in groups if is_blocked(item[0])] + [
            item for item in groups if not is_blocked(item[0])
        ]
        for cluster, members in ordered:
            allowed = ("dev", "test") if is_blocked(cluster) else ("train", "dev", "test")
            chosen = max(allowed, key=lambda name: (targets[name] - counts[name], name == "test"))
            counts[chosen] += len(members)
            for row in members:
                row["split"] = chosen
    return out


def build_draft(v1_path: Path, datadog_rows: list[dict], benign_rows: list[dict], *,
                cutoff: str = DEFAULT_CUTOFF, osv_mal: dict[tuple[str, str], bool] | None = None,
                max_malicious: int = 600, max_benign: int = 800, cap: int = CAP) -> list[dict]:
    """Assemble deduplicated v2 draft rows: ~600 malicious, ~800 benign, + 30 v1 suspicious."""
    osv_mal = osv_mal or {}
    v1_rows = load_labels(v1_path)
    v1_keys = {(r["name"], r["version"]) for r in v1_rows}
    v1_test_keys = {(r["name"], r["version"]) for r in v1_rows if r["split"] == "test"}
    v1_test_names = {r["name"] for r in v1_rows if r["split"] == "test"}
    v1_test_clusters = {r["cluster"] for r in v1_rows if r["split"] == "test" and r.get("cluster")}
    suspicious_rows = [
        {**r, "source_date": "", "source_kind": "labels-v1-suspicious", "_install_hash": "", "_tarball_sha256": ""}
        for r in v1_rows if r["label"] == "suspicious"
    ]

    # Filter malicious: exclude v1 duplicates, prioritize newest 2025-2026 & OSV-confirmed if available
    seen_keys = set(v1_keys)
    seen_sha = set()
    filtered_mal = []
    for row in sorted(datadog_rows, key=lambda r: (-int(r["source_date"][:4] or 0), -int(bool(osv_mal.get((r["name"], r["version"])))), r["id"])):
        key = (row["name"], row["version"])
        sha = row.get("_tarball_sha256")
        if key in seen_keys or (sha and sha in seen_sha):
            continue
        seen_keys.add(key)
        if sha:
            seen_sha.add(sha)
        filtered_mal.append(row)

    # Filter benign: exclude v1 duplicates and anything OSV flags as MAL
    filtered_ben = []
    for row in benign_rows:
        key = (row["name"], row["version"])
        sha = row.get("_tarball_sha256")
        if key in seen_keys or osv_mal.get(key) or (sha and sha in seen_sha):
            continue
        seen_keys.add(key)
        if sha:
            seen_sha.add(sha)
        filtered_ben.append(row)

    # Merge clusters by install_hash and cap per cluster before taking target counts
    combined = suspicious_rows + filtered_mal + filtered_ben
    parent: dict[str, str] = {}

    def find(c: str) -> str:
        parent.setdefault(c, c)
        while parent[c] != c:
            parent[c] = parent[parent[c]]
            c = parent[c]
        return c

    by_install: dict[str, str] = {}
    for row in combined:
        find(row["cluster"])
        ih = row.get("_install_hash")
        if ih:
            other = by_install.setdefault(ih, row["cluster"])
            l, r = find(other), find(row["cluster"])
            if l != r:
                parent[r] = l
    for row in combined:
        row["cluster"] = find(row["cluster"])

    def cap_pick(items: list[dict], limit: int) -> list[dict]:
        counts: Counter[str] = Counter()
        picked = []
        for item in items:
            if len(picked) >= limit:
                break
            if counts[item["cluster"]] >= cap:
                continue
            counts[item["cluster"]] += 1
            picked.append(item)
        return picked

    final_mal = cap_pick(filtered_mal, max_malicious)
    final_ben = cap_pick(filtered_ben, max_benign)
    all_rows = suspicious_rows + final_mal + final_ben

    blocked_clusters = frozenset(
        row["cluster"]
        for row in all_rows
        if (row["name"], row["version"]) in v1_test_keys
        or row["name"] in v1_test_names
        or row["cluster"] in v1_test_clusters
    )
    split_rows = split_clusters_three_way(all_rows, blocked_train_clusters=blocked_clusters)
    cleaned = []
    for row in split_rows:
        row["time_split"] = time_split_flag(row.get("source_date", ""), cutoff)
        cleaned.append({field: row.get(field, "") for field in V2_FIELDS})
    return cleaned


def render_stats_md(rows: list[dict], cutoff: str = DEFAULT_CUTOFF,
                    osv_mal: dict[tuple[str, str], bool] | None = None) -> str:
    by_label = Counter(r["label"] for r in rows)
    by_split = Counter(r["split"] for r in rows)
    by_source = Counter(r["source_kind"] for r in rows)
    by_year = Counter((r["source_date"][:4] if r["source_date"] else "unknown") for r in rows)
    by_time = Counter(r["time_split"] for r in rows)
    test_after = sum(1 for r in rows if r["split"] == "test" and r["time_split"] == "after")
    osv_note = []
    if osv_mal is not None:
        mal_rows = [r for r in rows if r["label"] == "malicious"]
        osv_hits = sum(1 for r in mal_rows if osv_mal.get((r["name"], r["version"])))
        osv_note = [f"- Đối chiếu OSV (mã `MAL-` trong mẫu độc): **{osv_hits}/{len(mal_rows)}**"]
    lines = [
        "# Thống kê nháp bộ dữ liệu labels-v2",
        "",
        f"Tổng số dòng: **{len(rows)}** · Mốc `time_split`: `{cutoff}`.",
        "",
        "## Theo nhãn",
        "",
        *(f"- `{k}`: {v}" for k, v in sorted(by_label.items())),
        "",
        "## Theo tập chia (cluster-disjoint)",
        "",
        *(f"- `{k}`: {v}" for k, v in sorted(by_split.items())),
        "",
        "## Theo nguồn",
        "",
        *(f"- `{k}`: {v}" for k, v in sorted(by_source.items())),
        *osv_note,
        "",
        "## Theo năm (`source_date`)",
        "",
        *(f"- `{k}`: {v}" for k, v in sorted(by_year.items())),
        "",
        "## Theo `time_split`",
        "",
        *(f"- `{k}`: {v}" for k, v in sorted(by_time.items())),
        f"- Tập test theo thời gian (`split == test` và `time_split == after`): **{test_after}**",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build data/labels-v2-draft.csv (never freezes labels-v2.csv)")
    parser.add_argument("--v1", type=Path, default=Path("data/labels-v1.csv"))
    parser.add_argument("--datadog-dir", type=Path, default=Path("data/datadog"))
    parser.add_argument("--triage", type=Path, action="append", default=[])
    parser.add_argument("--cutoff", default=DEFAULT_CUTOFF)
    parser.add_argument("--osv-cache", type=Path, default=Path("data/osv-v2-cache.json"))
    parser.add_argument("--skip-osv", action="store_true")
    parser.add_argument("--max-malicious", type=int, default=600)
    parser.add_argument("--max-benign", type=int, default=800)
    parser.add_argument("--output", type=Path, default=Path("data/labels-v2-draft.csv"))
    parser.add_argument("--readme", type=Path, default=Path("data/README-v2-draft.md"))
    args = parser.parse_args()

    dd_rows = load_datadog_v2(args.datadog_dir)
    triage_files = args.triage or sorted(
        Path("data").glob("review_*/triage_*.csv"),
        key=lambda p: (0 if "v2" in p.stem or "popular" in p.stem else 1, str(p)),
    )
    ben_rows = load_benign_triaged(triage_files)
    osv_mal = {} if args.skip_osv else annotate_osv(dd_rows + ben_rows, args.osv_cache)
    draft_rows = build_draft(args.v1, dd_rows, ben_rows, cutoff=args.cutoff, osv_mal=osv_mal,
                             max_malicious=args.max_malicious, max_benign=args.max_benign)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, V2_FIELDS)
        writer.writeheader()
        writer.writerows(draft_rows)
    if args.readme:
        args.readme.write_text(render_stats_md(draft_rows, args.cutoff, osv_mal=None if args.skip_osv else osv_mal), encoding="utf-8")
    print(json.dumps({"rows": len(draft_rows), "labels": dict(Counter(r["label"] for r in draft_rows)),
                      "splits": dict(Counter(r["split"] for r in draft_rows))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
