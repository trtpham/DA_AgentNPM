"""Execute only inside a restricted, offline Docker container."""

import argparse
import base64
import binascii
import json
import re
import subprocess
import tempfile
from pathlib import Path

IMAGE = "agent-npm-sandbox:local"
CANARY = json.loads((Path(__file__).parent / "canary" / "manifest.json").read_text(encoding="utf-8"))
OPEN = re.compile(r'\bopen(?:at|at2)?\([^"\n]*"([^"\n]+)"[^\n]*\)\s+=\s+\d+')
# strace -f prefixes every line with the PID (or thread id) that made the call.
LINE = re.compile(r"^(\d+)\s+(.*)$")
# fork/clone returns the child id, either on the same line or on the "<... resumed>" line.
SPAWN = re.compile(r"^(?:<\.\.\. )?(?:clone3?|fork|vfork)\b.*=\s+(\d+)\s*$")
SPAWN_EAGAIN = re.compile(r"^(?:<\.\.\. )?(?:clone3?|fork|vfork)\b.*=\s+-1 EAGAIN\b")
EXECVE_OK = re.compile(r'^execve\("[^"]*",\s*\[([^\]]*)\].*=\s+0\s*$')
EXECVE_ARGS = re.compile(r'^execve\("[^"]*",\s*\["sh",\s*"-c"')
NPM_EXEC = re.compile(r'^execve\("/usr/local/bin/npm",\s*\["npm",\s*"install"')
OUTCOME_ERRORS = {"timeout": "sandbox timed out", "oom": "sandbox out of memory",
                  "pids_limit": "sandbox process limit reached", "failed": "sandbox execution failed"}
ACTORS = ("npm", "package", "unknown")


def classify_outcome(status: int, trace: str) -> str:
    """W5-2: name why the install stopped, from the exit code and the trace."""
    if status == 124:  # coreutils timeout
        return "timeout"
    if status == 137:  # SIGKILL; inside the container this is the --memory cgroup limit
        return "oom"
    if any(SPAWN_EAGAIN.match(match.group(2)) for match in map(LINE.match, trace.splitlines()) if match):
        return "pids_limit"
    return "failed" if status else "ok"


def _process_tree(trace: str):
    """strace -f lines as (pid, call, raw), each pid's parent, and an `actor(pid)` function.

    `package` is any process under an `sh -c` that npm starts for a lifecycle script; `npm` is the
    rest of the tree under the traced npm process; `unknown` covers ids whose parent was cut from a
    truncated trace. Two passes, because a child's lines can appear before its parent's clone returns.
    """
    parent: dict[str, str] = {}
    script_roots: set[str] = set()
    root = None
    entries = []
    for raw in trace.splitlines():
        match = LINE.match(raw)
        if not match:
            continue
        pid, call = match.groups()
        entries.append((pid, call, raw))
        if spawn := SPAWN.match(call):
            parent.setdefault(spawn.group(1), pid)
        if call.startswith("execve("):
            # Only the traced `npm install` itself is the root; an orphan from a cut trace stays unknown.
            if root is None and pid not in parent and NPM_EXEC.match(call):
                root = pid
            if EXECVE_ARGS.match(call):
                script_roots.add(pid)

    cache: dict[str, str] = {}

    def actor(pid: str) -> str:
        chain = []
        current, found = pid, "unknown"
        while current is not None and current not in cache:
            chain.append(current)
            if current in script_roots:
                found = "package"
                break
            if current == root:
                found = "npm"
                break
            current = parent.get(current)
            if current in chain:  # defensive: ids are reused only after exit, never in a loop
                break
        else:
            if current is not None:
                found = cache[current]
        for item in chain:
            cache[item] = found
        return found

    return entries, parent, actor


def attribute_events(trace: str) -> dict:
    """W5-3: give every process, connect() and outside open() an actor from the strace -f PID tree."""
    entries, _, actor = _process_tree(trace)
    result = {name: {"processes": [], "network_attempts": [], "files_outside_package": set()} for name in ACTORS}
    pending_exec: dict[str, str] = {}
    for pid, call, raw in entries:
        bucket = result[actor(pid)]
        if call.startswith("execve(") and call.endswith("<unfinished ...>"):
            pending_exec[pid] = raw
        elif call.startswith("<... execve resumed>"):
            if pid in pending_exec and re.search(r"=\s+0\s*$", call):
                bucket["processes"].append(pending_exec[pid][:300])
            pending_exec.pop(pid, None)
        elif EXECVE_OK.match(call):
            bucket["processes"].append(raw[:300])
        elif "connect(" in call:
            bucket["network_attempts"].append(raw[:300])
        elif opened := OPEN.search(call):
            path = opened.group(1)
            if path.startswith("/") and not path.startswith("/work/"):
                bucket["files_outside_package"].add(path)
    return {name: {"processes": data["processes"][:20], "network_attempts": data["network_attempts"][:20],
                   "network_count": len(data["network_attempts"]),
                   "files_outside_package": sorted(data["files_outside_package"])[:50]}
            for name, data in result.items()}


CONNECT = re.compile(r"^(connect|sendto)\(.*?\{sa_family=(AF_INET6?)\b(.*?)\}")
SOCKET_PORT = re.compile(r"sin6?_port=htons\((\d+)\)")
SOCKET_ADDRESS = re.compile(r"inet_addr\(\"([^\"]+)\"\)|inet_pton\(AF_INET6,\s*\"([^\"]+)\"")
WRITE_OPEN = re.compile(r"^open(?:at|at2)?\([^\"\n]*\"([^\"\n]+)\",\s*([A-Z_|]+)")
WRITE_FLAGS = ("O_WRONLY", "O_RDWR", "O_CREAT", "O_APPEND", "O_TRUNC")
RENAME = re.compile(r"^(?:rename|renameat2?|link|linkat|symlink|symlinkat)\(.*\"([^\"\n]+)\"[^\"]*\)\s+=")
# Paths that make code run again later (shell start files, cron, autostart, systemd, system config).
PERSISTENCE = re.compile(r"/\.(?:bashrc|bash_profile|bash_login|profile|zshrc|zprofile|zshenv)$|crontab|/var/spool/cron/"
                         r"|/\.config/autostart/|/\.config/systemd/|^/etc/")
EXECVE = re.compile(r"^execve\(\"([^\"]*)\",\s*\[(.*?)\]")
ARGUMENT = re.compile(r"\"((?:\\.|[^\"\\])*)\"")
RESULT = re.compile(r"\s=\s+(-?\d+)(?:\s+([A-Z]\w*))?")


def behavior_events(trace: str) -> dict:
    """C4: connects, persistence writes and the process tree, each with its actor. Reads the log only."""
    entries, parent, actor = _process_tree(trace)
    connects, persistence, processes, seen = [], [], [], set()
    pending_exec: dict[str, str] = {}
    for pid, call, _ in entries:
        results = RESULT.findall(call)
        status = None
        if results:
            value, errno = results[-1]
            status = "ok" if not value.startswith("-") else (errno or "error")
        if network := CONNECT.match(call):
            port = SOCKET_PORT.search(network.group(3))
            address = SOCKET_ADDRESS.search(network.group(3))
            item = {"ip": (address.group(1) or address.group(2)) if address else None,
                    "port": int(port.group(1)) if port else None, "family": network.group(2),
                    "call": network.group(1), "dns": bool(port and port.group(1) == "53"),
                    "result": status, "actor": actor(pid)}
            key = (item["ip"], item["port"], item["call"], item["actor"])
            if key not in seen:
                seen.add(key)
                connects.append(item)
        elif (opened := WRITE_OPEN.match(call)) and any(flag in opened.group(2) for flag in WRITE_FLAGS):
            if PERSISTENCE.search(opened.group(1)):
                persistence.append({"path": opened.group(1), "result": status, "actor": actor(pid)})
        elif (renamed := RENAME.match(call)) and PERSISTENCE.search(renamed.group(1)):
            persistence.append({"path": renamed.group(1), "result": status, "actor": actor(pid)})
        if call.startswith("execve(") and call.endswith("<unfinished ...>"):
            pending_exec[pid] = call
            continue
        if call.startswith("<... execve resumed>"):
            call, ok = pending_exec.pop(pid, ""), bool(re.search(r"=\s+0\s*$", call))
        else:
            ok = bool(re.search(r"=\s+0\s*$", call))
        if ok and (executed := EXECVE.match(call)):
            argv = [argument[:200] for argument in ARGUMENT.findall(executed.group(2))[:10]]
            processes.append({"pid": int(pid), "ppid": int(parent[pid]) if pid in parent else None,
                              "argv": argv, "actor": actor(pid)})
    # Package processes first: they are what the review is about; npm's own tree is context.
    processes.sort(key=lambda item: item["actor"] != "package")
    return {"connects": connects[:20], "connect_count": len(connects), "persistence_writes": persistence[:20],
            "process_tree": processes[:20], "process_count": len(processes)}


def touched_canaries(opened: set[str], trace: str, stdout: str, stderr: str) -> list[str]:
    """Canary files opened, and canary values that appear in output or in process arguments."""
    touched = [item["name"] for item in CANARY["files"] if item["path"] in opened]
    if CANARY["environment"] in stdout or CANARY["environment"] in stderr:
        touched.append("environment")
    for name, value in CANARY.get("environment_vars", {}).items():
        if value in stdout or value in stderr or value in trace:
            touched.append(f"env:{name}")
    return touched


# C6: extra ulimits, still opt-in. No tmpfs on /tmp: with --read-only, /tmp is already unwritable;
# a tmpfs there loosened the sandbox and made npm's own trace overflow the 2 MB cap (2026-11-08).
HARDENING = ["--ulimit", "nofile=256:256", "--ulimit", "fsize=67108864:67108864"]


VOLUME = re.compile(r"agentnpm-[a-z0-9][a-z0-9-]{0,80}")


def docker_command(root: Path | None, hardening: bool = False, volume: str | None = None) -> list[str]:
    """`root` is a host folder (harmless fixtures only); `volume` is a Docker volume that already holds the
    extracted package (Gate B0 2026-11-09: real packages never touch the Windows disk)."""
    if (root is None) == (volume is None) or (volume is not None and not VOLUME.fullmatch(volume)):
        raise ValueError("exactly one of a package folder or an agentnpm-* volume is required")
    # The volume holds the runner's home (copied by Docker on first mount); the package is in pkg/.
    source = (f"type=volume,source={volume},target=/input,readonly,volume-subpath=pkg" if volume
              else f"type=bind,source={root},target=/input,readonly")
    environment = [f"CANARY_ENV={CANARY['environment']}"]
    environment += [f"{name}={value}" for name, value in CANARY.get("environment_vars", {}).items()]
    return [
        "docker", "run", "--rm", "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--cap-add", "SYS_PTRACE",
        "--security-opt", "no-new-privileges",
        # --memory-swap equal to --memory removes swap (C1, W5-5 option 1, PO 08/11): without it the
        # `memory` fixture reached 448 MB under a 256 MB limit.
        "--pids-limit", "64", "--memory", "256m", "--memory-swap", "256m", "--cpus", "1",
        "--user", "10001:10001", "--tmpfs", "/work:rw,exec,nosuid,size=64m,uid=10001,gid=10001",
        "--tmpfs", "/home/agent:rw,noexec,nosuid,size=1m,uid=10001,gid=10001",
        "--mount", source,
        *[part for item in environment for part in ("--env", item)],
        *(HARDENING if hardening else []),
        IMAGE, "/usr/local/bin/run_install.sh",
    ]


def _field(output: str, key: str) -> str:
    values = [part[len(key) + 1:] for part in output.splitlines() if part.startswith(key + "=")]
    if len(values) != 1:
        raise ValueError(f"invalid sandbox {key} output")
    return values[0]


def _decode(output: str, key: str) -> str:
    value = _field(output, key)
    if len(value) > 2_700_000:
        raise ValueError(f"invalid sandbox {key} output")
    return base64.b64decode(value, validate=True).decode("utf-8", errors="replace")


def run_sandbox(package: Path, hardening: bool = False) -> dict:
    try:
        root = package.resolve(strict=True)
        if not root.is_dir() or not (root / "package.json").is_file():
            raise ValueError("package directory required")
        command = docker_command(root, hardening)
    except (OSError, ValueError) as error:
        return {"ok": False, "data": None, "error": str(error)[:300]}
    return _execute(command)


def run_sandbox_volume(volume: str, hardening: bool = False) -> dict:
    """Same sandbox, package read from a Docker volume prepared by experiments.sandbox_batch."""
    try:
        command = docker_command(None, hardening, volume)
    except ValueError as error:
        return {"ok": False, "data": None, "error": str(error)[:300]}
    return _execute(command)


def _execute(command: list[str]) -> dict:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
        if result.returncode:
            raise RuntimeError(f"Docker failed: {result.stderr[-300:]}")
        status = int(_field(result.stdout, "EXIT"))
        trace_truncated = _field(result.stdout, "TRACE_TRUNCATED")
        if trace_truncated not in ("0", "1"):
            raise ValueError("invalid sandbox TRACE_TRUNCATED output")
        trace = _decode(result.stdout, "TRACE")
        stdout = _decode(result.stdout, "STDOUT")
        stderr = _decode(result.stdout, "STDERR")
        trace_complete = trace_truncated == "0" and bool(trace.strip())
        opened = set(OPEN.findall(trace))
        touched = touched_canaries(opened, trace, stdout, stderr)
        lines = trace.splitlines()
        outcome = classify_outcome(status, trace)
        if outcome != "ok":
            error = OUTCOME_ERRORS[outcome]
        else:
            error = None if trace_complete else "sandbox trace incomplete"
        return {"ok": error is None, "data": {
            "returncode": status,
            "outcome": outcome,
            "trace_complete": trace_complete,
            "stdout": {"untrusted": True, "content": stdout},
            "stderr": {"untrusted": True, "content": stderr},
            "strace": {"untrusted": True, "content": trace,
                       "truncated": trace_truncated == "1"},
            "processes": [line[:300] for line in lines if "execve(" in line][:20],
            "files_outside_package": sorted(path for path in opened if path.startswith("/")
                                            and not path.startswith("/work/"))[:50],
            "network_attempts": [line[:300] for line in lines if "connect(" in line][:20],
            "canary_touched": touched,
            "by_actor": attribute_events(trace),
            "behavior": behavior_events(trace),
        }, "error": error}
    except (OSError, ValueError, KeyError, RuntimeError, binascii.Error,
            subprocess.SubprocessError) as error:
        return {"ok": False, "data": None, "error": str(error)[:300]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a harmless fixture in the offline sandbox")
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    result = run_sandbox(args.package)
    if result["data"]:
        output_root = Path(__file__).parent / "out"
        output_root.mkdir(exist_ok=True)
        output = Path(tempfile.mkdtemp(prefix="trace-", dir=output_root)) / "strace.log"
        output.write_text(result["data"]["strace"]["content"], encoding="utf-8")
        result["data"]["strace"]["path"] = str(output)
        result["data"]["strace"].pop("content")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
