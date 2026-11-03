"""Turn a rule-based decision into the npm command it would run (TV1-7, AGENTS §6.6).

Only this module may ever write `package.json` or call `npm approve-scripts`/`deny-scripts`.
For now it only plans the command: real execution needs its own PO-approved gate.
"""

import re
from pathlib import Path

PACKAGE_ID = re.compile(r"^(?:@[a-z0-9._-]+/)?[a-z0-9._-]+@[0-9A-Za-z.+-]+$")
COMMANDS = {"approve": "approve-scripts", "deny": "deny-scripts"}


def apply_decision(project_dir: str, package: str, decision: dict, dry_run: bool = True) -> dict:
    """Return the command for a decision from `agent.decide.decide`; never runs it.

    AGENTS §6.6 sketches `apply_decision(project_dir, verdict, dry_run=True)`; the rules
    already live in `agent.decide`, so this takes their output instead of re-deciding.
    """
    if not dry_run:
        return {"ok": False, "data": None,
                "error": "real approve/deny is disabled; it needs a separate PO-approved gate"}
    try:
        project = Path(project_dir).resolve(strict=True)
        if not (project / "package.json").is_file():
            raise ValueError("project_dir must contain package.json")
        if not PACKAGE_ID.fullmatch(package):
            raise ValueError("invalid package id")
        action = decision["action"]
        if action not in ("approve", "review", "deny"):
            raise ValueError("invalid decision action")
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {"ok": False, "data": None, "error": str(error)[:300]}
    command = ["npm", COMMANDS[action], package] if action in COMMANDS else None
    return {"ok": True, "data": {"dry_run": True, "action": action, "rule": decision.get("rule"),
                                 "command": command, "cwd": str(project)}, "error": None}
