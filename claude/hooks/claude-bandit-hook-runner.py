#!/usr/bin/env python3
"""Advisory Claude Code hook for an active Codex Bandit work item.

The hook reports route-card status at session start. It never blocks Claude
Code; users can invoke the orchestrator or stage skills for state changes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        return Path(project_dir).expanduser().resolve()
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        return Path.cwd().resolve()
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip()).resolve()
    return Path.cwd().resolve()


def plugin_root() -> Path:
    raw = os.environ.get("CLAUDE_PLUGIN_ROOT")
    return Path(raw).expanduser().resolve() if raw else Path(__file__).resolve().parents[1]


def select_work_item(root: Path) -> str | None:
    configured = os.environ.get("CODEX_BANDIT_WORK_ITEM_ID")
    if configured:
        return configured
    work_root = root / ".codex-bandit" / "work"
    if not work_root.is_dir():
        return None
    candidates = sorted(path.name for path in work_root.iterdir() if path.is_dir())
    return candidates[0] if len(candidates) == 1 else None


def run_status(root: Path, work_item_id: str) -> dict[str, Any] | None:
    request = {
        "schema_version": "codex-bandit.script-request.v1",
        "command": "route-card",
        "operation": "status",
        "repo_root": str(root),
        "work_item_id": work_item_id,
        "route_card_path": f".codex-bandit/work/{work_item_id}/route-card.json",
        "ledger_path": f".codex-bandit/work/{work_item_id}/evidence.jsonl",
        "input": {},
        "caller": {"role": "orchestrator", "mode": "assisted"},
        "request_id": f"claude_hook_session_start_{work_item_id}",
    }
    script = plugin_root() / "scripts" / "route-card"
    try:
        proc = subprocess.run(
            [str(script)],
            input=json.dumps(request, separators=(",", ":")),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(root),
            check=False,
        )
    except OSError:
        return None
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def main() -> int:
    root = repo_root()
    work_item_id = select_work_item(root)
    if not work_item_id:
        return 0
    payload = run_status(root, work_item_id)
    if not payload:
        return 0
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    stage = result.get("current_stage") or payload.get("stage") or "unknown"
    status = payload.get("status", "unknown")
    print(
        json.dumps(
            {
                "systemMessage": (
                    f"Codex Bandit advisory: work item {work_item_id} is at "
                    f"stage {stage} with status {status}. Use "
                    "codex-bandit:orchestrate to continue the governed workflow."
                )
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
