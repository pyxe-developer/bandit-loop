#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import run_fixture_checks as fixtures  # noqa: E402


class OrchestrateCheckError(AssertionError):
    pass


def assert_true(condition, message: str) -> None:
    if not condition:
        raise OrchestrateCheckError(message)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise OrchestrateCheckError(f"{message}: expected {expected!r}, got {actual!r}")


def fixture_file(name: str) -> dict:
    return json.loads((ROOT / "references" / "fixtures" / name).read_text(encoding="utf-8"))


def request(tmp: Path, operation: str, *, input_value: dict | None = None, request_id: str = "orch") -> dict:
    return {
        "schema_version": "codex-bandit.orchestrate-request.v1",
        "operation": operation,
        "repo_root": str(tmp),
        "work_item_id": "cb-123",
        "route_card_path": ".codex-bandit/work/cb-123/route-card.json",
        "ledger_path": ".codex-bandit/work/cb-123/evidence.jsonl",
        "input": input_value or {},
        "request_id": request_id,
    }


def run_orchestrate(tmp: Path, operation: str, *, input_value: dict | None = None, request_id: str = "orch") -> tuple[int, dict]:
    proc = subprocess.run(
        [str(ROOT / "scripts" / "orchestrate-assisted")],
        input=json.dumps(request(tmp, operation, input_value=input_value, request_id=request_id)),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(ROOT),
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise OrchestrateCheckError(f"orchestrate-assisted emitted invalid JSON: exit={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}") from exc
    assert_equal(payload.get("schema_version"), "codex-bandit.orchestrate-response.v1", f"{request_id} schema")
    return proc.returncode, payload


def load_route(tmp: Path) -> dict:
    return json.loads((tmp / ".codex-bandit" / "work" / "cb-123" / "route-card.json").read_text(encoding="utf-8"))


def ledger_events(tmp: Path) -> list[dict]:
    path = tmp / ".codex-bandit" / "work" / "cb-123" / "evidence.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def blocker_codes(payload: dict) -> list[str]:
    return [item.get("code") for item in payload.get("blockers", [])]


def warning_codes(payload: dict) -> list[str]:
    return [item.get("code") for item in payload.get("warnings", [])]


def setup_work_item(tmp: Path, route: dict | None = None, events: list[dict] | None = None) -> dict:
    fixtures.init_git_repo(tmp)
    route = copy.deepcopy(route or fixtures.route_card_base())
    fixtures.write_workdir(tmp, route, copy.deepcopy(events or []))
    return route


def check_blocked_route_card() -> int:
    with tempfile.TemporaryDirectory(prefix="codex-bandit-orch-invalid-") as td:
        tmp = Path(td)
        route = fixtures.route_card_base()
        route["stage_plan"]["current_stage"] = "missing_stage"
        exit_code, payload = run_orchestrate(tmp, "create", input_value={"route_card": route}, request_id="orch_invalid_route")
        assert_equal(exit_code, 2, "invalid route exit")
        assert_equal(payload["status"], "invalid_input", "invalid route status")
        assert_true(any(item.get("code") == "E_ROUTE_CARD_STAGE_NOT_ENABLED" for item in payload["errors"]), "invalid route returned route-card schema error")
    return 1


def check_resume_and_review_digest_wire_up() -> int:
    with tempfile.TemporaryDirectory(prefix="codex-bandit-orch-digest-") as td:
        tmp = Path(td)
        setup_work_item(tmp, events=fixtures.events_by_name("fixture_02b_multi_commit_red_green_active")[:2])
        exit_code, payload = run_orchestrate(tmp, "next", request_id="orch_resume_red")
        assert_equal(exit_code, 0, "resume red exit")
        assert_equal(payload["stage"], "green", "resume advanced to green")
        assert_equal(load_route(tmp)["stage_plan"]["current_stage"], "green", "route card current stage after resume")

        exit_code, payload = run_orchestrate(tmp, "next", request_id="orch_green_to_adv")
        assert_equal(exit_code, 0, "green to adversarial exit")
        assert_equal(payload["stage"], "adversarial", "advanced to adversarial")
        route = load_route(tmp)
        package = route["evidence"]["review_package"]
        assert_true(isinstance(package, dict), "review package pointer written")
        assert_true(str(package.get("digest", "")).startswith("sha256:"), "review package digest written")
        assert_true(str(package.get("diff_digest", "")).startswith("sha256:"), "review package diff digest written")
        assert_equal(route["stage_plan"]["current_stage"], "adversarial", "route card current stage after digest wire-up")

        old_digest_events = fixtures.events_by_name("fixture_02b_multi_commit_red_green_active")
        fixtures.write_workdir(tmp, route, old_digest_events)
        exit_code, payload = fixtures.run_script(tmp, fixtures.request_base("verify-stage", "verify", stage="adversarial"))
        assert_equal(exit_code, 1, "old adversarial digest now blocks")
        assert_true("E_REVIEW_PACKAGE_DIGEST_MISMATCH" in blocker_codes(payload), "wired digest makes stale fixture verdict decorative no longer")
    return 1


def check_adversarial_resume_requires_wired_digest() -> int:
    checks = 0
    with tempfile.TemporaryDirectory(prefix="codex-bandit-orch-adv-resume-") as td:
        tmp = Path(td)
        route = fixtures.route_card_base()
        route["stage_plan"]["current_stage"] = "adversarial"
        route["evidence"]["review_package"] = None
        setup_work_item(tmp, route=route, events=fixtures.events_by_name("fixture_02b_multi_commit_red_green_active")[:2])
        exit_code, payload = run_orchestrate(tmp, "next", request_id="orch_adv_resume_wire")
        assert_equal(exit_code, 1, "adversarial resume dispatch exit")
        assert_equal(payload["next_action"], "dispatch_role", "adversarial resume dispatch action")
        route = load_route(tmp)
        digest = route["evidence"]["review_package"]["digest"]
        assert_true(str(digest).startswith("sha256:"), "adversarial resume wired review package digest")
        assert_equal(payload["result"]["dispatch_request"]["subject"]["review_package_digest"], digest, "adversarial dispatch carries wired digest")
        checks += 1

    with tempfile.TemporaryDirectory(prefix="codex-bandit-orch-adv-apply-missing-") as td:
        tmp = Path(td)
        route = fixtures.route_card_base()
        route["stage_plan"]["current_stage"] = "adversarial"
        route["evidence"]["review_package"] = None
        setup_work_item(tmp, route=route, events=fixtures.events_by_name("fixture_02b_multi_commit_red_green_active")[:2])
        role_output = {
            "schema_version": "codex-bandit.role-output.v1",
            "dispatch_id": "disp_adv_missing_pkg",
            "work_item_id": "cb-123",
            "stage": "adversarial",
            "actor": {"role": "adversarial_reviewer", "mode": "assisted"},
            "outcome": "success",
            "summary": "approve without package",
            "proposed_evidence": [{"record_type": "verdict", "actor": {"role": "adversarial_reviewer", "mode": "assisted"}, "claim": "adversarial_approved_current_review_package", "status": "pass", "verdict": {"schema_version": "codex-bandit.verdict.v1", "verdict": "approve", "rubric_ids": ["S4_REVIEW", "R6_EVIDENCE_BINDING"], "reviewed_evidence_ids": ["ev_red_001", "ev_green_001"], "review_package_digest": None, "subject": {"base_ref": "main", "head_ref": "codex-bandit/cb-123", "head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "review_package_digest": None}, "findings": [], "test_surface_findings": [], "cannot_judge_reason": None}}],
            "route_card_patch": None,
            "blockers": [],
            "reroute": None,
        }
        dispatch = {
            "schema_version": "codex-bandit.stage-dispatch-request.v1",
            "dispatch_id": "disp_adv_missing_pkg",
            "work_item_id": "cb-123",
            "stage": "adversarial",
            "target_role": "adversarial_reviewer",
            "capability_mode": "assisted",
            "route_card": {"path": ".codex-bandit/work/cb-123/route-card.json", "digest": "sha256:test"},
            "reducer_status": {"adversarial": "not_started"},
            "required_inputs": {"evidence_ids": ["ev_red_001", "ev_green_001"], "report_paths": [], "commands": ["review_package"]},
            "role_contract": {"can_edit": [], "must_not_edit": ["**"], "can_append_evidence": ["verdict", "blocker"], "must_return": ["role_output"]},
            "subject": {"base_ref": "main", "head_ref": "codex-bandit/cb-123", "expected_head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "review_package_digest": None},
        }
        exit_code, payload = run_orchestrate(tmp, "apply-role-output", input_value={"dispatch_request": dispatch, "role_output": role_output}, request_id="orch_adv_apply_missing_pkg")
        assert_equal(exit_code, 1, "adversarial apply missing package exit")
        assert_true("E_REVIEW_PACKAGE_DIGEST_REQUIRED" in blocker_codes(payload), "adversarial apply missing package blocks")
        checks += 1
    return checks


def check_adversarial_null_digest_rejected_with_real_package() -> int:
    checks = 0
    with tempfile.TemporaryDirectory(prefix="codex-bandit-orch-null-digest-") as td:
        tmp = Path(td)
        route = fixtures.route_card_base()
        route["stage_plan"]["current_stage"] = "adversarial"
        route["evidence"]["review_package"] = {"digest": "sha256:REALPKG"}
        events = fixtures.events_by_name("fixture_02b_multi_commit_red_green_active")
        events[-1]["verdict"]["review_package_digest"] = None
        events[-1]["verdict"]["subject"]["review_package_digest"] = None
        events[-1]["subject"]["review_package_digest"] = None
        setup_work_item(tmp, route=route, events=events)
        core_exit, core_payload = fixtures.run_script(tmp, fixtures.request_base("verify-stage", "verify", stage="adversarial"))
        assert_equal(core_exit, 0, "precondition core reducer still passes null digest")
        assert_true(core_payload["ok"], "precondition core reducer pass demonstrates orchestrator-side guard")
        exit_code, payload = run_orchestrate(tmp, "next", request_id="orch_null_digest_next")
        assert_equal(exit_code, 1, "orchestrator rejects null digest pass")
        assert_true("E_REVIEW_PACKAGE_DIGEST_MISMATCH" in blocker_codes(payload), "orchestrator null digest mismatch blocker")
        assert_equal(load_route(tmp)["stage_plan"]["current_stage"], "adversarial", "null digest did not advance")
        checks += 1

    with tempfile.TemporaryDirectory(prefix="codex-bandit-orch-null-role-") as td:
        tmp = Path(td)
        route = fixtures.route_card_base()
        route["stage_plan"]["current_stage"] = "adversarial"
        route["evidence"]["review_package"] = {"digest": "sha256:REALPKG"}
        setup_work_item(tmp, route=route, events=fixtures.events_by_name("fixture_02b_multi_commit_red_green_active")[:2])
        role_output = {
            "schema_version": "codex-bandit.role-output.v1",
            "dispatch_id": "disp_adv_null_digest",
            "work_item_id": "cb-123",
            "stage": "adversarial",
            "actor": {"role": "adversarial_reviewer", "mode": "assisted"},
            "outcome": "success",
            "summary": "null digest",
            "proposed_evidence": [{"record_type": "verdict", "actor": {"role": "adversarial_reviewer", "mode": "assisted"}, "claim": "adversarial_approved_current_review_package", "status": "pass", "verdict": {"schema_version": "codex-bandit.verdict.v1", "verdict": "approve", "rubric_ids": ["S4_REVIEW", "R6_EVIDENCE_BINDING"], "reviewed_evidence_ids": ["ev_red_001", "ev_green_001"], "review_package_digest": None, "subject": {"base_ref": "main", "head_ref": "codex-bandit/cb-123", "head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "review_package_digest": None}, "findings": [], "test_surface_findings": [], "cannot_judge_reason": None}}],
            "route_card_patch": None,
            "blockers": [],
            "reroute": None,
        }
        dispatch = {
            "schema_version": "codex-bandit.stage-dispatch-request.v1",
            "dispatch_id": "disp_adv_null_digest",
            "work_item_id": "cb-123",
            "stage": "adversarial",
            "target_role": "adversarial_reviewer",
            "capability_mode": "assisted",
            "route_card": {"path": ".codex-bandit/work/cb-123/route-card.json", "digest": "sha256:test"},
            "reducer_status": {"adversarial": "not_started"},
            "required_inputs": {"evidence_ids": ["ev_red_001", "ev_green_001"], "report_paths": [], "commands": ["review_package"]},
            "role_contract": {"can_edit": [], "must_not_edit": ["**"], "can_append_evidence": ["verdict", "blocker"], "must_return": ["role_output"]},
            "subject": {"base_ref": "main", "head_ref": "codex-bandit/cb-123", "expected_head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "review_package_digest": "sha256:REALPKG"},
        }
        exit_code, payload = run_orchestrate(tmp, "apply-role-output", input_value={"dispatch_request": dispatch, "role_output": role_output}, request_id="orch_adv_null_role")
        assert_equal(exit_code, 1, "adversarial role null digest exit")
        assert_true("E_REVIEW_PACKAGE_DIGEST_REQUIRED" in blocker_codes(payload), "adversarial role null digest blocks before append")
        assert_true(not any(event.get("stage") == "adversarial" for event in ledger_events(tmp)), "null digest verdict not appended")
        checks += 1
    return checks


def check_apply_dispatch_fixture_success() -> int:
    with tempfile.TemporaryDirectory(prefix="codex-bandit-orch-dispatch-") as td:
        tmp = Path(td)
        route = fixtures.route_card_base()
        route["stage_plan"]["current_stage"] = "green"
        setup_work_item(tmp, route=route, events=fixtures.events_by_name("fixture_02b_red_pass_active"))
        dispatch_fixture = fixture_file("stage-dispatch.json")["fixtures"][0]
        exit_code, payload = run_orchestrate(
            tmp,
            "apply-role-output",
            input_value={"dispatch_request": dispatch_fixture["request"], "role_output": dispatch_fixture["role_output"]},
            request_id="orch_apply_green",
        )
        assert_equal(exit_code, 0, "apply green role output exit")
        assert_equal(payload["status"], "pass", "apply green role output status")
        events = ledger_events(tmp)
        assert_true(any(event.get("stage") == "green" and event.get("record_type") == "command" for event in events), "green command evidence appended")
        assert_true(any(event.get("stage") == "green" and event.get("recorded_by", {}).get("role") == "orchestrator" for event in events), "assisted evidence recorded by orchestrator")
        assert_true(payload["result"]["stage_status"]["ok"], "reducer accepted appended green evidence")
    return 1


def check_stale_evidence_blocks() -> int:
    with tempfile.TemporaryDirectory(prefix="codex-bandit-orch-stale-") as td:
        tmp = Path(td)
        route = fixtures.route_card_base()
        route["stage_plan"]["current_stage"] = "green"
        setup_work_item(tmp, route=route, events=fixtures.events_by_name("fixture_02b_green_stale_head"))
        exit_code, payload = run_orchestrate(tmp, "next", request_id="orch_stale_green")
        assert_equal(exit_code, 3, "stale evidence exit")
        assert_equal(payload["status"], "stale", "stale evidence status")
        assert_true("E_STAGE_ATTEMPT_SUBJECT_DIVERGED" in blocker_codes(payload), "stale blocker preserved from reducer")
        assert_equal(load_route(tmp)["stage_plan"]["current_stage"], "green", "stale evidence did not advance route card")
    return 1


def check_manual_patch_guard() -> int:
    with tempfile.TemporaryDirectory(prefix="codex-bandit-orch-manual-") as td:
        tmp = Path(td)
        route = fixtures.route_card_base()
        route["stage_plan"]["current_stage"] = "green"
        setup_work_item(tmp, route=route, events=fixtures.events_by_name("fixture_02b_red_pass_active"))
        for raw_path in ["src/invoice.ts", "./src/invoice.ts", "./tests/test_invoice.ts", "src/../src/invoice.ts"]:
            exit_code, payload = run_orchestrate(tmp, "guard-edit", input_value={"paths": [raw_path]}, request_id=f"orch_guard_edit_{raw_path.replace('/', '_').replace('.', 'dot')}")
            assert_equal(exit_code, 1, f"guard edit exit before manual patch for {raw_path}")
            assert_true("E_ORCHESTRATOR_EDIT_REQUIRES_ESCAPE" in blocker_codes(payload), f"guard edit blocks normalized path {raw_path}")

        outside = str(tmp.parent / "outside.ts")
        exit_code, payload = run_orchestrate(tmp, "guard-edit", input_value={"paths": [outside]}, request_id="orch_guard_outside")
        assert_equal(exit_code, 1, "guard edit exit before manual patch")
        assert_true("E_EDIT_PATH_OUTSIDE_REPO" in blocker_codes(payload), "guard edit blocks outside-repo absolute path")

        exit_code, payload = run_orchestrate(tmp, "record-escape", input_value={"kind": "manual_patch", "reason": "human authorized patch", "approved_by": "matthew", "paths": ["./src/invoice.ts"]}, request_id="orch_manual_patch")
        assert_equal(exit_code, 0, "manual patch record exit")
        assert_true(any(event.get("claim") == "manual_patch" for event in ledger_events(tmp)), "manual patch transition recorded")

        exit_code, payload = run_orchestrate(tmp, "guard-edit", input_value={"paths": ["src/invoice.ts"]}, request_id="orch_guard_after_manual")
        assert_equal(exit_code, 0, "guard edit exit after manual patch")
        assert_equal(payload["status"], "pass", "manual patch authorizes guarded edit once")
        assert_true(any(event.get("claim") == "manual_patch_consumed" for event in ledger_events(tmp)), "manual patch authorization consumed")

        exit_code, payload = run_orchestrate(tmp, "guard-edit", input_value={"paths": ["src/invoice.ts"]}, request_id="orch_guard_after_consumed")
        assert_equal(exit_code, 1, "guard edit exit after manual patch consumed")
        assert_true("E_ORCHESTRATOR_EDIT_REQUIRES_ESCAPE" in blocker_codes(payload), "manual patch must be re-authorized for a later edit")
    return 1


def check_repair_attempt_budget_tracks_and_blocks() -> int:
    with tempfile.TemporaryDirectory(prefix="codex-bandit-orch-budget-") as td:
        tmp = Path(td)
        route = fixtures.route_card_base()
        route["stage_plan"]["current_stage"] = "green"
        setup_work_item(tmp, route=route, events=fixtures.events_by_name("fixture_02b_multi_commit_red_green_active")[:2])
        dispatch_fixture = fixture_file("stage-dispatch.json")["fixtures"][0]
        for idx, expected_attempt in [(1, "cb-123:green:attempt-2"), (2, "cb-123:green:attempt-3")]:
            role_output = copy.deepcopy(dispatch_fixture["role_output"])
            dispatch = copy.deepcopy(dispatch_fixture["request"])
            dispatch["dispatch_id"] = f"disp_green_budget_{idx}"
            role_output["dispatch_id"] = dispatch["dispatch_id"]
            exit_code, payload = run_orchestrate(
                tmp,
                "apply-role-output",
                input_value={"dispatch_request": dispatch, "role_output": role_output},
                request_id=f"orch_budget_green_{idx}",
            )
            assert_equal(exit_code, 0, f"green repair attempt {idx} exit")
            events = [event for event in ledger_events(tmp) if event.get("stage") == "green" and event.get("record_type") == "command"]
            assert_equal(events[-1]["stage_attempt_id"], expected_attempt, f"green repair attempt {idx} attempt id")
            assert_equal(load_route(tmp)["stage_plan"]["repair_loop_budget"]["used_total"], idx, f"repair budget used_total after attempt {idx}")

        role_output = copy.deepcopy(dispatch_fixture["role_output"])
        dispatch = copy.deepcopy(dispatch_fixture["request"])
        dispatch["dispatch_id"] = "disp_green_budget_exhausted"
        role_output["dispatch_id"] = dispatch["dispatch_id"]
        exit_code, payload = run_orchestrate(
            tmp,
            "apply-role-output",
            input_value={"dispatch_request": dispatch, "role_output": role_output},
            request_id="orch_budget_green_exhausted",
        )
        assert_equal(exit_code, 1, "green repair budget exhausted exit")
        assert_true("E_REPAIR_BUDGET_EXHAUSTED" in blocker_codes(payload), "repair budget exhaustion blocks")
        assert_equal(load_route(tmp)["stage_plan"]["repair_loop_budget"]["used_total"], 2, "blocked repair does not expand budget")
    return 1


def check_route_card_patch_refusal_regression() -> int:
    with tempfile.TemporaryDirectory(prefix="codex-bandit-orch-routepatch-") as td:
        tmp = Path(td)
        route = fixtures.route_card_base()
        route["stage_plan"]["current_stage"] = "green"
        setup_work_item(tmp, route=route, events=fixtures.events_by_name("fixture_02b_red_pass_active"))
        dispatch_fixture = fixture_file("stage-dispatch.json")["fixtures"][0]
        role_output = copy.deepcopy(dispatch_fixture["role_output"])
        role_output["route_card_patch"] = {"set": {"stage_plan.current_stage": "adversarial"}}
        exit_code, payload = run_orchestrate(
            tmp,
            "apply-role-output",
            input_value={"dispatch_request": dispatch_fixture["request"], "role_output": role_output},
            request_id="orch_route_patch_refusal",
        )
        assert_equal(exit_code, 1, "route_card_patch refusal exit")
        assert_true("E_ROUTE_PATCH_REQUIRES_ORCHESTRATOR_REVIEW" in blocker_codes(payload), "route_card_patch refusal blocker")
        assert_true(not any(event.get("stage") == "green" and event.get("record_type") == "command" for event in ledger_events(tmp)), "route_card_patch refusal happens before append")
    return 1


def check_deferred_delivery_routes_to_closeout() -> int:
    with tempfile.TemporaryDirectory(prefix="codex-bandit-orch-defer-") as td:
        tmp = Path(td)
        route = fixtures.route_card_base()
        route["stage_plan"]["current_stage"] = "prepare_pr"
        route["evidence"]["review_package"] = {"digest": "sha256:reviewpkg"}
        setup_work_item(tmp, route=route, events=fixtures.events_by_name("fixture_02b_multi_commit_red_green_active"))
        exit_code, payload = run_orchestrate(tmp, "record-escape", input_value={"kind": "defer_delivery", "reason": "user deferred delivery", "approved_by": "matthew"}, request_id="orch_defer")
        assert_equal(exit_code, 0, "defer delivery record exit")
        exit_code, payload = run_orchestrate(tmp, "next", request_id="orch_defer_next")
        assert_equal(exit_code, 0, "defer next exit")
        assert_equal(payload["stage"], "closeout", "defer routes to closeout")
        assert_equal(load_route(tmp)["stage_plan"]["current_stage"], "closeout", "route card current stage closeout after deferral")
    return 1


def check_missing_hitl_approval_blocks() -> int:
    with tempfile.TemporaryDirectory(prefix="codex-bandit-orch-hitl-missing-") as td:
        tmp = Path(td)
        route = fixtures.route_card_base()
        route["stage_plan"]["current_stage"] = "hitl_merge_checkpoint"
        route["evidence"]["review_package"] = {"digest": "sha256:reviewpkg"}
        setup_work_item(tmp, route=route, events=fixtures.events_by_name("fixture_02b_multi_commit_red_green_active"))
        exit_code, payload = run_orchestrate(tmp, "next", request_id="orch_missing_hitl")
        assert_equal(exit_code, 1, "missing HITL exit")
        assert_equal(payload["next_action"], "await_human_merge_approval", "missing HITL awaits human approval")
        assert_true("E_HITL_APPROVAL_REQUIRED" in blocker_codes(payload), "missing HITL approval blocker preserved")
        assert_equal(load_route(tmp)["stage_plan"]["current_stage"], "hitl_merge_checkpoint", "missing HITL did not advance")
    return 1


def check_hitl_remote_head_seam_blocks_auto_advance() -> int:
    with tempfile.TemporaryDirectory(prefix="codex-bandit-orch-hitl-seam-") as td:
        tmp = Path(td)
        route = fixtures.route_card_base()
        route["stage_plan"]["current_stage"] = "hitl_merge_checkpoint"
        route["evidence"]["review_package"] = {"digest": "sha256:reviewpkg"}
        hitl = next(item for item in fixture_file("verdict-delivery.json")["fixtures"] if item["name"] == "fixture_02d_hitl_merge_approval_valid")["evidence_event"]
        setup_work_item(tmp, route=route, events=fixtures.events_by_name("fixture_02b_multi_commit_red_green_active") + [hitl])
        exit_code, payload = run_orchestrate(tmp, "next", request_id="orch_hitl_seam")
        assert_equal(exit_code, 1, "HITL seam exit")
        assert_equal(payload["next_action"], "ticket_07_remote_head_check_required", "HITL seam next action")
        assert_true("W_OPERATION_TIME_REMOTE_HEAD_REQUIRED" in warning_codes(payload), "HITL seam warning preserved")
        assert_true("E_OPERATION_TIME_REMOTE_HEAD_REQUIRED" in blocker_codes(payload), "HITL pass is not merge-ready in orchestration")
        assert_equal(load_route(tmp)["stage_plan"]["current_stage"], "hitl_merge_checkpoint", "HITL pass did not auto-advance to land_deploy")
    return 1


def check_land_deploy_prereqs_respected() -> int:
    with tempfile.TemporaryDirectory(prefix="codex-bandit-orch-land-") as td:
        tmp = Path(td)
        route = fixtures.route_card_base()
        route["stage_plan"]["current_stage"] = "land_deploy"
        setup_work_item(tmp, route=route, events=[])
        exit_code, payload = run_orchestrate(tmp, "next", request_id="orch_land_prereq")
        assert_equal(exit_code, 3, "land_deploy prereq exit")
        assert_equal(payload["next_action"], "ticket_07_delivery_operation_required", "land_deploy blocked for Ticket 07")
        assert_true("E_ADVERSARIAL_APPROVAL_REQUIRED" in blocker_codes(payload), "land_deploy adversarial approval blocker preserved")
        assert_equal(load_route(tmp)["stage_plan"]["current_stage"], "land_deploy", "land_deploy block did not reroute around exit 3")
    return 1


def main() -> int:
    counts = {
        "blocked_route_card": check_blocked_route_card(),
        "resume_digest_wire_up": check_resume_and_review_digest_wire_up(),
        "adversarial_resume_digest": check_adversarial_resume_requires_wired_digest(),
        "adversarial_null_digest": check_adversarial_null_digest_rejected_with_real_package(),
        "dispatch_fixture_success": check_apply_dispatch_fixture_success(),
        "stale_evidence": check_stale_evidence_blocks(),
        "manual_patch": check_manual_patch_guard(),
        "repair_budget": check_repair_attempt_budget_tracks_and_blocks(),
        "route_card_patch_refusal": check_route_card_patch_refusal_regression(),
        "deferred_delivery": check_deferred_delivery_routes_to_closeout(),
        "missing_hitl": check_missing_hitl_approval_blocks(),
        "hitl_remote_head_seam": check_hitl_remote_head_seam_blocks_auto_advance(),
        "land_deploy_prereqs": check_land_deploy_prereqs_respected(),
    }
    print(json.dumps({"ok": True, "counts": counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OrchestrateCheckError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
