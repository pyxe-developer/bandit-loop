#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO / "codex" / "tests"))

import run_fixture_checks as fixtures  # noqa: E402


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def run_script(name: str, request: dict) -> tuple[int, dict]:
    proc = subprocess.run(
        [str(ROOT / "scripts" / name)],
        input=json.dumps(request),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(ROOT),
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{name} emitted invalid JSON: {proc.stdout!r} {proc.stderr!r}") from exc
    return proc.returncode, payload


def dashboard_request(tmp: Path, operation: str, input_value: dict | None = None) -> dict:
    return {
        "schema_version": "codex-bandit.dashboard-request.v1",
        "operation": operation,
        "repo_root": str(tmp),
        "epic_id": "epic-42",
        "input": input_value or {},
        "request_id": f"dashboard_{operation}",
    }


def orchestrate_request(tmp: Path, operation: str) -> dict:
    return {
        "schema_version": "codex-bandit.orchestrate-request.v1",
        "operation": operation,
        "repo_root": str(tmp),
        "work_item_id": "cb-123",
        "route_card_path": ".codex-bandit/work/cb-123/route-card.json",
        "ledger_path": ".codex-bandit/work/cb-123/evidence.jsonl",
        "input": {},
        "request_id": f"orchestrate_{operation}",
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="bandit-dashboard-") as raw:
        tmp = Path(raw)
        fixtures.init_git_repo(tmp)
        route = copy.deepcopy(fixtures.route_card_base())
        route["stage_plan"]["current_stage"] = "plan"
        route["source"]["request"] = "Render <unsafe> epic state"
        fixtures.write_workdir(tmp, route, [])

        code, payload = run_script(
            "dashboard",
            dashboard_request(
                tmp,
                "upsert",
                {
                    "title": "Tracking <Epic>",
                    "description": "A durable view of delivery state.",
                    "work_item_ids": ["cb-123", "cb-missing"],
                },
            ),
        )
        assert_true(code == 0 and payload["ok"], "dashboard upsert failed")
        path = Path(payload["result"]["dashboard_path"])
        assert_true(path.exists(), "dashboard HTML was not written")
        rendered = path.read_text(encoding="utf-8")
        assert_true("Tracking &lt;Epic&gt;" in rendered, "epic title was not escaped")
        assert_true("Render &lt;unsafe&gt; epic state" in rendered, "work item text was not escaped")
        assert_true("Waiting for route card" in rendered, "missing work item was not visible")
        assert_true("Bandit epic · epic-42" in rendered, "epic identity was not visible")

        code, status = run_script("dashboard", dashboard_request(tmp, "status"))
        assert_true(code == 0 and status["result"]["counts"]["total"] == 2, "dashboard status summary was wrong")

        code, advanced = run_script("orchestrate-assisted", orchestrate_request(tmp, "next"))
        assert_true(code == 0 and advanced["stage"] == "red", "orchestrator did not advance plan to red")
        assert_true(str(path) in advanced["result"]["dashboard_paths"], "orchestrator did not report refreshed dashboard")
        refreshed = path.read_text(encoding="utf-8")
        assert_true("<strong>Red tests</strong>" in refreshed, "dashboard did not refresh after orchestration")

        bad = dashboard_request(tmp, "upsert", {"title": "Bad", "work_item_ids": ["../escape"]})
        code, payload = run_script("dashboard", bad)
        assert_true(code == 2 and payload["status"] == "invalid_input", "unsafe work item ID was accepted")

    print("Pi dashboard checks passed: 4")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
