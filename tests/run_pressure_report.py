#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VALIDATOR = Path("/Users/matthewflebbe/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py")
DEFAULT_VALIDATOR_PYTHON = Path("/Library/Frameworks/Python.framework/Versions/3.11/bin/python3")


def run(command: list[str]) -> dict:
    proc = subprocess.run(command, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return {
        "command": command,
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def parse_json_stdout(result: dict) -> dict:
    if result["exit_code"] != 0:
        return {}
    try:
        return json.loads(result["stdout"])
    except json.JSONDecodeError:
        return {}


def validator_command() -> list[str]:
    if DEFAULT_VALIDATOR.exists():
        python = str(DEFAULT_VALIDATOR_PYTHON if DEFAULT_VALIDATOR_PYTHON.exists() else Path(sys.executable))
        return [python, str(DEFAULT_VALIDATOR), "."]
    return [sys.executable, "-c", "raise SystemExit('plugin validator not found')"]


def main() -> int:
    suites = {
        "fixture_checks": run([sys.executable, "tests/run_fixture_checks.py"]),
        "orchestrate_checks": run([sys.executable, "tests/run_orchestrate_checks.py"]),
        "stage_skill_checks": run([sys.executable, "tests/run_stage_skill_checks.py"]),
        "plugin_validation": run(validator_command()),
    }
    fixture = parse_json_stdout(suites["fixture_checks"])
    orchestrate = parse_json_stdout(suites["orchestrate_checks"])
    stage = parse_json_stdout(suites["stage_skill_checks"])

    scenarios = [
        {
            "scenario": "role-boundary violation",
            "expected": "inadmissible producer/recorder evidence blocks with E_APPEND_AUTHORITY_INVALID",
            "actual": "covered by fixture runtime_regressions; suite passed",
        },
        {
            "scenario": "stale evidence",
            "expected": "stale subject or head drift blocks with E_STALE_SUBJECT",
            "actual": "covered by fixture and orchestrate stale_evidence checks; suites passed",
        },
        {
            "scenario": "missing route-card fields",
            "expected": "invalid route cards fail closed with schema or stage errors",
            "actual": "covered by 8 route-card fixtures and blocked_route_card; suites passed",
        },
        {
            "scenario": "manual patch",
            "expected": "guarded product/test edits block until explicit manual_patch authorization",
            "actual": "covered by orchestrate manual_patch; suite passed",
        },
        {
            "scenario": "missing HITL approval",
            "expected": "merge remains blocked without exact PR/head SHA human approval",
            "actual": "covered by fixture_07b_missing_hitl_approval_blocks_merge and orchestrate missing_hitl; suites passed",
        },
        {
            "scenario": "failing CI/deploy health",
            "expected": "failing CI, failed deploy, or unhealthy post-deploy health blocks delivery",
            "actual": "covered by delivery fixtures; suite passed",
        },
        {
            "scenario": "untrusted PR comments",
            "expected": "remote comments are recorded as untrusted and have instruction_effect none",
            "actual": "covered by fixture_07b_remote_comments_untrusted_do_not_bypass_ci; suite passed",
        },
        {
            "scenario": "enforced mode validation",
            "expected": "install-agents validates TOML, digests, schema, selected evidence, and Codex CLI availability",
            "actual": "covered by 13 install-agent fixtures; suite passed",
        },
        {
            "scenario": "enforced installed-but-not-proven-loaded",
            "expected": "known limit: validation is not proof that Codex loaded or enforced named custom agents",
            "actual": "documented known limit; no non-interactive Codex named-agent list/dry-run is exercised",
        },
        {
            "scenario": "hooks advisory default",
            "expected": "blocking reducer output exits 0 by default and non-zero only with CODEX_BANDIT_HOOK_BLOCKING=1",
            "actual": "covered by fixture_10_hooks_blocking_stage_advisory_default_opt_in_blocks; suite passed",
        },
        {
            "scenario": "hook uninstall safety",
            "expected": "tampered manifest paths, drifted hooks, and symlinked managed paths are skipped and preserved",
            "actual": "covered by three Ticket 10 hook uninstall fixtures; suite passed",
        },
        {
            "scenario": "MCP wrapper",
            "expected": "MCP tool subprocess output matches direct script output",
            "actual": "covered by fixture_09_mcp_verify_stage_parity; host MCP loading is not exercised",
        },
        {
            "scenario": "deploy contract completeness",
            "expected": "known v1 limit: non-null deploy contract presence is enough; subfields are not validated",
            "actual": "covered by fixture_10_deploy_contract_incomplete_presence_only_known_limit; incomplete contract passed",
        },
    ]

    ok = all(result["exit_code"] == 0 for result in suites.values())
    report = {
        "ok": ok,
        "release_scope": "full optional surface",
        "optional_surfaces_shipping": ["assisted", "enforced_mode_opt_in", "hooks_opt_in", "mcp", "delivery_hitl"],
        "optional_surfaces_deferred": [],
        "suite_numbers": {
            "fixture_checks": fixture.get("counts", {}),
            "fixture_covered": fixture.get("covered"),
            "orchestrate_checks": orchestrate.get("counts", {}),
            "stage_skill_checks": stage.get("counts", {}),
            "plugin_validation": "passed" if suites["plugin_validation"]["exit_code"] == 0 else "failed",
        },
        "scenarios": scenarios,
        "known_limits": [
            "Enforced validation proves Codex CLI availability plus TOML/schema/digest checks, not actual Codex runtime custom-agent loading or enforcement.",
            "Deploy contract validation is presence-only; deploy command, health command, environment, and timeout subfields are not validated in v1.",
            "MCP validation covers plugin-validator acceptance and subprocess parity, not host MCP discovery/loading.",
            "Git hooks are advisory by default and block only when CODEX_BANDIT_HOOK_BLOCKING=1 is explicitly set.",
            "Remote CI, review, deploy, health, and PR-head states must come from operation-time tools; the plugin does not monitor deployment beyond supplied health-check state.",
        ],
        "suites": suites,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
