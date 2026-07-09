#!/usr/bin/env python3
"""Advisory Codex Bandit hook runner.

Hooks are intentionally non-blocking unless CODEX_BANDIT_HOOK_BLOCKING=1 is set
by an explicit user opt-in outside the plugin manifest.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


HOOK_CONFIG: dict[str, tuple[str, str, str | None]] = {
    "session-start": ("route-card", "status", None),
    "pre-commit": ("verify-stage", "verify", "green"),
    "pre-push": ("verify-stage", "verify", "adversarial"),
}


def repo_root() -> Path:
    env_root = os.environ.get("CODEX_BANDIT_REPO_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError:
        return Path.cwd().resolve()
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip()).resolve()
    return Path.cwd().resolve()


def plugin_root() -> Path:
    env_root = os.environ.get("CODEX_BANDIT_PLUGIN_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def select_work_item(root: Path) -> str | None:
    env_work_item = os.environ.get("CODEX_BANDIT_WORK_ITEM_ID")
    if env_work_item:
        return env_work_item
    work_root = root / ".codex-bandit" / "work"
    if not work_root.is_dir():
        return None
    candidates = sorted(path.name for path in work_root.iterdir() if path.is_dir())
    if len(candidates) == 1:
        return candidates[0]
    return None


def advisory_skip(reason: str) -> int:
    print(f"codex-bandit hook advisory skip: {reason}", file=sys.stderr)
    return 0


def run_hook(hook_name: str) -> int:
    if hook_name not in HOOK_CONFIG:
        return advisory_skip(f"unknown hook {hook_name!r}")

    root = repo_root()
    work_item_id = select_work_item(root)
    if not work_item_id:
        return advisory_skip("no unambiguous .codex-bandit work item")

    command, operation, stage = HOOK_CONFIG[hook_name]
    script = plugin_root() / "scripts" / command
    if not script.is_file():
        return advisory_skip(f"script not found: {script}")

    request: dict[str, Any] = {
        "schema_version": "codex-bandit.script-request.v1",
        "command": command,
        "operation": operation,
        "repo_root": str(root),
        "work_item_id": work_item_id,
        "route_card_path": f".codex-bandit/work/{work_item_id}/route-card.json",
        "ledger_path": f".codex-bandit/work/{work_item_id}/evidence.jsonl",
        "input": {},
        "caller": {"role": "orchestrator", "mode": "assisted"},
        "request_id": f"hook_{hook_name}_{work_item_id}",
    }
    if stage:
        request["stage"] = stage

    proc = subprocess.run(
        [str(script)],
        input=json.dumps(request, separators=(",", ":")),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(root),
        check=False,
    )
    if proc.stdout:
        print(proc.stdout, end="", file=sys.stderr)
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    if os.environ.get("CODEX_BANDIT_HOOK_BLOCKING") == "1":
        return proc.returncode
    return 0


def main() -> int:
    hook_name = sys.argv[1] if len(sys.argv) > 1 else "session-start"
    try:
        return run_hook(hook_name)
    except Exception as exc:  # Hooks must not break unrelated repo work.
        return advisory_skip(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
