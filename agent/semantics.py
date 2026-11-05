"""Anti-rote helpers (Gate B0 2026-11-05).

L1 blind review: the model sees a neutral alias instead of the package name, and identity fields of
package.json (name, description, keywords, author, repository...) are hidden from it.
L2 fixed vocabulary: `technique` is one of TECHNIQUES while the model generates its verdict.
L3 semantic evidence: a cited line must show a sign of the claimed technique, otherwise it is not
counted as evidence. This only makes the evidence check stricter.
"""

import re

BLIND_ALIAS = "package-under-review"
HIDDEN = '"<hidden for blind review>"'
IDENTITY_KEYS = ("name", "description", "keywords", "author", "contributors", "maintainers", "repository",
                 "homepage", "bugs", "funding", "license", "publishConfig")

NETWORK = (r"https?:|\bhttps?\.|\bnet\.|\bdns\.|\btls\.|request\(|\bfetch\(|axios|XMLHttpRequest|WebSocket|socket"
           r"|\bcurl\b|\bwget\b|\b\d{1,3}(?:\.\d{1,3}){3}\b|\.connect\(|\.get\(|\.post\(")
# Package managers fetch code from a registry: `npm install x` is a download even without a URL.
FETCH = r"|\b(?:npm|pnpm|yarn|bun)\s+(?:install|i|add|ci)\b|\bnpx\s|\bpip3?\s+install\b|\bgit\s+clone\b"
WRITE = r"writeFile|appendFile|createWriteStream|copyFile|mkdir|rename|symlink|\.write\("
# Each technique names WHAT a line does, never whether it is bad: the label and severity carry the
# judgement. Neutral everyday actions come first (an all-alarming list made small models call every
# package suspicious, ablation 2026-11-05). Each lists signs that must appear in a cited line.
TECHNIQUES: dict[str, str | None] = {
    "print-output": r"console\.|process\.std(?:out|err)|\becho\b|\bprint",
    "read-package-file": r"readFile|createReadStream|readdir|\bstat|require\(|__dirname|\bfs\.|existsSync",
    "write-package-file": WRITE + r"|\bfs\.",
    "read-env": r"process\.env|\benv\b|\$\{?[A-Z_]{3,}",
    "execute-process": r"child_process|\bexec|\bspawn|\bfork\(|execFile|\bsh\b|\bbash\b|\bcmd\b|powershell"
                       r"|\"(?:pre|post)?install\"\s*:|\bnode\s|\bnpx?\s|node-gyp|execPath",
    "native-build": r"node-gyp|\bgyp\b|binding|prebuild|cmake|\bmake\b|\.node\b|napi|\bnan\b|compile",
    "network-request": NETWORK,
    "binary-download": NETWORK + FETCH + r"|download|\.tar|\.tgz|\.zip|\.exe|binary|release",
    "download-code": NETWORK + FETCH + r"|download",
    "decode-data": r"base64|Buffer\.from|\batob\b|fromCharCode|\\x[0-9a-fA-F]{2}|\\u[0-9a-fA-F]{4}"
                   r"|decodeURI|unescape|\bhex\b|[A-Za-z0-9+/]{40,}={0,2}|_0x[0-9a-f]{3,}",
    "dynamic-eval": r"\beval\b|Function\(|\bvm\.|runIn\w*Context|new\s+Function|require\(\s*[^'\"\s)]",
    "read-secret-file": r"\.npmrc|\.ssh|id_rsa|id_ed25519|\.aws|credentials|\.env\b|\.netrc|\.gitconfig|\.docker"
                        r"|keychain|wallet|\.kube",
    "write-outside-package": WRITE + r"|homedir|tmpdir|/etc/|/tmp\b|\.bashrc|\.profile|\.zshrc|crontab|AppData"
                             r"|Startup|LaunchAgents|systemd",
    "other": None,
}
# Older verdicts and small models write free text; map common wording to a family (first match wins).
FREE_TEXT = (
    (r"secret|credential|token|npmrc|ssh key|password", "read-secret-file"),
    (r"environment|process\.env|env var", "read-env"),
    (r"binary|prebuilt", "binary-download"),
    (r"download|fetch|remote code|dropper", "download-code"),
    (r"network|http|exfiltrat|beacon|request|upload", "network-request"),
    (r"eval|dynamic|function constructor", "dynamic-eval"),
    (r"decod|obfuscat|encod|base64", "decode-data"),
    (r"outside|home dir|persist", "write-outside-package"),
    (r"child_process|exec|spawn|process|shell|command", "execute-process"),
    (r"native|gyp|compile|build", "native-build"),
    (r"file write|writes? (?:a )?file|write", "write-package-file"),
    (r"print|log|console|echo", "print-output"),
    (r"read", "read-package-file"),
)


def technique_family(technique: str) -> str:
    """The vocabulary entry a technique belongs to; unknown wording is `other`."""
    text = technique.strip().lower()
    if text in TECHNIQUES:
        return text
    for pattern, family in FREE_TEXT:
        if re.search(pattern, text):
            return family
    return "other"


def shows_technique(technique: str, excerpt: str, file: str = "") -> bool:
    """True when the cited lines contain a sign of the claimed technique (`other` always passes).

    Only a native build may be shown by the file itself (binding.gyp); other file names prove nothing.
    """
    family = technique_family(technique)
    pattern = TECHNIQUES[family]
    if pattern is None or (family == "native-build" and file.rsplit("/", 1)[-1] == "binding.gyp"):
        return True
    return re.search(pattern, excerpt, re.I) is not None


# --- L1: blind review ----------------------------------------------------------------------------
def identity_lines(manifest_text: str) -> set[int]:
    """One-based lines of package.json that hold identity fields at the top level (incl. multi-line values)."""
    hidden, depth, inside = set(), 0, False
    key = re.compile(r'^\s*"(' + "|".join(IDENTITY_KEYS) + r')"\s*:')
    for number, line in enumerate(manifest_text.splitlines(), 1):
        # Brackets inside strings are rare in these fields; a miscount only hides or shows a line more.
        balance = line.count("{") + line.count("[") - line.count("}") - line.count("]")
        if inside:
            hidden.add(number)
            depth += balance
            inside = depth > 1  # back at the top-level object
        elif depth == 1 and key.match(line):
            hidden.add(number)
            inside = balance > 0
            depth += balance
        else:
            depth += balance
    return hidden


def blind_read(content: str, start: int, hidden: set[int]) -> str:
    """Replace hidden package.json lines in a read_file result; line count and numbering stay the same."""
    lines = content.split("\n")
    return "\n".join(HIDDEN if start + offset in hidden else line for offset, line in enumerate(lines))


def blind_manifest(result: dict) -> dict:
    """Copy of a read_manifest result with the package identity replaced by the alias."""
    if not result.get("ok") or not isinstance(result.get("data"), dict):
        return result
    data = {**result["data"], "name": BLIND_ALIAS, "version": None}
    return {**result, "data": data}


def blind_text(text: str, names: list[str]) -> str:
    """Replace the real package name in text sent to the model (e.g. indicator snippets)."""
    for name in sorted({n for n in names if n and len(n) >= 3}, key=len, reverse=True):
        text = re.sub(re.escape(name), BLIND_ALIAS, text)
    return text

