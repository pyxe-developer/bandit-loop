#!/usr/bin/env python3
"""Assisted orchestration layer over the Codex Bandit core scripts."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from bandit_runtime import (  # noqa: E402
    HITL_REMOTE_HEAD_WARNING,
    ROLE_OUTPUT,
    TOOL_VERSION,
    digest_bytes,
    digest_json,
    validate_role_output,
)
from dashboard_runtime import refresh_for_work_item  # noqa: E402


REQUEST_SCHEMA = "codex-bandit.orchestrate-request.v1"
RESPONSE_SCHEMA = "codex-bandit.orchestrate-response.v1"
SCRIPT_REQUEST = "codex-bandit.script-request.v1"
EVIDENCE = "codex-bandit.evidence.v1"

STAGE_ORDER = [
    "plan",
    "red",
    "green",
    "adversarial",
    "prepare_pr",
    "hitl_merge_checkpoint",
    "land_deploy",
    "closeout",
]
STAGE_ROLE = {
    "plan": "issue_planner",
    "red": "test_writer",
    "green": "code_writer",
    "adversarial": "adversarial_reviewer",
    "prepare_pr": "prepare_pr",
    "hitl_merge_checkpoint": "human",
    "land_deploy": "land_deploy",
    "closeout": "closeout_retro",
}
DRIFT_BLOCKERS = {
    "E_STALE_SUBJECT",
    "E_STAGE_ATTEMPT_SUBJECT_DIVERGED",
    "E_DIRTY_WORKTREE",
    "E_MISSING_PREREQUISITE",
    "E_RED_REQUIRED",
    "E_GREEN_REQUIRED",
    "E_ADVERSARIAL_APPROVAL_REQUIRED",
    "E_GIT_HEAD_UNAVAILABLE",
    "E_ROUTE_CARD_WORK_ITEM_MISMATCH",
}
ADVERSARIAL_DIGEST_BLOCKER = "E_REVIEW_PACKAGE_DIGEST_REQUIRED"
MANUAL_PATCH_CONSUMED_CLAIM = "manual_patch_consumed"


class OrchestrateError(Exception):
    def __init__(
        self,
        status: str,
        code: str,
        message: str,
        *,
        blockers: list[dict[str, Any]] | None = None,
        errors: list[dict[str, Any]] | None = None,
        warnings: list[dict[str, Any]] | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.blockers = blockers or []
        self.errors = errors or []
        self.warnings = warnings or []
        self.result = result or {}


def blocker(
    code: str,
    message: str,
    *,
    stage: str | None,
    owner_role: str = "orchestrator",
    retryable: bool = True,
    requires_human: bool = False,
    evidence_ids: list[str] | None = None,
    suggested_next_stage: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "code": code,
        "severity": "blocker",
        "message": message,
        "stage": stage or "plan",
        "owner_role": owner_role,
        "retryable": retryable,
        "requires_human": requires_human,
    }
    if evidence_ids:
        out["evidence_ids"] = evidence_ids
    if suggested_next_stage:
        out["suggested_next_stage"] = suggested_next_stage
    return out


def error(code: str, message: str, *, field_path: str | None = None) -> dict[str, Any]:
    out = {"code": code, "message": message}
    if field_path:
        out["field_path"] = field_path
    return out


def response(
    request: dict[str, Any] | None,
    *,
    ok: bool,
    status: str,
    stage: str | None = None,
    next_action: str | None = None,
    result: dict[str, Any] | None = None,
    blockers: list[dict[str, Any]] | None = None,
    errors: list[dict[str, Any]] | None = None,
    warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": RESPONSE_SCHEMA,
        "request_id": request.get("request_id") if isinstance(request, dict) else None,
        "ok": ok,
        "status": status,
        "work_item_id": request.get("work_item_id") if isinstance(request, dict) else None,
        "stage": stage,
        "next_action": next_action,
        "result": result or {},
        "blockers": blockers or [],
        "errors": errors or [],
        "warnings": warnings or [],
    }


def emit(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    if payload["ok"]:
        return 0
    if payload["status"] == "invalid_input":
        return 2
    if payload["status"] == "runtime_error":
        return 4
    if payload["status"] == "stale":
        return 3
    if any(item.get("code") in DRIFT_BLOCKERS for item in payload.get("blockers", [])):
        return 3
    return 1


def read_request() -> tuple[dict[str, Any] | None, str | None]:
    raw = sys.stdin.read()
    if not raw.strip():
        return None, "empty request"
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"request is not JSON: {exc.msg}"
    if not isinstance(value, dict):
        return None, "request must be a JSON object"
    return value, None


def require_request(request: dict[str, Any]) -> None:
    if request.get("schema_version") != REQUEST_SCHEMA:
        raise OrchestrateError(
            "invalid_input",
            "E_SCHEMA_INVALID",
            "schema_version must be codex-bandit.orchestrate-request.v1",
            errors=[error("E_SCHEMA_INVALID", "schema_version must be codex-bandit.orchestrate-request.v1", field_path="/schema_version")],
        )
    for key in ["operation", "repo_root", "work_item_id", "route_card_path", "ledger_path", "input", "request_id"]:
        if key not in request:
            raise OrchestrateError(
                "invalid_input",
                "E_SCHEMA_INVALID",
                f"{key} is required",
                errors=[error("E_SCHEMA_INVALID", f"{key} is required", field_path=f"/{key}")],
            )
    if not isinstance(request["input"], dict):
        raise OrchestrateError(
            "invalid_input",
            "E_SCHEMA_INVALID",
            "input must be an object",
            errors=[error("E_SCHEMA_INVALID", "input must be an object", field_path="/input")],
        )


def script_request(request: dict[str, Any], command: str, operation: str, *, stage: str | None = None, input_value: dict[str, Any] | None = None) -> dict[str, Any]:
    out = {
        "schema_version": SCRIPT_REQUEST,
        "command": command,
        "operation": operation,
        "repo_root": request["repo_root"],
        "work_item_id": request["work_item_id"],
        "route_card_path": request["route_card_path"],
        "ledger_path": request["ledger_path"],
        "input": input_value or {},
        "caller": {"role": "orchestrator", "mode": "assisted"},
        "request_id": f"{request['request_id']}:{command}:{operation}:{stage or 'none'}",
    }
    if stage:
        out["stage"] = stage
    return out


def run_core(request: dict[str, Any], command: str, operation: str, *, stage: str | None = None, input_value: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    req = script_request(request, command, operation, stage=stage, input_value=input_value)
    proc = subprocess.run(
        [str(SCRIPTS / command)],
        input=json.dumps(req),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(ROOT),
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise OrchestrateError(
            "runtime_error",
            "E_CORE_SCRIPT_RESPONSE_INVALID",
            f"{command} did not emit JSON",
            errors=[error("E_CORE_SCRIPT_RESPONSE_INVALID", f"{command} did not emit JSON")],
            result={"exit_code": proc.returncode, "stderr": proc.stderr},
        ) from exc
    if payload.get("schema_version") != "codex-bandit.script-response.v1":
        raise OrchestrateError(
            "runtime_error",
            "E_CORE_SCRIPT_RESPONSE_INVALID",
            f"{command} emitted an invalid script-response envelope",
            errors=[error("E_CORE_SCRIPT_RESPONSE_INVALID", f"{command} emitted an invalid script-response envelope")],
            result={"core_response": payload},
        )
    return proc.returncode, payload


def route_path(request: dict[str, Any]) -> Path:
    raw = Path(request["route_card_path"])
    if raw.is_absolute():
        return raw
    return Path(request["repo_root"]).expanduser().resolve() / raw


def ledger_path(request: dict[str, Any]) -> Path:
    raw = Path(request["ledger_path"])
    if raw.is_absolute():
        return raw
    return Path(request["repo_root"]).expanduser().resolve() / raw


def load_route(request: dict[str, Any]) -> dict[str, Any]:
    try:
        route = json.loads(route_path(request).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OrchestrateError(
            "invalid_input",
            "E_ROUTE_CARD_MISSING",
            "route card does not exist",
            errors=[error("E_ROUTE_CARD_MISSING", "route card does not exist", field_path="/route_card_path")],
        ) from exc
    except json.JSONDecodeError as exc:
        raise OrchestrateError(
            "invalid_input",
            "E_ROUTE_CARD_INVALID_JSON",
            "route card is not valid JSON",
            errors=[error("E_ROUTE_CARD_INVALID_JSON", "route card is not valid JSON", field_path="/route_card_path")],
        ) from exc
    if not isinstance(route, dict):
        raise OrchestrateError(
            "invalid_input",
            "E_ROUTE_CARD_INVALID",
            "route card must be a JSON object",
            errors=[error("E_ROUTE_CARD_INVALID", "route card must be a JSON object", field_path="/route_card_path")],
        )
    return route


def read_events(request: dict[str, Any]) -> list[dict[str, Any]]:
    path = ledger_path(request)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            return events
        if isinstance(value, dict):
            events.append(value)
    return events


def route_review_package_digest(route: dict[str, Any]) -> str | None:
    review_package = route.get("evidence", {}).get("review_package")
    digest = review_package.get("digest") if isinstance(review_package, dict) else None
    return digest if isinstance(digest, str) and digest else None


def adversarial_digest_blocker(stage: str = "adversarial") -> dict[str, Any]:
    return blocker(
        ADVERSARIAL_DIGEST_BLOCKER,
        "Adversarial review requires an active route-card evidence.review_package.digest.",
        stage=stage,
        owner_role="orchestrator",
    )


def validate_route_or_block(request: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    route = load_route(request)
    events = read_events(request)
    exit_code, payload = run_core(request, "route-card", "status", input_value={"route_card": route, "evidence_events": events})
    if exit_code != 0 or not payload.get("ok"):
        raise OrchestrateError(
            "invalid_input" if payload.get("status") == "invalid_input" else "blocked",
            "E_ROUTE_CARD_INVALID",
            "route card validation failed",
            blockers=payload.get("blockers", []),
            errors=payload.get("errors", []),
            warnings=payload.get("warnings", []),
            result={"core_response": payload},
        )
    return route, payload


def verify(request: dict[str, Any], stage: str) -> tuple[int, dict[str, Any]]:
    return run_core(request, "verify-stage", "verify", stage=stage)


def latest_stage_event(events: list[dict[str, Any]], stage: str, record_type: str | None = None) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.get("stage") == stage and (record_type is None or event.get("record_type") == record_type):
            return event
    return None


def validate_adversarial_pass_binding(request: dict[str, Any], route: dict[str, Any]) -> dict[str, Any] | None:
    route_digest = route_review_package_digest(route)
    if not route_digest:
        return adversarial_digest_blocker("adversarial")
    event = latest_stage_event(read_events(request), "adversarial", "verdict")
    verdict = event.get("verdict", {}) if isinstance(event, dict) else {}
    verdict_digest = verdict.get("review_package_digest")
    subject_digest = (verdict.get("subject") or {}).get("review_package_digest")
    if verdict_digest != route_digest or (subject_digest is not None and subject_digest != route_digest):
        return blocker(
            "E_REVIEW_PACKAGE_DIGEST_MISMATCH",
            "Adversarial verdict must bind to the active route-card review package digest.",
            stage="adversarial",
            owner_role="adversarial_reviewer",
            evidence_ids=[event.get("id")] if isinstance(event, dict) and event.get("id") else None,
        )
    return None


def update_route(request: dict[str, Any], updates: dict[str, Any], reason: str, *, stage: str | None = None) -> dict[str, Any]:
    route = load_route(request)
    _, payload = run_core(
        request,
        "route-card",
        "update",
        stage=stage or route.get("stage_plan", {}).get("current_stage"),
        input_value={
            "expected_previous_digest": digest_json(route),
            "set": updates,
            "reason": reason,
        },
    )
    if not payload.get("ok"):
        raise OrchestrateError(
            payload.get("status", "blocked"),
            "E_ROUTE_CARD_UPDATE_FAILED",
            "route-card update failed",
            blockers=payload.get("blockers", []),
            errors=payload.get("errors", []),
            warnings=payload.get("warnings", []),
            result={"core_response": payload},
        )
    return payload


def enabled_stages(route: dict[str, Any]) -> list[str]:
    enabled = route.get("stage_plan", {}).get("enabled_stages")
    if not isinstance(enabled, list):
        return []
    return [stage for stage in STAGE_ORDER if stage in enabled]


def next_enabled_stage(route: dict[str, Any], current: str) -> str | None:
    enabled = enabled_stages(route)
    try:
        idx = enabled.index(current)
    except ValueError:
        return None
    return enabled[idx + 1] if idx + 1 < len(enabled) else None


def dispatch_request_for(request: dict[str, Any], route: dict[str, Any], stage: str, reducer: dict[str, Any]) -> dict[str, Any]:
    role = STAGE_ROLE.get(stage, "orchestrator")
    role_contract = route.get("role_boundaries", {}).get("roles", {}).get(role)
    if not isinstance(role_contract, dict):
        raise OrchestrateError(
            "blocked",
            "E_ROLE_CONTRACT_MISSING",
            f"route card is missing role boundary for {role}",
            blockers=[blocker("E_ROLE_CONTRACT_MISSING", f"route card is missing role boundary for {role}", stage=stage, owner_role="orchestrator")],
        )
    commands: list[str] = []
    if stage in {"red", "green"}:
        commands = [stage]
    elif stage in {"adversarial", "prepare_pr"}:
        commands = ["review_package"]
    for command in commands:
        if command not in route.get("commands", {}):
            raise OrchestrateError(
                "blocked",
                "E_ROUTE_CARD_REQUIRED_FIELD_MISSING",
                f"route card is missing required command {command}",
                blockers=[blocker("E_ROUTE_CARD_REQUIRED_FIELD_MISSING", f"route card is missing required command {command}", stage=stage, owner_role="orchestrator")],
            )
    reports = route.get("evidence", {}).get("report_paths", {})
    review_package_digest = route_review_package_digest(route)
    if stage == "adversarial" and not review_package_digest:
        raise OrchestrateError(
            "blocked",
            ADVERSARIAL_DIGEST_BLOCKER,
            "adversarial dispatch requires a wired review package digest",
            blockers=[adversarial_digest_blocker(stage)],
        )
    dispatch_id = f"disp_{stage}_{hashlib.sha1((request['work_item_id'] + request['request_id'] + stage).encode()).hexdigest()[:10]}"
    return {
        "schema_version": "codex-bandit.stage-dispatch-request.v1",
        "dispatch_id": dispatch_id,
        "work_item_id": request["work_item_id"],
        "stage": stage,
        "target_role": role,
        "capability_mode": route.get("capability_mode", {}).get("mode"),
        "route_card": {"path": request["route_card_path"], "digest": digest_json(route)},
        "reducer_status": {stage: reducer.get("status")},
        "required_inputs": {
            "evidence_ids": reducer.get("evidence_ids") or reducer.get("active_evidence_ids", []),
            "report_paths": [value for value in reports.values() if isinstance(value, str)],
            "commands": commands,
        },
        "role_contract": {
            **role_contract,
            "must_return": ["role_output"],
        },
        "subject": {
            "base_ref": route.get("subject", {}).get("base_ref"),
            "head_ref": route.get("subject", {}).get("head_ref"),
            "expected_head_sha": route.get("subject", {}).get("expected_head_sha"),
            "review_package_digest": review_package_digest,
        },
    }


def build_review_package_and_wire_digest(request: dict[str, Any], *, update_stage: str | None = None) -> dict[str, Any]:
    _, build = run_core(request, "review-package", "build", stage="adversarial", input_value={})
    if not build.get("ok"):
        raise OrchestrateError(
            build.get("status", "blocked"),
            "E_REVIEW_PACKAGE_BUILD_FAILED",
            "review-package build failed",
            blockers=build.get("blockers", []),
            errors=build.get("errors", []),
            warnings=build.get("warnings", []),
            result={"core_response": build},
        )
    package = build.get("result", {}).get("review_package")
    digest = build.get("result", {}).get("digest")
    if not isinstance(package, dict) or not isinstance(digest, str):
        raise OrchestrateError(
            "runtime_error",
            "E_REVIEW_PACKAGE_RESPONSE_INVALID",
            "review-package build response did not include a package digest",
            errors=[error("E_REVIEW_PACKAGE_RESPONSE_INVALID", "review-package build response did not include a package digest")],
            result={"core_response": build},
        )
    pointer = {
        "digest": digest,
        "diff_digest": package.get("diff_digest"),
    }
    if package.get("path"):
        pointer["path"] = package["path"]
    route = load_route(request)
    update = update_route(
        request,
        {"evidence.review_package": pointer},
        "wire review package digest before adversarial",
        stage=update_stage or route.get("stage_plan", {}).get("current_stage"),
    )
    return {"review_package": package, "route_update": update}


def handle_create(request: dict[str, Any]) -> dict[str, Any]:
    route = request["input"].get("route_card")
    if not isinstance(route, dict):
        raise OrchestrateError(
            "invalid_input",
            "E_ROUTE_CARD_REQUIRED",
            "input.route_card is required",
            errors=[error("E_ROUTE_CARD_REQUIRED", "input.route_card is required", field_path="/input/route_card")],
        )
    _, payload = run_core(request, "route-card", "create", input_value={"route_card": route})
    if not payload.get("ok"):
        return response(
            request,
            ok=False,
            status=payload.get("status", "invalid_input"),
            stage=route.get("stage_plan", {}).get("current_stage"),
            next_action="fix_route_card",
            blockers=payload.get("blockers", []),
            errors=payload.get("errors", []),
            warnings=payload.get("warnings", []),
            result={"core_response": payload},
        )
    ledger_path(request).parent.mkdir(parents=True, exist_ok=True)
    ledger_path(request).touch(exist_ok=True)
    return response(request, ok=True, status="pass", stage=route.get("stage_plan", {}).get("current_stage"), next_action="status", result={"core_response": payload})


def handle_status(request: dict[str, Any]) -> dict[str, Any]:
    route, route_status = validate_route_or_block(request)
    stage = route.get("stage_plan", {}).get("current_stage")
    _, stage_status = verify(request, stage)
    return response(
        request,
        ok=True,
        status="pass",
        stage=stage,
        next_action="next",
        warnings=stage_status.get("warnings", []),
        result={"route_card": route_status.get("result", {}), "stage_status": stage_status},
    )


def blocked_or_dispatch(request: dict[str, Any], route: dict[str, Any], stage: str, stage_status: dict[str, Any]) -> dict[str, Any]:
    status = stage_status.get("status", "blocked")
    response_status = "stale" if status == "stale" else "blocked"
    if stage == "hitl_merge_checkpoint":
        return response(
            request,
            ok=False,
            status=response_status,
            stage=stage,
            next_action="await_human_merge_approval",
            blockers=stage_status.get("blockers", []),
            warnings=stage_status.get("warnings", []),
            result={"stage_status": stage_status},
        )
    if stage == "land_deploy":
        return response(
            request,
            ok=False,
            status=response_status,
            stage=stage,
            next_action="ticket_07_delivery_operation_required",
            blockers=stage_status.get("blockers", []),
            warnings=stage_status.get("warnings", []),
            result={"stage_status": stage_status},
        )
    dispatch = dispatch_request_for(request, route, stage, stage_status)
    return response(
        request,
        ok=False,
        status=response_status,
        stage=stage,
        next_action="dispatch_role",
        blockers=stage_status.get("blockers", []),
        warnings=stage_status.get("warnings", []),
        result={"stage_status": stage_status, "dispatch_request": dispatch},
    )


def handle_next(request: dict[str, Any]) -> dict[str, Any]:
    route, _ = validate_route_or_block(request)
    stage = route.get("stage_plan", {}).get("current_stage")
    if not isinstance(stage, str):
        raise OrchestrateError(
            "invalid_input",
            "E_ROUTE_CARD_STAGE_MISSING",
            "route card missing stage_plan.current_stage",
            errors=[error("E_ROUTE_CARD_STAGE_MISSING", "route card missing stage_plan.current_stage", field_path="/stage_plan/current_stage")],
        )
    if stage == "plan":
        nxt = next_enabled_stage(route, stage)
        if not nxt:
            raise OrchestrateError(
                "blocked",
                "E_NEXT_STAGE_MISSING",
                "plan has no next enabled stage",
                blockers=[blocker("E_NEXT_STAGE_MISSING", "plan has no next enabled stage", stage=stage)],
            )
        update = update_route(request, {"stage_plan.current_stage": nxt, "stage_plan.lifecycle_state": "active"}, "route-card validated; start RED", stage=stage)
        route = load_route(request)
        _, red_status = verify(request, nxt)
        dispatch = dispatch_request_for(request, route, nxt, red_status)
        return response(request, ok=True, status="pass", stage=nxt, next_action="dispatch_role", result={"route_update": update, "dispatch_request": dispatch})

    extra: dict[str, Any] = {}
    if stage == "adversarial" and not route_review_package_digest(route):
        extra["review_package_wire_up"] = build_review_package_and_wire_digest(request, update_stage=stage)
        route = load_route(request)

    _, stage_status = verify(request, stage)
    warnings = stage_status.get("warnings", [])
    warning_codes = {item.get("code") for item in warnings}
    if stage == "hitl_merge_checkpoint" and stage_status.get("status") == "pass" and HITL_REMOTE_HEAD_WARNING in warning_codes:
        return response(
            request,
            ok=False,
            status="blocked",
            stage=stage,
            next_action="ticket_07_remote_head_check_required",
            blockers=[
                blocker(
                    "E_OPERATION_TIME_REMOTE_HEAD_REQUIRED",
                    "HITL ledger consistency passed, but operation-time remote PR head has not been checked; do not advance to land_deploy yet.",
                    stage=stage,
                    owner_role="land_deploy",
                    requires_human=True,
                )
            ],
            warnings=warnings,
            result={"stage_status": stage_status, "merge_ready": False},
        )
    if stage_status.get("status") == "deferred":
        update = update_route(request, {"stage_plan.current_stage": "closeout", "stage_plan.lifecycle_state": "active"}, "delivery deferred; route to closeout", stage=stage)
        return response(request, ok=True, status="pass", stage="closeout", next_action="dispatch_role", result={"stage_status": stage_status, "route_update": update})
    if not stage_status.get("ok"):
        return blocked_or_dispatch(request, route, stage, stage_status)
    if stage == "adversarial":
        digest_blocker = validate_adversarial_pass_binding(request, route)
        if digest_blocker:
            return response(
                request,
                ok=False,
                status="blocked",
                stage=stage,
                next_action="dispatch_role",
                blockers=[digest_blocker],
                warnings=warnings,
                result={**extra, "stage_status": stage_status, "merge_ready": False},
            )

    nxt = next_enabled_stage(route, stage)
    if not nxt:
        update = update_route(request, {"stage_plan.lifecycle_state": "complete"}, "workflow complete", stage=stage)
        return response(request, ok=True, status="pass", stage=stage, next_action="complete", result={"stage_status": stage_status, "route_update": update})

    extra = {**extra, "stage_status": stage_status}
    if stage == "green" and nxt == "adversarial":
        extra["review_package_wire_up"] = build_review_package_and_wire_digest(request, update_stage=stage)
        route = load_route(request)

    update = update_route(request, {"stage_plan.current_stage": nxt, "stage_plan.lifecycle_state": "active"}, f"advance {stage} to {nxt}", stage=stage)
    route = load_route(request)
    _, next_status = verify(request, nxt)
    extra["route_update"] = update
    extra["next_stage_status"] = next_status
    if next_status.get("ok"):
        return response(request, ok=True, status="pass", stage=nxt, next_action="next", warnings=next_status.get("warnings", []), result=extra)
    return response(
        request,
        ok=True,
        status="pass",
        stage=nxt,
        next_action="dispatch_role" if nxt != "hitl_merge_checkpoint" else "await_human_merge_approval",
        warnings=next_status.get("warnings", []),
        result={**extra, "dispatch_request": None if nxt == "hitl_merge_checkpoint" else dispatch_request_for(request, route, nxt, next_status)},
    )


def event_attempt_number(event: dict[str, Any], stage: str) -> int:
    raw = str(event.get("stage_attempt_id", ""))
    prefix = f"{event.get('work_item_id')}:{stage}:attempt-"
    if not raw.startswith(prefix):
        return 0
    try:
        return int(raw.rsplit("-", 1)[1])
    except ValueError:
        return 0


def next_attempt_number(events: list[dict[str, Any]], work_item_id: str, stage: str) -> int:
    highest = 0
    for event in events:
        if event.get("work_item_id") == work_item_id and event.get("stage") == stage:
            highest = max(highest, event_attempt_number(event, stage))
    return highest + 1


def stage_attempt_id(route: dict[str, Any], stage: str, events: list[dict[str, Any]]) -> str:
    work_item_id = route["work_item_id"]
    return f"{work_item_id}:{stage}:attempt-{next_attempt_number(events, work_item_id, stage)}"


def repair_budget_blocker(route: dict[str, Any], target_stage: str, next_attempt: int) -> dict[str, Any] | None:
    budget = route.get("stage_plan", {}).get("repair_loop_budget", {})
    used_after = max(0, next_attempt - 1)
    max_total = budget.get("max_total")
    per_stage = (budget.get("per_stage") or {}).get(target_stage)
    if isinstance(max_total, int) and used_after > max_total:
        return blocker(
            "E_REPAIR_BUDGET_EXHAUSTED",
            "Repair budget is exhausted for this work item.",
            stage=target_stage,
            owner_role="human",
            requires_human=True,
        )
    if isinstance(per_stage, int) and used_after > per_stage:
        return blocker(
            "E_REPAIR_BUDGET_EXHAUSTED",
            f"Repair budget is exhausted for {target_stage}.",
            stage=target_stage,
            owner_role="human",
            requires_human=True,
        )
    return None


def digest_file(path: Path) -> str:
    if path.exists() and path.is_file():
        return digest_bytes(path.read_bytes())
    return "sha256:" + hashlib.sha256(str(path).encode()).hexdigest()


def event_from_proposal(request: dict[str, Any], route: dict[str, Any], role_output: dict[str, Any], proposal: dict[str, Any], index: int, events: list[dict[str, Any]]) -> dict[str, Any]:
    stage = role_output["stage"]
    record_type = proposal.get("record_type")
    actor = proposal.get("actor") or role_output.get("actor") or {"role": STAGE_ROLE.get(stage), "mode": "assisted"}
    seed = json.dumps([request["request_id"], role_output.get("dispatch_id"), stage, index, proposal], sort_keys=True)
    event: dict[str, Any] = {
        "schema_version": EVIDENCE,
        "id": proposal.get("id") or f"ev_{stage}_{hashlib.sha1(seed.encode()).hexdigest()[:12]}",
        "work_item_id": request["work_item_id"],
        "stage_attempt_id": proposal.get("stage_attempt_id") or stage_attempt_id(route, stage, events),
        "record_type": record_type,
        "stage": stage,
        "actor": actor,
        "recorded_by": {"role": "orchestrator", "mode": "assisted"},
        "identity_strength": "declared",
        "claim": proposal.get("claim") or f"{stage}_{record_type}",
        "subject_scope": "audit",
        "status": proposal.get("status") or "pass",
        "tool_version": TOOL_VERSION,
        "created_at": proposal.get("created_at") or "2026-07-09T12:00:00Z",
    }
    if record_type in {"command", "verdict", "approval"}:
        event["subject_scope"] = "product"
        subject = {
            "base_ref": route.get("subject", {}).get("base_ref"),
            "head_ref": route.get("subject", {}).get("head_ref"),
            "head_sha": route.get("subject", {}).get("expected_head_sha"),
        }
        review_package = route.get("evidence", {}).get("review_package")
        if isinstance(review_package, dict) and review_package.get("digest"):
            subject["review_package_digest"] = review_package["digest"]
        event["subject"] = subject
    if record_type == "command":
        command = copy.deepcopy(proposal.get("command") or {})
        name = command.get("name") or stage
        spec = route.get("commands", {}).get(name, {})
        command.setdefault("name", name)
        command.setdefault("argv", spec.get("argv", []))
        command.setdefault("cwd", spec.get("cwd", "."))
        command.setdefault("exit_code", 0)
        event["command"] = command
        artifact_path = proposal.get("artifact_path") or spec.get("report_path")
        if isinstance(artifact_path, str):
            path = Path(artifact_path)
            if not path.is_absolute():
                path = Path(request["repo_root"]).expanduser().resolve() / path
            event["artifact"] = {"path": artifact_path, "digest": digest_file(path), "media_type": "text/markdown"}
        if isinstance(proposal.get("files_changed"), list):
            event["files_changed"] = proposal["files_changed"]
        event["completed_at"] = proposal.get("completed_at") or event["created_at"]
    elif record_type == "verdict":
        verdict = copy.deepcopy(proposal.get("verdict") or {})
        digest = route_review_package_digest(route)
        verdict.setdefault("schema_version", "codex-bandit.verdict.v1")
        verdict.setdefault("verdict", "approve")
        verdict.setdefault("rubric_ids", ["S4_REVIEW", "R6_EVIDENCE_BINDING"])
        verdict.setdefault("reviewed_evidence_ids", [])
        if digest:
            verdict.setdefault("review_package_digest", digest)
        verdict.setdefault("subject", event["subject"])
        verdict.setdefault("findings", [])
        verdict.setdefault("test_surface_findings", [])
        verdict.setdefault("cannot_judge_reason", None)
        event["verdict"] = verdict
        event["completed_at"] = proposal.get("completed_at") or event["created_at"]
    elif record_type == "blocker":
        event["status"] = "blocked"
        event["blocker"] = copy.deepcopy(proposal.get("blocker") or blocker("E_ROLE_BLOCKED", role_output.get("summary") or "Role blocked.", stage=stage, owner_role=actor.get("role", "orchestrator")))
    elif record_type == "note":
        event["note"] = copy.deepcopy(proposal.get("note") or {"summary": role_output.get("summary") or "role note", "visibility": "internal"})
    return event


def blocker_event_from_role_output(request: dict[str, Any], route: dict[str, Any], role_output: dict[str, Any], item: dict[str, Any], index: int, events: list[dict[str, Any]]) -> dict[str, Any]:
    stage = role_output.get("stage") or route.get("stage_plan", {}).get("current_stage")
    seed = json.dumps([request["request_id"], role_output.get("dispatch_id"), stage, index, item], sort_keys=True)
    return {
        "schema_version": EVIDENCE,
        "id": f"ev_{stage}_blocker_{hashlib.sha1(seed.encode()).hexdigest()[:12]}",
        "work_item_id": request["work_item_id"],
        "stage_attempt_id": stage_attempt_id(route, stage, events),
        "record_type": "blocker",
        "stage": stage,
        "actor": role_output.get("actor") or {"role": STAGE_ROLE.get(stage), "mode": "assisted"},
        "recorded_by": {"role": "orchestrator", "mode": "assisted"},
        "identity_strength": "declared",
        "claim": "role_reported_blocker",
        "subject_scope": "audit",
        "status": "blocked",
        "blocker": item,
        "tool_version": TOOL_VERSION,
        "created_at": "2026-07-09T12:00:00Z",
    }


def append_event(request: dict[str, Any], stage: str, event: dict[str, Any]) -> dict[str, Any]:
    _, payload = run_core(request, "evidence-ledger", "append", stage=stage, input_value={"event": event})
    if not payload.get("ok"):
        raise OrchestrateError(
            payload.get("status", "blocked"),
            "E_EVIDENCE_APPEND_FAILED",
            "evidence append failed",
            blockers=payload.get("blockers", []),
            errors=payload.get("errors", []),
            warnings=payload.get("warnings", []),
            result={"core_response": payload, "event": event},
        )
    return payload


def validate_adversarial_role_output(route: dict[str, Any], role_output: dict[str, Any]) -> dict[str, Any] | None:
    if role_output.get("stage") != "adversarial":
        return None
    route_digest = route_review_package_digest(route)
    if not route_digest:
        return adversarial_digest_blocker("adversarial")
    if role_output.get("outcome") != "success":
        return None
    verdict_seen = False
    for proposal in role_output.get("proposed_evidence") or []:
        if proposal.get("record_type") != "verdict":
            continue
        verdict_seen = True
        verdict = proposal.get("verdict")
        verdict_digest = verdict.get("review_package_digest") if isinstance(verdict, dict) else None
        subject_digest = (verdict.get("subject") or {}).get("review_package_digest") if isinstance(verdict, dict) else None
        if verdict_digest != route_digest or (subject_digest is not None and subject_digest != route_digest):
            return blocker(
                "E_REVIEW_PACKAGE_DIGEST_MISMATCH" if verdict_digest else ADVERSARIAL_DIGEST_BLOCKER,
                "Adversarial role output must include the active route-card review package digest.",
                stage="adversarial",
                owner_role="adversarial_reviewer",
            )
    if not verdict_seen:
        return blocker(
            "E_ADVERSARIAL_VERDICT_REQUIRED",
            "Adversarial success must propose verdict evidence.",
            stage="adversarial",
            owner_role="adversarial_reviewer",
        )
    return None


def handle_apply_role_output(request: dict[str, Any]) -> dict[str, Any]:
    route, _ = validate_route_or_block(request)
    role_output = request["input"].get("role_output")
    if not isinstance(role_output, dict):
        raise OrchestrateError(
            "invalid_input",
            "E_ROLE_OUTPUT_REQUIRED",
            "input.role_output is required",
            errors=[error("E_ROLE_OUTPUT_REQUIRED", "input.role_output is required", field_path="/input/role_output")],
        )
    if role_output.get("schema_version") != ROLE_OUTPUT:
        raise OrchestrateError(
            "invalid_input",
            "E_ROLE_OUTPUT_SCHEMA_INVALID",
            "role output schema_version is invalid",
            errors=[error("E_ROLE_OUTPUT_SCHEMA_INVALID", "role output schema_version is invalid", field_path="/input/role_output/schema_version")],
        )
    dispatch = request["input"].get("dispatch_request")
    if not isinstance(dispatch, dict):
        stage = route.get("stage_plan", {}).get("current_stage")
        _, stage_status = verify(request, stage)
        dispatch = dispatch_request_for(request, route, stage, stage_status)
    validation = validate_role_output(dispatch, role_output)
    if not validation.get("valid"):
        b = blocker(validation["code"], validation["code"], stage=role_output.get("stage"), owner_role="orchestrator")
        return response(request, ok=False, status="blocked", stage=role_output.get("stage"), next_action="fix_role_output", blockers=[b], result={"validation": validation})
    if role_output.get("route_card_patch"):
        b = blocker("E_ROUTE_PATCH_REQUIRES_ORCHESTRATOR_REVIEW", "Role output may propose a route-card patch, but only orchestrator policy may apply it.", stage=role_output.get("stage"), owner_role="orchestrator")
        return response(request, ok=False, status="blocked", stage=role_output.get("stage"), next_action="review_route_card_patch", blockers=[b])
    digest_problem = validate_adversarial_role_output(route, role_output)
    if digest_problem:
        return response(request, ok=False, status="blocked", stage=role_output.get("stage"), next_action="build_review_package", blockers=[digest_problem])

    appended: list[dict[str, Any]] = []
    stage = role_output.get("stage") or dispatch.get("stage")
    events = read_events(request)
    for index, proposal in enumerate(role_output.get("proposed_evidence") or []):
        proposal_stage = role_output.get("stage") or proposal.get("stage")
        proposal_next_attempt: int | None = None
        if proposal.get("record_type") == "command" and proposal_stage in {"red", "green"}:
            proposal_next_attempt = next_attempt_number(events, request["work_item_id"], proposal_stage)
            budget_problem = repair_budget_blocker(route, proposal_stage, proposal_next_attempt)
            if budget_problem:
                return response(request, ok=False, status="blocked", stage=proposal_stage, next_action="ask_human", blockers=[budget_problem], result={"appended": appended})
        event = event_from_proposal(request, route, role_output, proposal, index, events)
        appended.append(append_event(request, event["stage"], event))
        events.append(event)
        if proposal_next_attempt and proposal_next_attempt > 1:
            used_after = max(route.get("stage_plan", {}).get("repair_loop_budget", {}).get("used_total", 0), proposal_next_attempt - 1)
            appended.append(update_route(request, {"stage_plan.repair_loop_budget.used_total": used_after}, f"record {proposal_stage} repair attempt {proposal_next_attempt}", stage=proposal_stage))
            route = load_route(request)
    for index, item in enumerate(role_output.get("blockers") or []):
        if role_output.get("outcome") in {"blocked", "cannot_judge", "manual_continuation"}:
            event = blocker_event_from_role_output(request, route, role_output, item, index, events)
            appended.append(append_event(request, item.get("stage") or stage, event))
            events.append(event)

    if role_output.get("outcome") in {"reroute", "repair_needed"}:
        reroute = role_output.get("reroute") or {}
        target = reroute.get("target_stage")
        if target not in enabled_stages(route):
            b = blocker("E_REROUTE_TARGET_INVALID", "reroute target is not enabled in the route card", stage=stage, owner_role="orchestrator")
            return response(request, ok=False, status="blocked", stage=stage, next_action="fix_role_output", blockers=[b], result={"appended": appended})
        next_attempt = next_attempt_number(events, request["work_item_id"], target)
        budget_problem = repair_budget_blocker(route, target, next_attempt)
        if budget_problem:
            return response(request, ok=False, status="blocked", stage=stage, next_action="ask_human", blockers=[budget_problem], result={"appended": appended})
        used_after = max(route.get("stage_plan", {}).get("repair_loop_budget", {}).get("used_total", 0), next_attempt - 1)
        update = update_route(
            request,
            {
                "stage_plan.current_stage": target,
                "stage_plan.lifecycle_state": "repairing" if role_output.get("outcome") == "repair_needed" else "active",
                "stage_plan.repair_loop_budget.used_total": used_after,
            },
            reroute.get("reason") or role_output.get("summary") or "role requested reroute",
            stage=stage,
        )
        return response(request, ok=True, status="pass", stage=target, next_action="dispatch_role", result={"appended": appended, "route_update": update})

    _, reduced = verify(request, stage)
    next_action = "next" if reduced.get("ok") else ("manual_continuation" if role_output.get("outcome") == "manual_continuation" else "dispatch_role")
    return response(
        request,
        ok=role_output.get("outcome") == "success",
        status="pass" if role_output.get("outcome") == "success" else "blocked",
        stage=stage,
        next_action=next_action,
        blockers=reduced.get("blockers", []),
        warnings=reduced.get("warnings", []),
        result={"appended": appended, "stage_status": reduced},
    )


def transition_event(request: dict[str, Any], route: dict[str, Any], kind: str) -> dict[str, Any]:
    stage = route.get("stage_plan", {}).get("current_stage", "plan")
    actor = {"role": "human", "mode": "manual", "id": request["input"].get("approved_by") or "human"}
    event_id = request["input"].get("id") or f"ev_{kind}_{hashlib.sha1((request['request_id'] + kind).encode()).hexdigest()[:12]}"
    to_stage = request["input"].get("to_stage") or stage
    status = "deferred" if kind == "defer_delivery" else "pass"
    event = {
        "schema_version": EVIDENCE,
        "id": event_id,
        "work_item_id": request["work_item_id"],
        "stage_attempt_id": request["input"].get("stage_attempt_id") or stage_attempt_id(route, stage, read_events(request)),
        "record_type": "transition",
        "stage": stage,
        "actor": actor,
        "recorded_by": {"role": "orchestrator", "mode": "assisted"},
        "identity_strength": "human_verified",
        "claim": kind,
        "subject_scope": "audit",
        "status": status,
        "transition": {
            "from_stage": stage,
            "to_stage": to_stage,
            "reason": request["input"].get("reason") or kind,
            "previous_route_card_digest": digest_json(route),
            "new_route_card_digest": digest_json(route),
        },
        "tool_version": TOOL_VERSION,
        "created_at": request["input"].get("created_at") or "2026-07-09T12:00:00Z",
    }
    if kind == "manual_patch":
        event["transition"]["authorized_paths"] = request["input"].get("paths")
        event["transition"]["expires_after_use"] = True
    return event


def handle_record_escape(request: dict[str, Any]) -> dict[str, Any]:
    route, _ = validate_route_or_block(request)
    kind = request["input"].get("kind")
    if kind not in {"manual_patch", "exit_orchestration", "defer_delivery"}:
        raise OrchestrateError(
            "invalid_input",
            "E_ESCAPE_KIND_INVALID",
            "input.kind must be manual_patch, exit_orchestration, or defer_delivery",
            errors=[error("E_ESCAPE_KIND_INVALID", "input.kind must be manual_patch, exit_orchestration, or defer_delivery", field_path="/input/kind")],
        )
    if kind == "manual_patch":
        paths = request["input"].get("paths")
        if not isinstance(paths, list) or not all(isinstance(item, str) and item for item in paths):
            raise OrchestrateError(
                "invalid_input",
                "E_MANUAL_PATCH_SCOPE_REQUIRED",
                "manual_patch requires input.paths to scope the authorization",
                errors=[error("E_MANUAL_PATCH_SCOPE_REQUIRED", "manual_patch requires input.paths to scope the authorization", field_path="/input/paths")],
            )
        request["input"]["paths"] = normalize_edit_paths(request, paths)[0]
    event = transition_event(request, route, kind)
    appended = append_event(request, event["stage"], event)
    updates: dict[str, Any] = {}
    if kind == "exit_orchestration":
        updates = {"stage_plan.lifecycle_state": "abandoned"}
    route_update = update_route(request, updates, kind, stage=event["stage"]) if updates else None
    return response(request, ok=True, status="pass", stage=event["stage"], next_action="manual_continuation" if kind != "defer_delivery" else "next", result={"appended": appended, "route_update": route_update})


def normalize_edit_paths(request: dict[str, Any], paths: list[str]) -> tuple[list[str], list[str]]:
    repo_root = Path(request["repo_root"]).expanduser().resolve()
    normalized: list[str] = []
    guarded: list[str] = []
    for raw in paths:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        resolved = candidate.expanduser().resolve()
        try:
            relative = resolved.relative_to(repo_root)
        except ValueError as exc:
            raise OrchestrateError(
                "blocked",
                "E_EDIT_PATH_OUTSIDE_REPO",
                "edit path must stay inside repo root",
                blockers=[blocker("E_EDIT_PATH_OUTSIDE_REPO", "edit path must stay inside repo root", stage=None, owner_role="orchestrator")],
            ) from exc
        rel = relative.as_posix()
        normalized.append(rel)
        if rel == "src" or rel.startswith("src/") or rel == "tests" or rel.startswith("tests/"):
            guarded.append(rel)
    return normalized, guarded


def manual_patch_covers(event: dict[str, Any], guarded_paths: list[str]) -> bool:
    transition = event.get("transition") or {}
    authorized = transition.get("authorized_paths")
    if not isinstance(authorized, list):
        return False
    normalized = {Path(path).as_posix().lstrip("./") for path in authorized if isinstance(path, str)}
    return all(path in normalized for path in guarded_paths)


def has_escape_authorization(events: list[dict[str, Any]], guarded_paths: list[str]) -> dict[str, Any] | None:
    consumed = {
        event.get("transition", {}).get("consumed_authorization_id")
        for event in events
        if event.get("record_type") == "transition" and event.get("claim") == MANUAL_PATCH_CONSUMED_CLAIM
    }
    for event in events:
        if event.get("record_type") != "transition":
            continue
        if event.get("claim") == "exit_orchestration":
            return event
        if event.get("claim") == "manual_patch" and event.get("id") not in consumed and manual_patch_covers(event, guarded_paths):
            return event
    return None


def manual_patch_consumed_event(request: dict[str, Any], route: dict[str, Any], authorization: dict[str, Any], guarded_paths: list[str]) -> dict[str, Any]:
    stage = route.get("stage_plan", {}).get("current_stage", "plan")
    seed = json.dumps([request["request_id"], authorization.get("id"), guarded_paths], sort_keys=True)
    return {
        "schema_version": EVIDENCE,
        "id": f"ev_manual_patch_consumed_{hashlib.sha1(seed.encode()).hexdigest()[:12]}",
        "work_item_id": request["work_item_id"],
        "stage_attempt_id": stage_attempt_id(route, stage, read_events(request)),
        "record_type": "transition",
        "stage": stage,
        "actor": {"role": "orchestrator", "mode": "assisted"},
        "recorded_by": {"role": "orchestrator", "mode": "assisted"},
        "identity_strength": "system",
        "claim": MANUAL_PATCH_CONSUMED_CLAIM,
        "subject_scope": "audit",
        "status": "pass",
        "transition": {
            "from_stage": stage,
            "to_stage": stage,
            "reason": "consume scoped manual_patch edit authorization",
            "previous_route_card_digest": digest_json(route),
            "new_route_card_digest": digest_json(route),
            "consumed_authorization_id": authorization.get("id"),
            "authorized_paths": guarded_paths,
        },
        "tool_version": TOOL_VERSION,
        "created_at": "2026-07-09T12:00:00Z",
    }


def handle_guard_edit(request: dict[str, Any]) -> dict[str, Any]:
    route, _ = validate_route_or_block(request)
    paths = request["input"].get("paths")
    if not isinstance(paths, list) or not all(isinstance(item, str) for item in paths):
        raise OrchestrateError(
            "invalid_input",
            "E_EDIT_PATHS_REQUIRED",
            "input.paths must be an array of repo-relative paths",
            errors=[error("E_EDIT_PATHS_REQUIRED", "input.paths must be an array of repo-relative paths", field_path="/input/paths")],
        )
    normalized, guarded = normalize_edit_paths(request, paths)
    events = read_events(request)
    authorization = has_escape_authorization(events, guarded) if guarded else None
    if guarded and not authorization:
        b = blocker(
            "E_ORCHESTRATOR_EDIT_REQUIRES_ESCAPE",
            "orchestrator must not edit product code/tests during active work unless manual_patch or exit_orchestration is recorded",
            stage=route.get("stage_plan", {}).get("current_stage"),
            owner_role="human",
            requires_human=True,
        )
        return response(request, ok=False, status="blocked", stage=route.get("stage_plan", {}).get("current_stage"), next_action="record_manual_patch_or_exit", blockers=[b])
    consumed = None
    if guarded and authorization and authorization.get("claim") == "manual_patch":
        consumed = append_event(request, route.get("stage_plan", {}).get("current_stage"), manual_patch_consumed_event(request, route, authorization, guarded))
    return response(
        request,
        ok=True,
        status="pass",
        stage=route.get("stage_plan", {}).get("current_stage"),
        next_action="continue",
        result={"paths": normalized, "guarded_paths": guarded, "authorization_consumed": consumed},
    )


def run(request: dict[str, Any]) -> dict[str, Any]:
    require_request(request)
    operation = request["operation"]
    if operation == "create":
        return handle_create(request)
    if operation == "status":
        return handle_status(request)
    if operation == "next":
        return handle_next(request)
    if operation == "apply-role-output":
        return handle_apply_role_output(request)
    if operation == "record-escape":
        return handle_record_escape(request)
    if operation == "guard-edit":
        return handle_guard_edit(request)
    raise OrchestrateError(
        "invalid_input",
        "E_OPERATION_UNSUPPORTED",
        f"unsupported orchestrate operation: {operation}",
        errors=[error("E_OPERATION_UNSUPPORTED", f"unsupported orchestrate operation: {operation}", field_path="/operation")],
    )


def main() -> int:
    request, parse_error = read_request()
    if parse_error:
        return emit(response(None, ok=False, status="invalid_input", errors=[error("E_SCHEMA_INVALID", parse_error)]))
    try:
        payload = run(request)
        try:
            dashboard_paths = refresh_for_work_item(Path(request["repo_root"]).expanduser().resolve(), request["work_item_id"])
            if dashboard_paths:
                payload.setdefault("result", {})["dashboard_paths"] = dashboard_paths
        except Exception as exc:
            payload.setdefault("warnings", []).append({"code": "W_DASHBOARD_REFRESH_FAILED", "message": str(exc)})
        return emit(payload)
    except OrchestrateError as exc:
        return emit(
            response(
                request,
                ok=False,
                status=exc.status,
                stage=request.get("input", {}).get("stage") if isinstance(request, dict) else None,
                blockers=exc.blockers,
                errors=exc.errors or ([error(exc.code, exc.message)] if exc.status in {"invalid_input", "runtime_error"} else []),
                warnings=exc.warnings,
                result=exc.result,
            )
        )
    except Exception as exc:
        return emit(response(request, ok=False, status="runtime_error", errors=[error("E_RUNTIME_ERROR", str(exc))]))


if __name__ == "__main__":
    raise SystemExit(main())
