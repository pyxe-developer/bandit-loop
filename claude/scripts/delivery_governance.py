#!/usr/bin/env python3
"""Operation-time delivery checks for Codex Bandit Ticket 07."""

from __future__ import annotations

import datetime as _dt
import json
import sys
from typing import Any

from bandit_runtime import (
    SCRIPT_RESPONSE,
    ScriptFailure,
    blocker,
    digest_json,
    error,
    exit_code_for,
    latest,
    latest_adversarial_approval,
    load_route_card_for_request,
    read_ledger,
    reduce_stage,
    response,
    safe_ledger_path,
    validate_hitl_approval,
    validate_request,
)


PASS_CI_STATES = {"pass", "passed", "success", "successful"}
FAIL_CI_STATES = {"fail", "failed", "failure", "error", "cancelled", "timed_out"}
PASS_REVIEW_STATES = {"approved", "pass", "passed"}
FAIL_REVIEW_STATES = {"changes_requested", "rejected", "dismissed", "failed"}
PASS_DEPLOY_STATES = {"pass", "passed", "success", "successful", "deployed"}
FAIL_DEPLOY_STATES = {"fail", "failed", "failure", "error", "cancelled"}
PASS_HEALTH_STATES = {"pass", "passed", "healthy", "success", "successful"}
FAIL_HEALTH_STATES = {"fail", "failed", "unhealthy", "error"}


def _parse_time(value: str | None) -> _dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _delivery_blocker(
    code: str,
    summary: str,
    *,
    stage: str = "land_deploy",
    owner_role: str = "land_deploy",
    remote_pr_number: int | None = None,
    head_sha: str | None = None,
    evidence_ids: list[str] | None = None,
    retryable: bool = True,
    requires_human: bool = False,
    untrusted_remote_input: bool = False,
) -> dict[str, Any]:
    out = {
        "code": code,
        "delivery_state": "delivery_blocked",
        "stage": stage,
        "owner_role": owner_role,
        "summary": summary,
        "retryable": retryable,
        "requires_human": requires_human,
        "untrusted_remote_input": untrusted_remote_input,
    }
    if remote_pr_number is not None:
        out["remote_pr_number"] = remote_pr_number
    if head_sha:
        out["head_sha"] = head_sha
    if evidence_ids:
        out["evidence_ids"] = evidence_ids
    return out


def _blocked(
    code: str,
    summary: str,
    *,
    stage: str = "land_deploy",
    owner_role: str = "land_deploy",
    remote_pr_number: int | None = None,
    head_sha: str | None = None,
    evidence_ids: list[str] | None = None,
    retryable: bool = True,
    requires_human: bool = False,
    untrusted_remote_input: bool = False,
    untrusted_remote_inputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "status": "blocked",
        "delivery_state": "delivery_blocked",
        "merge_allowed": False,
        "deploy_allowed": False,
        "blockers": [
            _delivery_blocker(
                code,
                summary,
                stage=stage,
                owner_role=owner_role,
                remote_pr_number=remote_pr_number,
                head_sha=head_sha,
                evidence_ids=evidence_ids,
                retryable=retryable,
                requires_human=requires_human,
                untrusted_remote_input=untrusted_remote_input,
            )
        ],
        "untrusted_remote_inputs": untrusted_remote_inputs or [],
    }


def _remote_comments(remote: dict[str, Any]) -> list[dict[str, Any]]:
    comments = remote.get("comments") or []
    if not isinstance(comments, list):
        return []
    out = []
    for item in comments:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "source": item.get("source") or "remote_comment",
                "author": item.get("author"),
                "body": item.get("body"),
                "treated_as_untrusted": True,
                "instruction_effect": "none",
            }
        )
    return out


def build_pr_package(route: dict[str, Any], local: dict[str, Any] | None = None) -> dict[str, Any]:
    local = local or {}
    subject = route.get("subject", {})
    evidence = route.get("evidence", {})
    review_package = evidence.get("review_package") if isinstance(evidence.get("review_package"), dict) else {}
    base_ref = subject.get("base_ref")
    head_ref = subject.get("head_ref")
    expected_head = subject.get("expected_head_sha")
    compare_url = local.get("compare_url") or f"{base_ref}...{head_ref}"
    branch_status = {
        "head_ref": head_ref,
        "expected_head_sha": expected_head,
        "local_branch": local.get("local_branch") or head_ref,
        "remote_branch_exists": bool(local.get("remote_branch_exists", False)),
        "branch_push_authorized": bool(route.get("delivery_authority", {}).get("allow_branch_push")),
    }
    local_gates = local.get("local_gates") or {
        "status": "pass",
        "source": "latest reducer status and required local commands",
    }
    return {
        "delivery_state": "pr_prepared",
        "route_card_digest": digest_json(route),
        "branch_status": branch_status,
        "local_gates": local_gates,
        "review_package": {
            "digest": review_package.get("digest"),
            "diff_digest": review_package.get("diff_digest"),
            "path": review_package.get("path"),
        },
        "pr_body": local.get("pr_body")
        or "\n".join(
            [
                f"Work item: {route.get('work_item_id')}",
                f"Base: {base_ref}",
                f"Head: {head_ref}",
                f"Expected head SHA: {expected_head}",
                f"Review package: {review_package.get('digest')}",
            ]
        ),
        "compare_guidance": {
            "base_ref": base_ref,
            "head_ref": head_ref,
            "url_or_range": compare_url,
        },
        "pr": {
            "number": local.get("pr_number"),
            "url": local.get("pr_url"),
            "created": bool(local.get("pr_created", False)),
        },
    }


def prepare_pr_result(route: dict[str, Any], local: dict[str, Any] | None = None) -> dict[str, Any]:
    local = local or {}
    if local.get("defer_reason"):
        return {
            "status": "deferred",
            "delivery_state": "delivery_deferred",
            "terminal": True,
            "reason": local["defer_reason"],
            "merge_allowed": False,
            "deploy_allowed": False,
            "blockers": [],
        }
    return {
        "status": "pass",
        "delivery_state": "pr_prepared",
        "terminal": False,
        "pr_package": build_pr_package(route, local),
        "blockers": [],
    }


def _approval_expired(approval_event: dict[str, Any], now: str | None) -> bool:
    approval = approval_event.get("approval", {})
    expires_at = _parse_time(approval.get("expires_at"))
    current = _parse_time(now)
    if expires_at is None:
        return True
    if current is None:
        current = _dt.datetime.now(_dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=_dt.timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=_dt.timezone.utc)
    return current >= expires_at


def _state(value: Any) -> str:
    if not isinstance(value, str):
        return "unknown"
    return value.strip().lower()


def evaluate_land_deploy(route: dict[str, Any], events: list[dict[str, Any]], remote: dict[str, Any], *, now: str | None = None) -> dict[str, Any]:
    if remote.get("delivery_deferred"):
        return {
            "status": "deferred",
            "delivery_state": "delivery_deferred",
            "terminal": True,
            "merge_allowed": False,
            "deploy_allowed": False,
            "reason": remote.get("defer_reason") or "Delivery deferred.",
            "blockers": [],
            "untrusted_remote_inputs": _remote_comments(remote),
        }

    reducer = reduce_stage(route, events, "land_deploy")
    if reducer.get("status") == "blocked":
        first = (reducer.get("blockers") or [{}])[0]
        return _blocked(
            first.get("code", "E_DELIVERY_PREREQUISITE_BLOCKED"),
            first.get("message", "Reducer prerequisites for delivery are not active."),
            owner_role=first.get("owner_role") or "land_deploy",
            requires_human=bool(first.get("requires_human")),
            evidence_ids=first.get("evidence_ids") or [],
        )

    active_adv = latest_adversarial_approval(route, events)
    approval_event = latest(events, stage="hitl_merge_checkpoint", record_types={"approval"})
    if not active_adv:
        return _blocked("E_ADVERSARIAL_APPROVAL_REQUIRED", "Merge requires active adversarial approval.", owner_role="adversarial_reviewer")
    if not approval_event:
        return _blocked("E_HITL_APPROVAL_REQUIRED", "Merge requires HITL approval bound to the exact PR and head SHA.", owner_role="human", requires_human=True)

    approval = approval_event.get("approval", {})
    remote_pr_number = remote.get("pr_number")
    remote_head = remote.get("pr_head_sha")
    if remote_pr_number is None:
        return _blocked("E_OPERATION_TIME_REMOTE_HEAD_REQUIRED", "Current remote PR number is required at merge time.", requires_human=False, untrusted_remote_inputs=_remote_comments(remote))
    if not remote_head:
        return _blocked("E_OPERATION_TIME_REMOTE_HEAD_REQUIRED", "Current remote PR head SHA is required at merge time.", remote_pr_number=remote_pr_number, requires_human=False, untrusted_remote_inputs=_remote_comments(remote))
    if approval.get("pr_number") != remote_pr_number:
        return _blocked("E_HITL_APPROVAL_REQUIRED", "HITL approval PR number does not match the remote PR.", remote_pr_number=remote_pr_number, head_sha=remote_head, owner_role="human", requires_human=True, evidence_ids=[approval_event.get("id")])

    hitl = validate_hitl_approval(
        route,
        approval_event,
        last_active_adversarial_head=(active_adv.get("subject") or {}).get("head_sha"),
        remote_pr_head_sha=remote_head,
    )
    if not hitl.get("valid"):
        return _blocked(
            hitl.get("code", "E_HITL_APPROVAL_REQUIRED"),
            hitl.get("message", "HITL approval is not valid for this remote PR head."),
            remote_pr_number=remote_pr_number,
            head_sha=remote_head,
            owner_role="human",
            requires_human=True,
            evidence_ids=[approval_event.get("id")],
        )
    if _approval_expired(approval_event, now):
        return _blocked(
            "E_HITL_APPROVAL_EXPIRED",
            "HITL merge approval is missing an expiry or has expired.",
            remote_pr_number=remote_pr_number,
            head_sha=remote_head,
            owner_role="human",
            requires_human=True,
            evidence_ids=[approval_event.get("id")],
        )
    if not route.get("delivery_authority", {}).get("allow_merge"):
        return _blocked("E_MERGE_AUTHORITY_REQUIRED", "Route card does not grant merge authority.", remote_pr_number=remote_pr_number, head_sha=remote_head, owner_role="human", requires_human=True)

    ci_state = _state((remote.get("ci") or {}).get("status"))
    if ci_state in FAIL_CI_STATES:
        return _blocked("E_CI_FAILED", "Required CI check failed.", remote_pr_number=remote_pr_number, head_sha=remote_head, untrusted_remote_inputs=_remote_comments(remote))
    if ci_state not in PASS_CI_STATES:
        return _blocked("E_CI_UNKNOWN", "Required CI state is missing, pending, or unknown.", remote_pr_number=remote_pr_number, head_sha=remote_head, untrusted_remote_inputs=_remote_comments(remote))

    review_state = _state((remote.get("reviews") or {}).get("status"))
    if review_state in FAIL_REVIEW_STATES:
        return _blocked("E_REVIEW_STATE_BLOCKED", "Required remote review state is blocking merge.", remote_pr_number=remote_pr_number, head_sha=remote_head, untrusted_remote_inputs=_remote_comments(remote))
    if review_state not in PASS_REVIEW_STATES:
        return _blocked("E_REVIEW_STATE_UNKNOWN", "Required remote review state is missing or unknown.", remote_pr_number=remote_pr_number, head_sha=remote_head, untrusted_remote_inputs=_remote_comments(remote))

    deploy = remote.get("deploy") or {}
    deploy_required = bool(deploy.get("required", False))
    authority = route.get("delivery_authority", {})
    deploy_contract = authority.get("deploy_contract")
    comments = _remote_comments(remote)

    if deploy_required and not authority.get("allow_deploy"):
        return _blocked("E_DEPLOY_AUTHORITY_REQUIRED", "Route card does not grant deploy authority.", remote_pr_number=remote_pr_number, head_sha=remote_head, owner_role="human", requires_human=True)
    if deploy_required and not deploy_contract:
        return _blocked("E_DEPLOY_CONTRACT_MISSING", "Deploy was requested but the route card has no deploy contract.", remote_pr_number=remote_pr_number, head_sha=remote_head, requires_human=True)

    if not deploy_required:
        return {
            "status": "pass",
            "delivery_state": "merge_approved",
            "merge_allowed": True,
            "deploy_allowed": False,
            "blockers": [],
            "untrusted_remote_inputs": comments,
            "operation_checks": {
                "remote_head_checked": True,
                "approval_unexpired": True,
                "ci_status": ci_state,
                "review_status": review_state,
            },
        }

    deploy_state = _state(deploy.get("status"))
    if deploy_state in FAIL_DEPLOY_STATES:
        return _blocked("E_DEPLOY_FAILED", "Deploy operation failed.", remote_pr_number=remote_pr_number, head_sha=remote_head, evidence_ids=["ev_merge_001"], requires_human=True)
    if deploy_state not in PASS_DEPLOY_STATES:
        return _blocked("E_DEPLOY_UNKNOWN", "Deploy operation state is missing or unknown.", remote_pr_number=remote_pr_number, head_sha=remote_head, evidence_ids=["ev_merge_001"])

    health_state = _state((remote.get("health") or {}).get("status"))
    if health_state in FAIL_HEALTH_STATES:
        return _blocked("E_DEPLOY_HEALTH_FAILED", "Health check failed after deploy.", remote_pr_number=remote_pr_number, head_sha=remote_head, evidence_ids=["ev_merge_001"], requires_human=True)
    if health_state not in PASS_HEALTH_STATES:
        return _blocked("E_DEPLOY_HEALTH_UNKNOWN", "Post-deploy health state is missing or unknown.", remote_pr_number=remote_pr_number, head_sha=remote_head, evidence_ids=["ev_merge_001"])

    return {
        "status": "pass",
        "delivery_state": "deployed",
        "merge_allowed": True,
        "deploy_allowed": True,
        "blockers": [],
        "untrusted_remote_inputs": comments,
        "operation_checks": {
            "remote_head_checked": True,
            "approval_unexpired": True,
            "ci_status": ci_state,
            "review_status": review_state,
            "deploy_status": deploy_state,
            "health_status": health_state,
        },
    }


def script_command(request: dict[str, Any]) -> dict[str, Any]:
    validate_request(request, "delivery-operation")
    route = load_route_card_for_request(request)
    operation = request.get("operation")
    if operation == "prepare-pr-package":
        result = prepare_pr_result(route, request.get("input", {}).get("local") or {})
        return response(
            request,
            ok=result["status"] == "pass",
            status=result["status"],
            result=result,
            blockers=[blocker(item["code"], item["summary"], stage=item["stage"], owner_role=item["owner_role"], requires_human=item["requires_human"]) for item in result.get("blockers", [])],
            stage="prepare_pr",
        )
    if operation == "evaluate-land-deploy":
        ledger_path = safe_ledger_path(request)
        events, malformed = read_ledger(ledger_path)
        if malformed is not None:
            return response(request, ok=False, status="blocked", blockers=[blocker("E_LEDGER_MALFORMED", "Evidence ledger is malformed.", stage="land_deploy", owner_role="orchestrator")], stage="land_deploy")
        result = evaluate_land_deploy(
            route,
            events,
            request.get("input", {}).get("remote") or {},
            now=request.get("input", {}).get("now"),
        )
        return response(
            request,
            ok=result["status"] == "pass",
            status=result["status"],
            result=result,
            blockers=[blocker(item["code"], item["summary"], stage=item["stage"], owner_role=item["owner_role"], requires_human=item["requires_human"]) for item in result.get("blockers", [])],
            stage="land_deploy",
        )
    return response(request, ok=False, status="invalid_input", errors=[{"code": "E_SCHEMA_INVALID", "message": f"unsupported delivery operation: {operation}"}])


def main() -> int:
    raw = sys.stdin.read()
    try:
        request = json.loads(raw)
        payload = script_command(request)
    except json.JSONDecodeError as exc:
        payload = {
            "schema_version": SCRIPT_RESPONSE,
            "request_id": None,
            "ok": False,
            "status": "invalid_input",
            "work_item_id": None,
            "stage": None,
            "evidence_ids": [],
            "result": {},
            "blockers": [],
            "errors": [error("E_SCHEMA_INVALID", f"request is not JSON: {exc.msg}")],
            "warnings": [],
        }
    except ScriptFailure as exc:
        payload = {
            "schema_version": SCRIPT_RESPONSE,
            "request_id": None,
            "ok": False,
            "status": exc.status,
            "work_item_id": None,
            "stage": None,
            "evidence_ids": [],
            "result": exc.result,
            "blockers": exc.blockers,
            "errors": exc.errors or [error(exc.code, exc.message)],
            "warnings": exc.warnings,
        }
    except Exception as exc:
        payload = {
            "schema_version": SCRIPT_RESPONSE,
            "request_id": None,
            "ok": False,
            "status": "runtime_error",
            "work_item_id": None,
            "stage": None,
            "evidence_ids": [],
            "result": {},
            "blockers": [],
            "errors": [{"code": "E_DELIVERY_RUNTIME_ERROR", "message": str(exc)}],
            "warnings": [],
        }
    print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    return exit_code_for(payload)


__all__ = [
    "build_pr_package",
    "evaluate_land_deploy",
    "prepare_pr_result",
    "script_command",
]


if __name__ == "__main__":
    raise SystemExit(main())
