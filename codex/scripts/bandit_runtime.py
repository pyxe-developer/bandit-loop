#!/usr/bin/env python3
"""Core JSON runtime for Codex Bandit scripts."""

from __future__ import annotations

import copy
import datetime as _dt
import errno
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SCRIPT_REQUEST = "codex-bandit.script-request.v1"
SCRIPT_RESPONSE = "codex-bandit.script-response.v1"
ROUTE_CARD = "codex-bandit.route-card.v1"
EVIDENCE = "codex-bandit.evidence.v1"
ROLE_OUTPUT = "codex-bandit.role-output.v1"
VERDICT = "codex-bandit.verdict.v1"
TOOL_VERSION = "0.1.0"
HITL_REMOTE_HEAD_WARNING = "W_OPERATION_TIME_REMOTE_HEAD_REQUIRED"
WORK_ITEM_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,80}$")

STAGES = {
    "plan",
    "red",
    "green",
    "adversarial",
    "prepare_pr",
    "hitl_merge_checkpoint",
    "land_deploy",
    "closeout",
}
ROLES = {
    "orchestrator",
    "issue_planner",
    "test_writer",
    "code_writer",
    "adversarial_reviewer",
    "prepare_pr",
    "land_deploy",
    "closeout_retro",
    "human",
}
STATUSES = {
    "pass",
    "fail",
    "blocked",
    "invalid_input",
    "stale",
    "changes_requested",
    "cannot_judge",
    "deferred",
    "runtime_error",
}
RUBRIC_IDS = {
    "S1_SCOPE",
    "S2_RED",
    "S3_GREEN",
    "S4_REVIEW",
    "S5_DELIVERY",
    "S6_CLOSEOUT",
    "R1_SPEC",
    "R2_TEST_ADEQUACY",
    "R3_IMPLEMENTATION_QUALITY",
    "R4_FAILURE_MODES",
    "R5_BYPASS_RISK",
    "R6_EVIDENCE_BINDING",
    "R7_DELIVERY_SAFETY",
}
ENFORCED_ADDRESSES = {
    "issue_planner": "codex-bandit.issue-planner",
    "test_writer": "codex-bandit.test-writer",
    "code_writer": "codex-bandit.code-writer",
    "adversarial_reviewer": "codex-bandit.adversarial-reviewer",
    "prepare_pr": "codex-bandit.prepare-pr",
    "land_deploy": "codex-bandit.land-and-deploy",
    "closeout_retro": "codex-bandit.closeout-retro",
}
STAGE_OWNER = {
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


class ScriptFailure(Exception):
    def __init__(
        self,
        status: str,
        code: str,
        message: str,
        *,
        exit_code: int | None = None,
        blockers: list[dict[str, Any]] | None = None,
        errors: list[dict[str, Any]] | None = None,
        warnings: list[dict[str, Any]] | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.blockers = blockers or []
        self.errors = errors or []
        self.warnings = warnings or []
        self.result = result or {}


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def digest_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def blocker(
    code: str,
    message: str | None = None,
    *,
    stage: str | None = None,
    owner_role: str | None = None,
    severity: str = "blocker",
    retryable: bool = True,
    requires_human: bool = False,
    evidence_ids: list[str] | None = None,
    field_path: str | None = None,
    suggested_next_stage: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "message": message or code,
        "stage": stage or "plan",
        "owner_role": owner_role or STAGE_OWNER.get(stage or "plan", "orchestrator"),
        "retryable": retryable,
        "requires_human": requires_human,
    }
    if evidence_ids:
        out["evidence_ids"] = evidence_ids
    if field_path:
        out["field_path"] = field_path
    if suggested_next_stage:
        out["suggested_next_stage"] = suggested_next_stage
    return out


def error(code: str, message: str | None = None, *, field_path: str | None = None) -> dict[str, Any]:
    out = {"code": code, "message": message or code}
    if field_path:
        out["field_path"] = field_path
    return out


def response(
    request: dict[str, Any] | None,
    *,
    ok: bool,
    status: str,
    result: dict[str, Any] | None = None,
    blockers: list[dict[str, Any]] | None = None,
    errors: list[dict[str, Any]] | None = None,
    warnings: list[dict[str, Any]] | None = None,
    evidence_ids: list[str] | None = None,
    work_item_id: str | None = None,
    stage: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCRIPT_RESPONSE,
        "request_id": request.get("request_id") if isinstance(request, dict) else None,
        "ok": ok,
        "status": status,
        "work_item_id": work_item_id if work_item_id is not None else (request.get("work_item_id") if isinstance(request, dict) else None),
        "stage": stage if stage is not None else (request.get("stage") if isinstance(request, dict) else None),
        "evidence_ids": evidence_ids or [],
        "result": result or {},
        "blockers": blockers or [],
        "errors": errors or [],
        "warnings": warnings or [],
    }


def exit_code_for(resp: dict[str, Any]) -> int:
    if resp["ok"]:
        return 0
    if resp["status"] == "invalid_input":
        return 2
    if resp["status"] == "runtime_error":
        return 4
    if resp["status"] == "stale":
        return 3
    if any(b.get("code") in DRIFT_BLOCKERS for b in resp.get("blockers", [])):
        return 3
    return 1


def emit(resp: dict[str, Any]) -> int:
    print(json.dumps(resp, separators=(",", ":"), ensure_ascii=False))
    return exit_code_for(resp)


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


def repo_root_from_request(request: dict[str, Any]) -> Path:
    repo_root = request.get("repo_root")
    if not isinstance(repo_root, str) or not repo_root:
        raise_invalid("repo_root is required", "/repo_root")
    return Path(repo_root).expanduser().resolve()


def validate_work_item_id(value: Any, field_path: str = "/work_item_id") -> str:
    if not isinstance(value, str) or not WORK_ITEM_RE.fullmatch(value):
        raise_invalid("work_item_id must be a lowercase slug", field_path)
    if "/" in value or "\\" in value or ".." in value.split("."):
        raise_invalid("work_item_id must not contain path traversal", field_path)
    return value


def ensure_inside(base: Path, target: Path, message: str, field_path: str) -> Path:
    resolved = target.expanduser().resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        raise_invalid(message, field_path)
    return resolved


def work_dir(repo_root: Path, work_item_id: str) -> Path:
    validate_work_item_id(work_item_id)
    return (repo_root / ".codex-bandit" / "work" / work_item_id).resolve()


def work_parent(repo_root: Path) -> Path:
    return (repo_root / ".codex-bandit" / "work").resolve()


def safe_route_card_path(request: dict[str, Any]) -> Path:
    repo_root = repo_root_from_request(request)
    work_item_id = validate_work_item_id(request.get("work_item_id"))
    raw = require_string(request, "route_card_path")
    target = Path(raw)
    if not target.is_absolute():
        target = repo_root / target
    ensure_inside(work_parent(repo_root), target, "route_card_path must stay within .codex-bandit/work", "/route_card_path")
    wd = work_dir(repo_root, work_item_id)
    path = ensure_inside(wd, target, "route_card_path must stay within .codex-bandit/work/<work_item_id>", "/route_card_path")
    if path != wd / "route-card.json":
        raise_invalid("route_card_path must be .codex-bandit/work/<work_item_id>/route-card.json", "/route_card_path")
    return path


def safe_ledger_path(request: dict[str, Any]) -> Path:
    repo_root = repo_root_from_request(request)
    work_item_id = validate_work_item_id(request.get("work_item_id"))
    raw = request.get("ledger_path")
    if not isinstance(raw, str) or not raw:
        raise_invalid("ledger_path is required", "/ledger_path")
    target = Path(raw)
    if not target.is_absolute():
        target = repo_root / target
    ensure_inside(work_parent(repo_root), target, "ledger_path must stay within .codex-bandit/work", "/ledger_path")
    wd = work_dir(repo_root, work_item_id)
    path = ensure_inside(wd, target, "ledger_path must stay within .codex-bandit/work/<work_item_id>", "/ledger_path")
    if path != wd / "evidence.jsonl":
        raise_invalid("ledger_path must be .codex-bandit/work/<work_item_id>/evidence.jsonl", "/ledger_path")
    return path


def safe_repo_relative_path(repo_root: Path, raw: str, field_path: str) -> Path:
    target = Path(raw)
    if not target.is_absolute():
        target = repo_root / target
    return ensure_inside(repo_root, target, "path must stay inside repo root", field_path)


def require_string(obj: dict[str, Any], key: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value:
        raise_invalid(f"{key} is required", f"/{key}")
    return value


def raise_invalid(message: str, field_path: str = "") -> None:
    raise ScriptFailure(
        "invalid_input",
        "E_SCHEMA_INVALID",
        message,
        exit_code=2,
        errors=[error("E_SCHEMA_INVALID", message, field_path=field_path or None)],
    )


def validate_request(request: dict[str, Any], expected_command: str) -> None:
    if request.get("schema_version") != SCRIPT_REQUEST:
        raise_invalid("schema_version must be codex-bandit.script-request.v1", "/schema_version")
    if request.get("command") != expected_command:
        raise_invalid(f"command must be {expected_command}", "/command")
    for key in ["operation", "repo_root", "work_item_id", "route_card_path", "input", "caller", "request_id"]:
        if key not in request:
            raise_invalid(f"{key} is required", f"/{key}")
    if not isinstance(request["input"], dict):
        raise_invalid("input must be an object", "/input")
    caller = request["caller"]
    if not isinstance(caller, dict) or caller.get("role") not in ROLES or caller.get("mode") not in {"assisted", "manual", "enforced"}:
        raise_invalid("caller must include a valid role and mode", "/caller")
    validate_work_item_id(request["work_item_id"])
    safe_route_card_path(request)
    if expected_command in {"evidence-ledger", "verify-stage"}:
        safe_ledger_path(request)
    if "stage" in request and request["stage"] is not None and request["stage"] not in STAGES:
        raise_invalid("stage is not valid", "/stage")


def load_json_file(path: Path, field_path: str = "") -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise_invalid(f"{path} does not exist", field_path)
    except json.JSONDecodeError as exc:
        raise_invalid(f"{path} is not valid JSON: {exc.msg}", field_path)


def load_route_card_for_request(request: dict[str, Any]) -> dict[str, Any]:
    route = load_json_file(safe_route_card_path(request), "/route_card_path")
    if not isinstance(route, dict):
        raise_invalid("route card must be a JSON object", "/route_card_path")
    if route.get("work_item_id") != request.get("work_item_id"):
        raise ScriptFailure(
            "invalid_input",
            "E_ROUTE_CARD_WORK_ITEM_MISMATCH",
            "route card work_item_id must match request work_item_id",
            exit_code=2,
            errors=[error("E_ROUTE_CARD_WORK_ITEM_MISMATCH", "route card work_item_id must match request work_item_id", field_path="/work_item_id")],
        )
    return route


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
        try:
            dir_fd = os.open(str(path.parent), os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def git_head(repo_root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return proc.stdout.strip()
    except Exception:
        return None


def git_is_dirty(repo_root: Path) -> bool | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain", "--", ".", ":!.codex-bandit"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return bool(proc.stdout.strip())
    except Exception:
        return None


def git_diff_digest(repo_root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--binary"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        return digest_bytes(proc.stdout)
    except Exception:
        return None


def git_review_diff(repo_root: Path, route: dict[str, Any]) -> tuple[str, str]:
    review_diff = route.get("subject", {}).get("review_diff", {})
    base = review_diff.get("base") or route.get("subject", {}).get("base_ref")
    head = review_diff.get("head") or route.get("subject", {}).get("head_ref")
    if not isinstance(base, str) or not base or not isinstance(head, str) or not head:
        raise ScriptFailure(
            "blocked",
            "E_REVIEW_DIFF_UNAVAILABLE",
            "Route card does not define a review diff base/head.",
            blockers=[blocker("E_REVIEW_DIFF_UNAVAILABLE", "Route card does not define a review diff base/head.", stage="adversarial", owner_role="orchestrator")],
        )
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--binary", f"{base}...{head}"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError:
        try:
            proc = subprocess.run(
                ["git", "-C", str(repo_root), "diff", "--binary", base, head],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as exc:
            raise ScriptFailure(
                "blocked",
                "E_REVIEW_DIFF_UNAVAILABLE",
                "Unable to build review diff from route-card base/head.",
                blockers=[blocker("E_REVIEW_DIFF_UNAVAILABLE", "Unable to build review diff from route-card base/head.", stage="adversarial", owner_role="orchestrator")],
            ) from exc
    diff = proc.stdout.decode("utf-8", errors="replace")
    return diff, digest_bytes(proc.stdout)


def path_matches(path: str, pattern: str) -> bool:
    from fnmatch import fnmatch

    return fnmatch(path, pattern)


def any_path_matches(paths: list[str], patterns: list[str]) -> bool:
    return any(path_matches(path, pattern) for path in paths for pattern in patterns)


def validate_basic_schema(value: Any, schema_name: str) -> list[dict[str, Any]]:
    schema_path = Path(__file__).resolve().parents[1] / "references" / "schemas" / "contract-schemas.json"
    if not schema_path.exists():
        return []
    schemas = json.loads(schema_path.read_text(encoding="utf-8")).get("schemas", {})
    schema = schemas.get(schema_name)
    if not schema:
        return []
    errors: list[dict[str, Any]] = []

    def walk(v: Any, s: dict[str, Any], path: str) -> None:
        typ = s.get("type")
        if typ == "object" and not isinstance(v, dict):
            errors.append(error("E_SCHEMA_INVALID", "expected object", field_path=path))
            return
        if typ == "array" and not isinstance(v, list):
            errors.append(error("E_SCHEMA_INVALID", "expected array", field_path=path))
            return
        if typ == "string" and not isinstance(v, str):
            errors.append(error("E_SCHEMA_INVALID", "expected string", field_path=path))
            return
        if typ == "boolean" and not isinstance(v, bool):
            errors.append(error("E_SCHEMA_INVALID", "expected boolean", field_path=path))
            return
        if "const" in s and v != s["const"]:
            errors.append(error("E_SCHEMA_INVALID", f"expected {s['const']}", field_path=path))
        if "enum" in s and v not in s["enum"]:
            errors.append(error("E_SCHEMA_INVALID", "unexpected enum value", field_path=path))
        if isinstance(v, dict):
            for key in s.get("required", []):
                if key not in v:
                    errors.append(error("E_SCHEMA_INVALID", f"{key} is required", field_path=f"{path}/{key}"))
            props = s.get("properties", {})
            for key, child_schema in props.items():
                if key in v and isinstance(child_schema, dict):
                    walk(v[key], child_schema, f"{path}/{key}")

    walk(value, schema, "")
    return errors


def validate_route_card(route: dict[str, Any], *, install_events: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    errors = validate_basic_schema(route, ROUTE_CARD)
    if route.get("schema_version") != ROUTE_CARD:
        errors.append(error("E_ROUTE_CARD_INVALID", "schema_version must be codex-bandit.route-card.v1", field_path="/schema_version"))
        return errors

    work_item_id = route.get("work_item_id")
    if not isinstance(work_item_id, str) or not WORK_ITEM_RE.fullmatch(work_item_id):
        errors.append(error("E_ROUTE_CARD_INVALID", "work_item_id is invalid", field_path="/work_item_id"))

    stage_plan = route.get("stage_plan", {})
    enabled = stage_plan.get("enabled_stages")
    current = stage_plan.get("current_stage")
    lifecycle = stage_plan.get("lifecycle_state")
    if not isinstance(enabled, list) or not enabled or len(enabled) != len(set(enabled)) or any(stage not in STAGES for stage in enabled):
        errors.append(error("E_ROUTE_CARD_INVALID", "enabled_stages must be ordered unique stage IDs", field_path="/stage_plan/enabled_stages"))
    elif lifecycle not in {"complete", "abandoned"} and current not in enabled:
        errors.append(error("E_ROUTE_CARD_STAGE_NOT_ENABLED", "current_stage must appear in enabled_stages", field_path="/stage_plan/current_stage"))
    if isinstance(enabled, list):
        local_required = {"plan", "red", "green", "adversarial", "closeout"}
        if not local_required.issubset(set(enabled)):
            errors.append(error("E_ROUTE_CARD_INVALID", "local stages are required", field_path="/stage_plan/enabled_stages"))
        authority = route.get("delivery_authority", {})
        delivery_requested = any(
            bool(authority.get(key))
            for key in ["allow_branch_push", "allow_pr_create", "allow_merge"]
        ) or authority.get("deploy_contract") is not None
        if delivery_requested and not {"prepare_pr", "hitl_merge_checkpoint", "land_deploy"}.issubset(set(enabled)):
            errors.append(error("E_ROUTE_CARD_INVALID", "delivery authority requires delivery stages", field_path="/stage_plan/enabled_stages"))

    repo_root = Path(route.get("repo", {}).get("root", ".")).expanduser().resolve()
    for name, spec in route.get("commands", {}).items():
        argv = spec.get("argv")
        if not isinstance(argv, list) or not all(isinstance(item, str) and item for item in argv):
            errors.append(error("E_ROUTE_CARD_COMMAND_ARGV", f"commands.{name}.argv must be an array", field_path=f"/commands/{name}/argv"))
        cwd = spec.get("cwd", ".")
        if not isinstance(cwd, str):
            errors.append(error("E_ROUTE_CARD_COMMAND_CWD", "command cwd must be a string", field_path=f"/commands/{name}/cwd"))
        else:
            try:
                safe_repo_relative_path(repo_root, cwd, f"/commands/{name}/cwd")
            except ScriptFailure:
                errors.append(error("E_ROUTE_CARD_COMMAND_CWD", "command cwd must stay inside repo root", field_path=f"/commands/{name}/cwd"))

    authority = route.get("delivery_authority", {})
    if authority.get("allow_pr_create") and not authority.get("allow_branch_push") and not has_remote_branch_evidence(install_events or []):
        errors.append(error("E_PR_CREATE_AUTHORITY", "allow_pr_create requires allow_branch_push or remote-branch evidence", field_path="/delivery_authority/allow_pr_create"))
    hitl = authority.get("hitl_merge_checkpoint", {})
    if isinstance(hitl, dict) and any(hitl.get(key) is not None for key in ["pr_number", "head_sha", "approved_by", "approval_evidence_id", "approved_at"]):
        events = install_events or []
        approval_id = hitl.get("approval_evidence_id")
        has_matching_event = approval_id and any(event.get("id") == approval_id and event.get("record_type") == "approval" for event in events)
        if not has_matching_event:
            errors.append(error("E_PREBOUND_MERGE_APPROVAL", "approval evidence cannot be prebound before matching ledger event", field_path="/delivery_authority/hitl_merge_checkpoint"))

    capability = route.get("capability_mode", {})
    if capability.get("mode") == "enforced" and not validate_enforced_mode(route, install_events or {}).get("valid"):
        errors.append(error("E_ENFORCED_MODE_NOT_VALIDATED", "enforced mode requires install-agent validation evidence", field_path="/capability_mode"))

    return errors


def has_remote_branch_evidence(events: list[dict[str, Any]]) -> bool:
    for event in events:
        if event.get("record_type") in {"command", "transition", "note"} and event.get("status") == "pass":
            claim = str(event.get("claim", ""))
            if "remote_branch_exists" in claim or "branch_exists_remotely" in claim:
                return True
    return False


def read_ledger(path: Path) -> tuple[list[dict[str, Any]], list[str] | None]:
    if not path.exists():
        return [], None
    lines = path.read_text(encoding="utf-8").splitlines()
    events: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            return events, lines
        if not isinstance(value, dict):
            return events, lines
        events.append(value)
    return events, None


def parse_jsonl_lines(lines: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            return events, blocker("E_LEDGER_MALFORMED", "Evidence ledger contains malformed JSONL.", stage="red", owner_role="orchestrator")
        if not isinstance(value, dict):
            return events, blocker("E_LEDGER_MALFORMED", "Evidence ledger contains a non-object JSONL record.", stage="red", owner_role="orchestrator")
        events.append(value)
    return events, None


def validate_event(event: dict[str, Any]) -> list[dict[str, Any]]:
    errors = validate_basic_schema(event, EVIDENCE)
    scope = event.get("subject_scope")
    if scope == "product" and not isinstance(event.get("subject"), dict):
        errors.append(error("E_SCHEMA_INVALID", "subject is required for product evidence", field_path="/subject"))
    if scope == "agent_config" and not isinstance(event.get("agent_config_subject"), dict):
        errors.append(error("E_SCHEMA_INVALID", "agent_config_subject is required", field_path="/agent_config_subject"))
    record_type = event.get("record_type")
    if record_type == "command" and not isinstance(event.get("command"), dict):
        errors.append(error("E_SCHEMA_INVALID", "command payload is required", field_path="/command"))
    if record_type == "verdict" and not isinstance(event.get("verdict"), dict):
        errors.append(error("E_SCHEMA_INVALID", "verdict payload is required", field_path="/verdict"))
    if record_type == "approval" and not isinstance(event.get("approval"), dict):
        errors.append(error("E_SCHEMA_INVALID", "approval payload is required", field_path="/approval"))
    if (record_type == "blocker" or event.get("status") == "blocked") and not isinstance(event.get("blocker"), dict):
        errors.append(error("E_SCHEMA_INVALID", "blocker payload is required", field_path="/blocker"))
    if record_type == "route_update" and not isinstance(event.get("route_update"), dict):
        errors.append(error("E_SCHEMA_INVALID", "route_update payload is required", field_path="/route_update"))
    if record_type == "transition" and not isinstance(event.get("transition"), dict):
        errors.append(error("E_SCHEMA_INVALID", "transition payload is required", field_path="/transition"))
    if record_type == "note" and not isinstance(event.get("note"), dict):
        errors.append(error("E_SCHEMA_INVALID", "note payload is required", field_path="/note"))
    return errors


def recording_admissibility(route: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    mode = route.get("capability_mode", {}).get("mode")
    recorded_by = event.get("recorded_by") or {}
    actor = event.get("actor") or {}
    identity = event.get("identity_strength")
    stage = event.get("stage")
    event_id = event.get("id")
    if mode == "assisted":
        if recorded_by.get("role") != "orchestrator" or recorded_by.get("mode") != "assisted":
            return {"valid": False, "code": "E_APPEND_AUTHORITY_INVALID", "message": "Assisted evidence must be recorded_by orchestrator/assisted.", "stage": stage, "evidence_ids": [event_id] if event_id else []}
        if actor.get("role") == "human":
            if identity != "human_verified":
                return {"valid": False, "code": "E_IDENTITY_STRENGTH_INVALID", "message": "Human evidence requires human_verified identity_strength.", "stage": stage, "evidence_ids": [event_id] if event_id else []}
        elif identity not in {"declared", "system"}:
            return {"valid": False, "code": "E_IDENTITY_STRENGTH_INVALID", "message": "Assisted role evidence requires declared identity_strength.", "stage": stage, "evidence_ids": [event_id] if event_id else []}
    elif mode == "enforced":
        if actor.get("role") != "human" and event.get("record_type") != "actor_identity" and identity != "validated_agent":
            return {"valid": False, "code": "E_ENFORCED_IDENTITY_INVALID", "message": "Enforced role evidence requires validated_agent identity_strength.", "stage": stage, "evidence_ids": [event_id] if event_id else []}
    elif mode == "manual":
        if recorded_by.get("role") != "human" and recorded_by.get("mode") != "manual":
            return {"valid": False, "code": "E_APPEND_AUTHORITY_INVALID", "message": "Manual evidence must be recorded by a manual caller.", "stage": stage, "evidence_ids": [event_id] if event_id else []}
    return {"valid": True}


def authority_blocker(route: dict[str, Any], event: dict[str, Any]) -> dict[str, Any] | None:
    admissibility = recording_admissibility(route, event)
    if admissibility.get("valid"):
        return None
    return blocker(
        admissibility["code"],
        admissibility["message"],
        stage=admissibility.get("stage") or event.get("stage"),
        owner_role="orchestrator",
        evidence_ids=admissibility.get("evidence_ids") or None,
    )


def append_event(ledger_path: Path, event: dict[str, Any]) -> tuple[bool, list[dict[str, Any]], list[dict[str, Any]]]:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = ledger_path.with_suffix(ledger_path.suffix + ".lock")
    warnings: list[dict[str, Any]] = []
    with open(lock_path, "a+", encoding="utf-8") as lock_fh:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        existing, malformed = read_ledger(ledger_path)
        if malformed is not None:
            raise ScriptFailure(
                "blocked",
                "E_LEDGER_MALFORMED",
                "Evidence ledger contains malformed JSONL.",
                blockers=[blocker("E_LEDGER_MALFORMED", "Evidence ledger contains malformed JSONL.", stage=event.get("stage"), owner_role="orchestrator")],
            )
        event_id = event.get("id")
        for prior in existing:
            if prior.get("id") == event_id:
                if canonical_json(prior) == canonical_json(event):
                    warnings.append({"code": "W_DUPLICATE_IDEMPOTENT_APPEND", "message": "Duplicate event payload already exists."})
                    return False, [event_id], warnings
                raise ScriptFailure(
                    "blocked",
                    "E_DUPLICATE_EVIDENCE_ID",
                    "Evidence ID already exists with a different payload.",
                    blockers=[blocker("E_DUPLICATE_EVIDENCE_ID", "Evidence ID already exists with a different payload.", stage=event.get("stage"), owner_role="orchestrator", evidence_ids=[event_id])],
                )
        line = json.dumps(event, separators=(",", ":"), ensure_ascii=False) + "\n"
        with open(ledger_path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        return True, [event_id], warnings


def stage_attempt_number(event: dict[str, Any]) -> int:
    raw = str(event.get("stage_attempt_id", ""))
    match = re.search(r":attempt-(\d+)$", raw)
    return int(match.group(1)) if match else 0


def same_subject(a: dict[str, Any], b: dict[str, Any]) -> bool:
    keys = ["base_ref", "head_ref", "head_sha", "diff_digest"]
    return all(a.get(key) == b.get(key) for key in keys if key in a or key in b)


def reduce_stage(route: dict[str, Any], events: list[dict[str, Any]], stage: str, *, jsonl_lines: list[str] | None = None) -> dict[str, Any]:
    if jsonl_lines is not None:
        parsed, malformed = parse_jsonl_lines(jsonl_lines)
        if malformed:
            return reducer_result(route, stage, "blocked", blockers=[malformed])
        events = parsed

    route_work_item = route.get("work_item_id")
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    inactive: set[str] = set()
    seen: dict[str, str] = {}
    attempt_subject: dict[str, dict[str, Any]] = {}
    active_events: list[dict[str, Any]] = []
    prior_created_at: str | None = None

    for event in events:
        event_id = event.get("id")
        if not event_id:
            return reducer_result(route, stage, "blocked", blockers=[blocker("E_LEDGER_MALFORMED", "Evidence event is missing id.", stage=stage, owner_role="orchestrator")])
        canon = canonical_json(event)
        if event_id in seen and seen[event_id] != canon:
            return reducer_result(route, stage, "blocked", blockers=[blocker("E_DUPLICATE_EVIDENCE_ID", "Duplicate evidence id has conflicting payload.", stage=event.get("stage", stage), owner_role="orchestrator", evidence_ids=[event_id])])
        seen.setdefault(event_id, canon)

        if event.get("work_item_id") != route_work_item:
            continue
        created_at = event.get("created_at")
        if isinstance(created_at, str) and prior_created_at and created_at < prior_created_at:
            warnings.append({"code": "W_CREATED_AT_BACKDATED", "message": "created_at is earlier than a prior appended record; append order was preserved."})
        if isinstance(created_at, str):
            prior_created_at = created_at

        for superseded in event.get("supersedes", []) or []:
            inactive.add(superseded)
        if event.get("record_type") == "supersession":
            for superseded in event.get("supersedes", []) or []:
                inactive.add(superseded)

        if event.get("record_type") == "command" and event.get("subject_scope") == "product":
            attempt = event.get("stage_attempt_id")
            subject = event.get("subject") or {}
            if attempt not in attempt_subject:
                attempt_subject[attempt] = subject
            elif not same_subject(attempt_subject[attempt], subject):
                if event.get("stage") == stage:
                    return reducer_result(
                        route,
                        stage,
                        "stale",
                        blockers=[blocker("E_STAGE_ATTEMPT_SUBJECT_DIVERGED", "Command evidence diverged from the locked stage-attempt subject.", stage=stage, owner_role=STAGE_OWNER.get(stage), evidence_ids=[event_id])],
                        warnings=warnings,
                    )
                inactive.add(event_id)
                continue
        active_events.append(event)

    active = [event for event in active_events if event.get("id") not in inactive]
    result = _reduce_stage_active(route, active, inactive, stage)
    result["warnings"].extend(warnings)
    return result


def reducer_result(
    route: dict[str, Any],
    stage: str,
    status: str,
    *,
    active_ids: list[str] | None = None,
    inactive_ids: list[str] | None = None,
    blockers: list[dict[str, Any]] | None = None,
    warnings: list[dict[str, Any]] | None = None,
    attempt: dict[str, Any] | None = None,
    delivery_state: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ok": status == "pass",
        "work_item_id": route.get("work_item_id"),
        "stage": stage,
        "status": status,
        "active_evidence_ids": active_ids or [],
        "inactive_evidence_ids": inactive_ids or [],
        "attempt": attempt or {},
        "blockers": blockers or [],
        "warnings": warnings or [],
    }
    if delivery_state:
        out["delivery_state"] = delivery_state
    return out


def latest(events: list[dict[str, Any]], *, stage: str, record_types: set[str] | None = None) -> dict[str, Any] | None:
    candidates = [event for event in events if event.get("stage") == stage and (record_types is None or event.get("record_type") in record_types)]
    return candidates[-1] if candidates else None


def passing_red(route: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.get("stage") == "red" and red_event_passes(route, event):
            return event
    return None


def passing_green(route: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any] | None:
    red = passing_red(route, events)
    if not red:
        return None
    for event in reversed(events):
        if event.get("stage") == "green" and green_event_passes(route, event):
            return event
    return None


def latest_adversarial_approval(route: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.get("stage") == "adversarial" and adversarial_event_passes(route, event):
            return event
    return None


def red_event_passes(route: dict[str, Any], event: dict[str, Any]) -> bool:
    if event.get("record_type") != "command" or event.get("status") != "pass":
        return False
    if event.get("actor", {}).get("role") != "test_writer":
        return False
    if not recording_admissibility(route, event).get("valid"):
        return False
    if any_path_matches(event.get("files_changed", []) or [], ["src/**"]):
        return False
    command = event.get("command", {})
    if command.get("name") != "red":
        return False
    expected_codes = route.get("commands", {}).get("red", {}).get("success_exit_codes", [1])
    if command.get("exit_code") not in expected_codes:
        return False
    expected = command.get("expected_failure_result", {})
    return bool(expected.get("matched")) and not expected.get("unexpected_patterns")


def green_event_passes(route: dict[str, Any], event: dict[str, Any]) -> bool:
    if event.get("record_type") != "command" or event.get("status") != "pass":
        return False
    if event.get("actor", {}).get("role") != "code_writer":
        return False
    if not recording_admissibility(route, event).get("valid"):
        return False
    if any_path_matches(event.get("files_changed", []) or [], ["tests/**"]):
        return False
    command = event.get("command", {})
    expected_codes = route.get("commands", {}).get("green", {}).get("success_exit_codes", [0])
    return command.get("name") == "green" and command.get("exit_code") in expected_codes


def adversarial_event_passes(route: dict[str, Any], event: dict[str, Any]) -> bool:
    if event.get("record_type") != "verdict" or event.get("status") != "pass":
        return False
    if event.get("actor", {}).get("role") != "adversarial_reviewer":
        return False
    if not recording_admissibility(route, event).get("valid"):
        return False
    verdict = event.get("verdict", {})
    if verdict.get("verdict") != "approve":
        return False
    if not validate_verdict(verdict).get("valid"):
        return False
    subject = verdict.get("subject") or event.get("subject") or {}
    expected_head = route.get("subject", {}).get("expected_head_sha")
    if expected_head and subject.get("head_sha") != expected_head:
        return False
    digest = verdict.get("review_package_digest")
    if not digest:
        return False
    subject_digest = subject.get("review_package_digest")
    if subject_digest and subject_digest != digest:
        return False
    route_package = route.get("evidence", {}).get("review_package")
    if isinstance(route_package, dict) and route_package.get("digest") and route_package.get("digest") != digest:
        return False
    return True


def _reduce_stage_active(route: dict[str, Any], active: list[dict[str, Any]], inactive: set[str], stage: str) -> dict[str, Any]:
    if stage == "red":
        event = latest(active, stage="red", record_types={"command", "blocker"})
        if not event:
            return reducer_result(route, stage, "not_started")
        if event.get("blocker"):
            return reducer_result(route, stage, "blocked", blockers=[event["blocker"]])
        b = authority_blocker(route, event)
        if b:
            return reducer_result(route, stage, "blocked", blockers=[b])
        if event.get("actor", {}).get("role") != "test_writer":
            return reducer_result(route, stage, "blocked", blockers=[blocker("E_WRONG_ACTOR_ROLE", "RED evidence must be produced by test_writer.", stage=stage, owner_role="test_writer", evidence_ids=[event["id"]])])
        if any_path_matches(event.get("files_changed", []) or [], ["src/**"]):
            return reducer_result(route, stage, "blocked", blockers=[blocker("E_FORBIDDEN_PATH_CHANGED", "RED must not change implementation paths.", stage=stage, owner_role="test_writer", evidence_ids=[event["id"]])])
        command = event.get("command", {})
        expected = command.get("expected_failure_result", {})
        if not expected.get("matched") or expected.get("unexpected_patterns"):
            return reducer_result(route, stage, "blocked", blockers=[blocker("E_RED_UNEXPECTED_FAILURE", "RED failed for an unexpected reason.", stage=stage, owner_role="test_writer", evidence_ids=[event["id"]])])
        if not red_event_passes(route, event):
            return reducer_result(route, stage, "fail", active_ids=[event["id"]])
        return reducer_result(route, stage, "pass", active_ids=[event["id"]])

    if stage == "green":
        event = latest(active, stage="green", record_types={"command", "blocker"})
        if event and event.get("blocker"):
            return reducer_result(route, stage, "blocked", active_ids=[event["id"]], blockers=[event["blocker"]])
        red = passing_red(route, active)
        if not red:
            return reducer_result(route, stage, "blocked", blockers=[blocker("E_RED_REQUIRED", "GREEN requires an active RED pass.", stage=stage, owner_role="test_writer")])
        if not event:
            return reducer_result(route, stage, "not_started", active_ids=[red["id"]])
        b = authority_blocker(route, event)
        if b:
            return reducer_result(route, stage, "blocked", active_ids=[red["id"], event["id"]], blockers=[b])
        if event.get("actor", {}).get("role") != "code_writer":
            return reducer_result(route, stage, "blocked", blockers=[blocker("E_WRONG_ACTOR_ROLE", "GREEN evidence must be produced by code_writer.", stage=stage, owner_role="code_writer", evidence_ids=[event["id"]])])
        if any_path_matches(event.get("files_changed", []) or [], ["tests/**"]):
            return reducer_result(route, stage, "blocked", blockers=[blocker("E_FORBIDDEN_PATH_CHANGED", "GREEN must not change test paths.", stage=stage, owner_role="code_writer", evidence_ids=[event["id"]])])
        if green_event_passes(route, event):
            return reducer_result(route, stage, "pass", active_ids=[red["id"], event["id"]])
        return reducer_result(route, stage, "fail", active_ids=[red["id"], event["id"]])

    if stage == "adversarial":
        red = passing_red(route, active)
        green = passing_green(route, active)
        if not red:
            return reducer_result(route, stage, "blocked", blockers=[blocker("E_RED_REQUIRED", "Adversarial review requires active RED evidence.", stage=stage, owner_role="test_writer")])
        if not green:
            return reducer_result(route, stage, "blocked", blockers=[blocker("E_GREEN_REQUIRED", "Adversarial review requires active GREEN evidence.", stage=stage, owner_role="code_writer")])
        event = latest(active, stage="adversarial", record_types={"verdict", "blocker"})
        if not event:
            return reducer_result(route, stage, "not_started", active_ids=[red["id"], green["id"]])
        if event.get("blocker") and event.get("status") == "blocked":
            return reducer_result(route, stage, "blocked", active_ids=[red["id"], green["id"], event["id"]], blockers=[event["blocker"]], attempt={"retry_budget_consumed": False})
        b = authority_blocker(route, event)
        if b:
            return reducer_result(route, stage, "blocked", active_ids=[red["id"], green["id"], event["id"]], blockers=[b])
        verdict = event.get("verdict", {})
        validation = validate_verdict(verdict)
        if not validation["valid"]:
            return reducer_result(route, stage, "blocked", blockers=[blocker(validation["code"], validation["message"], stage=stage, owner_role="adversarial_reviewer", evidence_ids=[event["id"]])])
        subject = verdict.get("subject") or event.get("subject") or {}
        expected_head = route.get("subject", {}).get("expected_head_sha")
        if expected_head and subject.get("head_sha") != expected_head:
            return reducer_result(route, stage, "stale", active_ids=[red["id"], green["id"], event["id"]], blockers=[blocker("E_STALE_SUBJECT", "Adversarial verdict head does not match route-card expected head.", stage=stage, owner_role="adversarial_reviewer", evidence_ids=[event["id"]])])
        if verdict.get("review_package_digest"):
            subject_digest = subject.get("review_package_digest")
            route_package = route.get("evidence", {}).get("review_package")
            route_digest = route_package.get("digest") if isinstance(route_package, dict) else None
            if (subject_digest and subject_digest != verdict["review_package_digest"]) or (route_digest and route_digest != verdict["review_package_digest"]):
                return reducer_result(route, stage, "blocked", active_ids=[red["id"], green["id"], event["id"]], blockers=[blocker("E_REVIEW_PACKAGE_DIGEST_MISMATCH", "Adversarial verdict is not bound to the active review package digest.", stage=stage, owner_role="adversarial_reviewer", evidence_ids=[event["id"]])])
        if verdict.get("verdict") == "approve":
            inactive_ids = [item for item in inactive if item.startswith("ev_adv")]
            active_ids = [red["id"], green["id"], event["id"]]
            used_total = max(0, stage_attempt_number(green) - 1)
            return reducer_result(route, stage, "pass", active_ids=active_ids, inactive_ids=inactive_ids, attempt={"used_total": used_total})
        if verdict.get("verdict") == "changes_requested":
            return reducer_result(route, stage, "changes_requested", active_ids=[red["id"], green["id"], event["id"]])
        if verdict.get("verdict") == "cannot_judge":
            reason = verdict.get("cannot_judge_reason") or {}
            code = reason.get("code", "E_CANNOT_JUDGE")
            if code in {"PROVIDER_TIMEOUT", "E_PROVIDER_TIMEOUT"} or event.get("status") == "blocked":
                b = event.get("blocker") or blocker("E_PROVIDER_TIMEOUT", reason.get("message", "Provider timed out."), stage=stage, owner_role="orchestrator")
                return reducer_result(route, stage, "blocked", active_ids=[red["id"], green["id"], event["id"]], blockers=[b], attempt={"retry_budget_consumed": False})
            return reducer_result(route, stage, "cannot_judge", active_ids=[red["id"], green["id"], event["id"]], blockers=[blocker(code, reason.get("message", code), stage=stage, owner_role="orchestrator")], attempt={"retry_budget_consumed": True})

    if stage == "prepare_pr":
        adv = latest_adversarial_approval(route, active)
        if not adv:
            return reducer_result(route, stage, "blocked", blockers=[blocker("E_ADVERSARIAL_APPROVAL_REQUIRED", "prepare_pr requires active adversarial approval.", stage=stage, owner_role="adversarial_reviewer")])
        event = latest(active, stage=stage)
        if not event:
            return reducer_result(route, stage, "not_started", active_ids=[adv["id"]])
        if event.get("status") == "deferred":
            return reducer_result(route, stage, "deferred", active_ids=[adv["id"], event["id"]], delivery_state="delivery_deferred")
        return reducer_result(route, stage, event.get("status", "blocked"), active_ids=[adv["id"], event["id"]])

    if stage == "hitl_merge_checkpoint":
        adv = latest_adversarial_approval(route, active)
        event = latest(active, stage=stage, record_types={"approval", "blocker"})
        if not adv:
            return reducer_result(route, stage, "blocked", blockers=[blocker("E_ADVERSARIAL_APPROVAL_REQUIRED", "HITL merge requires active adversarial approval.", stage=stage, owner_role="adversarial_reviewer")])
        if not event:
            return reducer_result(route, stage, "blocked", blockers=[blocker("E_HITL_APPROVAL_REQUIRED", "Merge requires a human approval event.", stage=stage, owner_role="human", requires_human=True)])
        valid = validate_hitl_approval(route, event, last_active_adversarial_head=(adv.get("subject") or {}).get("head_sha"))
        if not valid["valid"]:
            return reducer_result(route, stage, "blocked", blockers=[blocker(valid["code"], valid["message"], stage=stage, owner_role="human", evidence_ids=[event["id"]], requires_human=True)], delivery_state="delivery_blocked")
        warnings = []
        if not valid.get("remote_head_checked"):
            warnings.append({"code": HITL_REMOTE_HEAD_WARNING, "message": "verify-stage validated ledger consistency only; Ticket 07 must check current remote PR head at merge time."})
        return reducer_result(route, stage, "pass", active_ids=[adv["id"], event["id"]], warnings=warnings, delivery_state="merge_approved")

    if stage == "land_deploy":
        adv = latest_adversarial_approval(route, active)
        if not adv:
            return reducer_result(route, stage, "blocked", blockers=[blocker("E_ADVERSARIAL_APPROVAL_REQUIRED", "land_deploy requires active adversarial approval.", stage=stage, owner_role="adversarial_reviewer")])
        approval = latest(active, stage="hitl_merge_checkpoint", record_types={"approval"})
        if not approval:
            return reducer_result(route, stage, "blocked", blockers=[blocker("E_HITL_APPROVAL_REQUIRED", "land_deploy requires active HITL merge approval.", stage=stage, owner_role="human", requires_human=True)])
        valid = validate_hitl_approval(route, approval, last_active_adversarial_head=(adv.get("subject") or {}).get("head_sha"))
        if not valid["valid"]:
            return reducer_result(route, stage, "blocked", blockers=[blocker(valid["code"], valid["message"], stage=stage, owner_role="human", evidence_ids=[approval["id"]], requires_human=True)], delivery_state="delivery_blocked")
        event = latest(active, stage=stage)
        if not event:
            return reducer_result(route, stage, "not_started", active_ids=[adv["id"], approval["id"]])
        if event.get("blocker"):
            return reducer_result(route, stage, "blocked", active_ids=[adv["id"], approval["id"], event["id"]], blockers=[event["blocker"]], delivery_state="delivery_blocked")
        return reducer_result(route, stage, event.get("status", "blocked"), active_ids=[adv["id"], approval["id"], event["id"]])

    if stage == "closeout":
        deferred = next((event for event in active if event.get("stage") in {"prepare_pr", "hitl_merge_checkpoint", "land_deploy"} and event.get("status") == "deferred"), None)
        event = latest(active, stage="closeout", record_types={"note", "transition"})
        if event and event.get("status") == "pass":
            return reducer_result(route, stage, "pass", active_ids=[event["id"]], delivery_state="delivery_deferred" if deferred else None)
        if deferred:
            return reducer_result(route, stage, "blocked", active_ids=[deferred["id"]], blockers=[blocker("E_CLOSEOUT_REQUIRED", "Deferred delivery requires closeout.", stage=stage, owner_role="closeout_retro")], delivery_state="delivery_deferred")
        return reducer_result(route, stage, "not_started")

    return reducer_result(route, stage, "not_started")


def validate_verdict(verdict: dict[str, Any]) -> dict[str, Any]:
    if verdict.get("schema_version") != VERDICT:
        return {"valid": False, "code": "E_VERDICT_SCHEMA_INVALID", "message": "Verdict schema_version is invalid."}
    status = verdict.get("verdict")
    rubric_ids = verdict.get("rubric_ids")
    if not isinstance(rubric_ids, list) or not rubric_ids:
        return {"valid": False, "code": "E_VERDICT_RUBRICS_REQUIRED", "message": "approve requires at least one rubric_id"}
    unknown = [rid for rid in rubric_ids if rid not in RUBRIC_IDS]
    if unknown:
        return {"valid": False, "code": "E_UNKNOWN_RUBRIC_ID", "message": f"unknown rubric_id: {', '.join(unknown)}"}
    findings = verdict.get("findings") or []
    test_findings = verdict.get("test_surface_findings") or []
    if status == "changes_requested" and not findings and not test_findings:
        return {"valid": False, "code": "E_VERDICT_FINDINGS_REQUIRED", "message": "changes_requested requires findings."}
    if status == "cannot_judge" and not verdict.get("cannot_judge_reason"):
        return {"valid": False, "code": "E_CANNOT_JUDGE_REASON_REQUIRED", "message": "cannot_judge requires a reason."}
    if status not in {"approve", "changes_requested", "cannot_judge"}:
        return {"valid": False, "code": "E_VERDICT_INVALID", "message": "Verdict value is invalid."}
    return {"valid": True, "status": "pass" if status == "approve" else status}


def validate_hitl_approval(
    route: dict[str, Any],
    event: dict[str, Any],
    *,
    last_active_adversarial_head: str | None,
    remote_pr_head_sha: str | None = None,
) -> dict[str, Any]:
    approval = event.get("approval", {})
    expected = route.get("subject", {}).get("expected_head_sha")
    head = approval.get("head_sha") or (event.get("subject") or {}).get("head_sha")
    remote = remote_pr_head_sha
    if event.get("actor", {}).get("role") != "human" or approval.get("kind") != "merge":
        return {"valid": False, "code": "E_HITL_APPROVAL_REQUIRED", "message": "Merge approval must come from a human approval event."}
    if expected and head != expected:
        return {"valid": False, "code": "E_STALE_SUBJECT", "message": "Approval head does not match route-card expected head."}
    if remote and head != remote:
        return {"valid": False, "code": "E_STALE_SUBJECT", "message": "Approval head does not match remote PR head."}
    if last_active_adversarial_head and head != last_active_adversarial_head:
        return {"valid": False, "code": "E_UNREVIEWED_MERGE_HEAD", "message": "HITL-approved head was not the last active adversarial-approved head."}
    return {"valid": True, "delivery_state": "merge_approved", "remote_head_checked": remote_pr_head_sha is not None}


def validate_delivery_blocker(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("delivery_state") == "delivery_blocked":
        evidence_ids = value.get("evidence_ids") or []
        merged = bool(value.get("merged", False)) or value.get("code") == "E_DEPLOY_HEALTH_FAILED" or any("merge" in str(item) for item in evidence_ids)
        return {"valid": True, "merge_allowed": False, "deployed": False, "merged": merged}
    return {"valid": True}


def false_enforcement_claim(text: str) -> bool:
    lower = text.lower()
    if "assisted" not in lower:
        return False
    forbidden = ["sandbox isolation", "model enforcement", "tool-policy enforcement", "role isolation", "enforces sandbox"]
    return any(item in lower for item in forbidden)


def validate_enforced_mode(
    route: dict[str, Any],
    evidence_events: list[dict[str, Any]] | dict[str, Any] | None = None,
    *,
    requested_role: str | None = None,
    observed_agent_address: str | None = None,
    observed_agent_config_digest: str | None = None,
    role_output_actor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    events: list[dict[str, Any]]
    if isinstance(evidence_events, dict):
        events = evidence_events.get("evidence_events", [])
    else:
        events = evidence_events or []

    mode = route.get("capability_mode", {}).get("mode")
    if mode != "enforced":
        return {"valid": True, "enforcement_claim": False}

    if requested_role and not observed_agent_address:
        return {"valid": False, "blocker_code": "E_ENFORCED_AGENT_MISSING"}
    if role_output_actor and not evidence_events:
        return {"valid": False, "blocker_code": "E_ENFORCED_IDENTITY_INVALID"}

    capability = route.get("capability_mode", {})
    validation_ids = capability.get("validation_evidence_ids")
    enforced_agent_set = capability.get("enforced_agent_set")
    if not isinstance(validation_ids, list) or not validation_ids or not all(isinstance(item, str) and item for item in validation_ids):
        return {"valid": False, "blocker_code": "E_ENFORCED_MODE_NOT_VALIDATED"}
    if not isinstance(enforced_agent_set, str) or not enforced_agent_set:
        return {"valid": False, "blocker_code": "E_ENFORCED_MODE_NOT_VALIDATED"}

    identity = None
    for event in reversed(events):
        if (
            event.get("id") in validation_ids
            and event.get("record_type") == "actor_identity"
            and event.get("status") == "pass"
            and event.get("claim") == "installed_agents_validated"
        ):
            identity = event
            break
    if not identity:
        return {"valid": False, "blocker_code": "E_ENFORCED_MODE_NOT_VALIDATED"}

    subject = identity.get("agent_config_subject", {})
    actor_identity = identity.get("actor_identity", {})
    if not isinstance(subject, dict) or not isinstance(actor_identity, dict):
        return {"valid": False, "blocker_code": "E_ENFORCED_MODE_NOT_VALIDATED"}
    agent_set_id = actor_identity.get("agent_set_id") or subject.get("agent_set_id")
    if agent_set_id != enforced_agent_set or subject.get("agent_set_id") != agent_set_id:
        return {"valid": False, "blocker_code": "E_ENFORCED_MODE_NOT_VALIDATED"}
    expires_at = actor_identity.get("expires_at")
    if not isinstance(expires_at, str) or not expires_at:
        return {"valid": False, "blocker_code": "E_ENFORCED_MODE_NOT_VALIDATED"}
    try:
        expires = _dt.datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return {"valid": False, "blocker_code": "E_ENFORCED_MODE_NOT_VALIDATED"}
    if expires <= _dt.datetime.now(_dt.timezone.utc):
        return {"valid": False, "blocker_code": "E_ENFORCED_MODE_NOT_VALIDATED"}

    raw_agents = actor_identity.get("agents")
    if not isinstance(raw_agents, list) or not raw_agents:
        return {"valid": False, "blocker_code": "E_ENFORCED_MODE_NOT_VALIDATED"}
    required_agent_fields = {"role", "address", "config_digest", "sandbox_mode", "model_policy", "tool_policy"}
    agents = {}
    for agent in raw_agents:
        if not isinstance(agent, dict) or any(not isinstance(agent.get(field), str) or not agent.get(field) for field in required_agent_fields):
            return {"valid": False, "blocker_code": "E_ENFORCED_MODE_NOT_VALIDATED"}
        agents[agent["role"]] = agent

    if observed_agent_config_digest and observed_agent_config_digest != subject.get("config_digest"):
        return {"valid": False, "blocker_code": "E_ENFORCED_AGENT_CONFIG_STALE"}

    if requested_role:
        agent = agents.get(requested_role)
        expected_addr = ENFORCED_ADDRESSES.get(requested_role)
        if not agent or agent.get("address") != expected_addr or (observed_agent_address and observed_agent_address != expected_addr):
            return {"valid": False, "blocker_code": "E_ENFORCED_AGENT_MISSING"}

    if role_output_actor:
        role = role_output_actor.get("role")
        agent = agents.get(role)
        if (
            role_output_actor.get("mode") != "enforced"
            or not agent
            or role_output_actor.get("agent_address") != agent.get("address")
            or role_output_actor.get("agent_set_id") != agent_set_id
            or role_output_actor.get("config_digest") != agent.get("config_digest")
            or not role_output_actor.get("session_id")
        ):
            return {"valid": False, "blocker_code": "E_ENFORCED_IDENTITY_INVALID"}

    return {"valid": True}


def validate_role_output(request: dict[str, Any], role_output: dict[str, Any]) -> dict[str, Any]:
    if role_output.get("schema_version") != ROLE_OUTPUT:
        return {"valid": False, "code": "E_ROLE_OUTPUT_SCHEMA_INVALID"}
    if role_output.get("dispatch_id") != request.get("dispatch_id"):
        return {"valid": False, "code": "E_DISPATCH_ID_MISMATCH"}
    if role_output.get("work_item_id") != request.get("work_item_id"):
        return {"valid": False, "code": "E_DISPATCH_SUBJECT_MISMATCH"}
    outcome = role_output.get("outcome")
    if outcome not in {"success", "blocked", "repair_needed", "reroute", "cannot_judge", "manual_continuation"}:
        return {"valid": False, "code": "E_ROLE_OUTPUT_OUTCOME_INVALID"}
    if outcome not in {"repair_needed", "cannot_judge"} and role_output.get("stage") != request.get("stage"):
        return {"valid": False, "code": "E_DISPATCH_SUBJECT_MISMATCH"}
    if outcome == "blocked" and not role_output.get("blockers"):
        return {"valid": False, "code": "E_BLOCKER_REQUIRED"}
    if outcome in {"reroute", "repair_needed"} and not role_output.get("reroute"):
        return {"valid": False, "code": "E_REROUTE_REQUIRED"}
    return {"valid": True, "outcome": outcome}


def route_card_command(request: dict[str, Any]) -> dict[str, Any]:
    validate_request(request, "route-card")
    operation = request["operation"]
    path = safe_route_card_path(request)
    payload = request["input"]

    if operation == "create":
        route = payload.get("route_card")
        if not isinstance(route, dict):
            raise_invalid("input.route_card is required", "/input/route_card")
        if route.get("work_item_id") != request.get("work_item_id"):
            return response(request, ok=False, status="invalid_input", errors=[error("E_ROUTE_CARD_WORK_ITEM_MISMATCH", "route card work_item_id must match request work_item_id", field_path="/input/route_card/work_item_id")])
        errors = validate_route_card(route)
        if errors:
            return response(request, ok=False, status="invalid_input", errors=errors)
        atomic_write(path, json.dumps(route, indent=2, sort_keys=True) + "\n")
        return response(request, ok=True, status="pass", result={"route_card_path": str(path), "digest": digest_json(route)})

    if operation in {"validate", "status", "render"}:
        route = payload.get("route_card") if isinstance(payload.get("route_card"), dict) else load_route_card_for_request(request)
        if route.get("work_item_id") != request.get("work_item_id"):
            return response(request, ok=False, status="invalid_input", errors=[error("E_ROUTE_CARD_WORK_ITEM_MISMATCH", "route card work_item_id must match request work_item_id", field_path="/work_item_id")])
        events = payload.get("evidence_events", [])
        errors = validate_route_card(route, install_events=events if isinstance(events, list) else [])
        if errors:
            return response(request, ok=False, status="invalid_input", errors=errors)
        if operation == "render":
            return response(request, ok=True, status="pass", result={"markdown": render_route_card(route), "digest": digest_json(route)})
        return response(request, ok=True, status="pass", result={"valid": True, "digest": digest_json(route), "current_stage": route.get("stage_plan", {}).get("current_stage")})

    if operation == "update":
        route = load_route_card_for_request(request)
        expected_digest = payload.get("expected_previous_digest")
        previous_digest = digest_json(route)
        if expected_digest != previous_digest:
            b = blocker("E_ROUTE_CARD_DIGEST_MISMATCH", "Route card digest does not match expected_previous_digest.", stage=route.get("stage_plan", {}).get("current_stage"), owner_role="orchestrator")
            return response(request, ok=False, status="blocked", blockers=[b], result={"previous_digest": previous_digest})
        updates = payload.get("set", {})
        if not isinstance(updates, dict):
            raise_invalid("input.set must be an object", "/input/set")
        policy_errors = validate_route_update_policy(route, updates, request)
        if policy_errors:
            return response(request, ok=False, status="blocked", blockers=policy_errors)
        updated = copy.deepcopy(route)
        for dotted, value in updates.items():
            set_dotted(updated, dotted, value)
        errors = validate_route_card(updated)
        if errors:
            return response(request, ok=False, status="invalid_input", errors=errors)
        new_digest = digest_json(updated)
        ledger_path = safe_ledger_path(request)
        audit_event = build_route_update_event(route, updated, request, updates, previous_digest, new_digest)
        event_errors = validate_event(audit_event)
        if event_errors:
            return response(request, ok=False, status="invalid_input", errors=event_errors)
        appended, ids, warnings = append_event(ledger_path, audit_event)
        atomic_write(path, json.dumps(updated, indent=2, sort_keys=True) + "\n")
        return response(request, ok=True, status="pass", evidence_ids=ids, warnings=warnings, result={"previous_digest": previous_digest, "new_digest": new_digest, "audit_appended": appended})

    raise_invalid(f"unsupported route-card operation: {operation}", "/operation")


def set_dotted(obj: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    target = obj
    for part in parts[:-1]:
        if part not in target or not isinstance(target[part], dict):
            target[part] = {}
        target = target[part]
    target[parts[-1]] = value


def get_dotted(obj: dict[str, Any], dotted: str) -> Any:
    target: Any = obj
    for part in dotted.split("."):
        if not isinstance(target, dict) or part not in target:
            return None
        target = target[part]
    return target


def validate_route_update_policy(route: dict[str, Any], updates: dict[str, Any], request: dict[str, Any]) -> list[dict[str, Any]]:
    caller = request.get("caller", {})
    role = caller.get("role")
    stage = route.get("stage_plan", {}).get("current_stage")
    blockers: list[dict[str, Any]] = []
    immutable = {
        "work_item_id",
        "source.request",
        "subject.base_ref",
        "subject.head_ref",
        "capability_mode.mode",
    }
    human_prefixes = ("intent.", "delivery_authority.", "capability_mode.", "source.links")
    orchestrator_prefixes = (
        "stage_plan.current_stage",
        "stage_plan.lifecycle_state",
        "stage_plan.repair_loop_budget",
        "stage_plan.escalation_policy",
        "subject.expected_head_sha",
        "subject.review_diff",
        "evidence.",
        "repo.updated_at",
    )
    for field in updates:
        if field in immutable:
            blockers.append(blocker("E_ROUTE_CARD_IMMUTABLE_FIELD", f"{field} is immutable after route-card creation.", stage=stage, owner_role="human", requires_human=True, field_path=field))
            continue
        if field.startswith("delivery_authority.") or field.startswith("intent.") or field.startswith("capability_mode."):
            if role != "human":
                blockers.append(blocker("E_ROUTE_CARD_UPDATE_UNAUTHORIZED", f"{field} requires human authorization.", stage=stage, owner_role="human", requires_human=True, field_path=field))
            continue
        if field.startswith(orchestrator_prefixes) or field in orchestrator_prefixes:
            if role not in {"orchestrator", "human"}:
                blockers.append(blocker("E_ROUTE_CARD_UPDATE_UNAUTHORIZED", f"{field} requires orchestrator or human authorization.", stage=stage, owner_role="orchestrator", field_path=field))
            continue
        if field.startswith(human_prefixes):
            if role != "human":
                blockers.append(blocker("E_ROUTE_CARD_UPDATE_UNAUTHORIZED", f"{field} requires human authorization.", stage=stage, owner_role="human", requires_human=True, field_path=field))
            continue
        blockers.append(blocker("E_ROUTE_CARD_UPDATE_UNSUPPORTED_FIELD", f"{field} is not an allowed route-card update field.", stage=stage, owner_role="orchestrator", field_path=field))
    if not request.get("ledger_path"):
        blockers.append(blocker("E_ROUTE_UPDATE_AUDIT_REQUIRED", "route-card update requires ledger_path for route_update audit evidence.", stage=stage, owner_role="orchestrator"))
    return blockers


def build_route_update_event(
    route: dict[str, Any],
    updated: dict[str, Any],
    request: dict[str, Any],
    updates: dict[str, Any],
    previous_digest: str,
    new_digest: str,
) -> dict[str, Any]:
    stage = route.get("stage_plan", {}).get("current_stage", "plan")
    reason = request["input"].get("reason")
    if not isinstance(reason, str) or not reason.strip():
        reason = "route-card update"
    return {
        "schema_version": EVIDENCE,
        "id": request["input"].get("route_update_event_id") or f"ev_route_update_{hashlib.sha1((request['request_id'] + new_digest).encode()).hexdigest()[:12]}",
        "work_item_id": route["work_item_id"],
        "stage_attempt_id": request["input"].get("stage_attempt_id") or f"{route['work_item_id']}:{stage}:attempt-1",
        "record_type": "route_update",
        "stage": stage,
        "actor": request["caller"],
        "recorded_by": {"role": "orchestrator", "mode": "assisted"} if request["caller"].get("role") != "human" else request["caller"],
        "identity_strength": "system" if request["caller"].get("role") == "orchestrator" else "human_verified",
        "claim": "route_card_updated",
        "subject_scope": "audit",
        "status": "pass",
        "route_update": {
            "field_paths": sorted(updates.keys()),
            "previous_values": {field: get_dotted(route, field) for field in updates},
            "new_values": {field: get_dotted(updated, field) for field in updates},
            "reason": reason,
            "previous_route_card_digest": previous_digest,
            "new_route_card_digest": new_digest,
            "authorized_by": request["caller"],
        },
        "tool_version": TOOL_VERSION,
        "created_at": now_iso(),
    }


def render_route_card(route: dict[str, Any]) -> str:
    intent = route.get("intent", {})
    stage_plan = route.get("stage_plan", {})
    lines = [
        f"# Codex Bandit Route Card: {route.get('work_item_id')}",
        "",
        f"- Current stage: `{stage_plan.get('current_stage')}`",
        f"- Lifecycle: `{stage_plan.get('lifecycle_state')}`",
        f"- Capability mode: `{route.get('capability_mode', {}).get('mode')}`",
        "",
        "## Problem",
        intent.get("problem", ""),
        "",
        "## Acceptance Criteria",
    ]
    lines.extend(f"- {item}" for item in intent.get("acceptance_criteria", []))
    return "\n".join(lines) + "\n"


def evidence_ledger_command(request: dict[str, Any]) -> dict[str, Any]:
    validate_request(request, "evidence-ledger")
    operation = request["operation"]
    route = load_route_card_for_request(request)
    ledger_path = safe_ledger_path(request)
    payload = request["input"]

    if operation == "append":
        event = payload.get("event")
        if not isinstance(event, dict):
            raise_invalid("input.event is required", "/input/event")
        event = stamp_event_subject_if_needed(event, route, repo_root_from_request(request))
        errors = validate_event(event)
        if errors:
            return response(request, ok=False, status="invalid_input", errors=errors)
        if event.get("work_item_id") != route.get("work_item_id"):
            return response(request, ok=False, status="invalid_input", errors=[error("E_EVIDENCE_WORK_ITEM_MISMATCH", "event work_item_id must match route card", field_path="/input/event/work_item_id")])
        b = authority_blocker(route, event)
        if b:
            return response(request, ok=False, status="blocked", blockers=[b])
        appended, ids, warnings = append_event(ledger_path, event)
        return response(request, ok=True, status="pass", evidence_ids=ids, warnings=warnings, result={"appended": appended})

    if operation == "status":
        events, malformed = read_ledger(ledger_path)
        target_stage = request.get("stage") or route.get("stage_plan", {}).get("current_stage")
        reduced = reduce_stage(route, events, target_stage, jsonl_lines=malformed)
        status = response_status_from_reducer(reduced)
        return response_from_reducer(request, reduced, status)

    if operation in {"supersede", "transition"}:
        event = payload.get("event") or build_audit_event(route, request, operation)
        errors = validate_event(event)
        if errors:
            return response(request, ok=False, status="invalid_input", errors=errors)
        if event.get("work_item_id") != route.get("work_item_id"):
            return response(request, ok=False, status="invalid_input", errors=[error("E_EVIDENCE_WORK_ITEM_MISMATCH", "event work_item_id must match route card", field_path="/input/event/work_item_id")])
        b = authority_blocker(route, event)
        if b:
            return response(request, ok=False, status="blocked", blockers=[b])
        appended, ids, warnings = append_event(ledger_path, event)
        return response(request, ok=True, status="pass", evidence_ids=ids, warnings=warnings, result={"appended": appended})

    raise_invalid(f"unsupported evidence-ledger operation: {operation}", "/operation")


def stamp_event_subject_if_needed(event: dict[str, Any], route: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    event = copy.deepcopy(event)
    if event.get("record_type") == "command" and event.get("subject_scope") == "product":
        head = git_head(repo_root)
        if not head:
            raise ScriptFailure(
                "blocked",
                "E_GIT_HEAD_UNAVAILABLE",
                "Cannot stamp command evidence without an actual git HEAD.",
                blockers=[blocker("E_GIT_HEAD_UNAVAILABLE", "Cannot stamp command evidence without an actual git HEAD.", stage=event.get("stage"), owner_role="orchestrator")],
            )
        dirty = git_is_dirty(repo_root)
        if dirty is None:
            raise ScriptFailure(
                "blocked",
                "E_GIT_HEAD_UNAVAILABLE",
                "Cannot verify worktree cleanliness before stamping command evidence.",
                blockers=[blocker("E_GIT_HEAD_UNAVAILABLE", "Cannot verify worktree cleanliness before stamping command evidence.", stage=event.get("stage"), owner_role="orchestrator")],
            )
        policy = route.get("subject", {}).get("dirty_state_policy", "block")
        if dirty and policy == "block":
            raise ScriptFailure(
                "stale",
                "E_DIRTY_WORKTREE",
                "Dirty worktree blocks command evidence stamping.",
                blockers=[blocker("E_DIRTY_WORKTREE", "Dirty worktree blocks command evidence stamping.", stage=event.get("stage"), owner_role="orchestrator")],
            )
        subject = dict(event.get("subject") or {})
        subject.setdefault("base_ref", route.get("subject", {}).get("base_ref"))
        subject.setdefault("head_ref", route.get("subject", {}).get("head_ref"))
        subject["head_sha"] = head
        if dirty:
            diff_digest = git_diff_digest(repo_root)
            if diff_digest:
                subject["diff_digest"] = diff_digest
        event["subject"] = subject
    return event


def build_audit_event(route: dict[str, Any], request: dict[str, Any], operation: str) -> dict[str, Any]:
    payload = request["input"]
    stage = request.get("stage") or route.get("stage_plan", {}).get("current_stage", "plan")
    event_id = payload.get("id") or f"ev_{operation}_{hashlib.sha1(now_iso().encode()).hexdigest()[:10]}"
    event = {
        "schema_version": EVIDENCE,
        "id": event_id,
        "work_item_id": route["work_item_id"],
        "stage_attempt_id": payload.get("stage_attempt_id") or f"{route['work_item_id']}:{stage}:attempt-1",
        "record_type": "supersession" if operation == "supersede" else "transition",
        "stage": stage,
        "actor": request["caller"],
        "recorded_by": request["caller"],
        "identity_strength": "system" if request["caller"].get("role") == "orchestrator" else "declared",
        "claim": payload.get("claim") or operation,
        "subject_scope": "audit",
        "status": "superseded" if operation == "supersede" else payload.get("status", "pass"),
        "tool_version": TOOL_VERSION,
        "created_at": now_iso(),
    }
    if operation == "supersede":
        event["supersedes"] = payload.get("supersedes", [])
    else:
        event["transition"] = payload.get("transition", {})
    return event


def verify_stage_command(request: dict[str, Any]) -> dict[str, Any]:
    validate_request(request, "verify-stage")
    if request["operation"] != "verify":
        raise_invalid("verify-stage operation must be verify", "/operation")
    if os.environ.get("CODEX_BANDIT_TEST_RUNTIME_ERROR") == "1" and request["input"].get("force_runtime_error"):
        raise RuntimeError("forced runtime failure")
    route = load_route_card_for_request(request)
    route_errors = validate_route_card(route)
    if route_errors:
        return response(request, ok=False, status="invalid_input", errors=route_errors)
    events, malformed = read_ledger(safe_ledger_path(request))
    stage = request.get("stage") or route.get("stage_plan", {}).get("current_stage")
    if not stage:
        raise_invalid("stage is required", "/stage")
    reduced = reduce_stage(route, events, stage, jsonl_lines=malformed)
    status = response_status_from_reducer(reduced)
    return response_from_reducer(request, reduced, status)


def response_status_from_reducer(reduced: dict[str, Any]) -> str:
    status = reduced["status"]
    if status == "not_started":
        return "blocked"
    if status in STATUSES:
        return status
    return "blocked"


def response_from_reducer(request: dict[str, Any], reduced: dict[str, Any], status: str) -> dict[str, Any]:
    blockers = list(reduced.get("blockers", []))
    if reduced["status"] == "not_started":
        blockers.append(blocker("E_STAGE_NOT_STARTED", "Stage has no active evidence yet.", stage=reduced["stage"], owner_role=STAGE_OWNER.get(reduced["stage"])))
    if reduced["status"] == "stale" and not any(item.get("code") == "E_STALE_SUBJECT" for item in blockers):
        blockers.append(blocker("E_STALE_SUBJECT", "Evidence is stale for the requested stage.", stage=reduced["stage"], owner_role=STAGE_OWNER.get(reduced["stage"])))
    return response(
        request,
        ok=reduced["status"] == "pass",
        status=status,
        evidence_ids=reduced.get("active_evidence_ids", []),
        blockers=blockers,
        warnings=reduced.get("warnings", []),
        result={key: value for key, value in reduced.items() if key not in {"ok", "work_item_id", "stage", "status", "blockers", "warnings"}},
        work_item_id=reduced.get("work_item_id"),
        stage=reduced.get("stage"),
    )


def review_package_command(request: dict[str, Any]) -> dict[str, Any]:
    validate_request(request, "review-package")
    operation = request["operation"]
    route = load_route_card_for_request(request)
    payload = request["input"]
    if operation == "build":
        ledger_path = request.get("ledger_path")
        events: list[dict[str, Any]] = []
        if isinstance(ledger_path, str):
            request_with_ledger = dict(request)
            events, _ = read_ledger(safe_ledger_path(request_with_ledger))
        diff, diff_digest = git_review_diff(repo_root_from_request(request), route)
        package = {
            "schema_version": "codex-bandit.review-package.v1",
            "work_item_id": route["work_item_id"],
            "subject": route.get("subject", {}),
            "route_card_digest": digest_json(route),
            "evidence_ids": [event.get("id") for event in events if event.get("id")],
            "diff": diff,
            "diff_digest": diff_digest,
            "built_at": now_iso(),
        }
        output_path = payload.get("output_path") or route.get("commands", {}).get("review_package", {}).get("report_path")
        if output_path:
            path = safe_repo_relative_path(repo_root_from_request(request), output_path, "/input/output_path")
            atomic_write(path, json.dumps(package, indent=2, sort_keys=True) + "\n")
            package["path"] = str(path)
        digest = digest_json(package)
        package["digest"] = digest
        return response(request, ok=True, status="pass", result={"review_package": package, "digest": digest})

    if operation == "validate":
        package = payload.get("review_package")
        if package is None:
            package_path = payload.get("path")
            if not isinstance(package_path, str):
                raise_invalid("input.review_package or input.path is required", "/input")
            package = load_json_file(safe_repo_relative_path(repo_root_from_request(request), package_path, "/input/path"), "/input/path")
        if not isinstance(package, dict) or package.get("schema_version") != "codex-bandit.review-package.v1":
            return response(request, ok=False, status="invalid_input", errors=[error("E_REVIEW_PACKAGE_INVALID", "Review package schema is invalid.")])
        return response(request, ok=True, status="pass", result={"valid": True, "digest": digest_json(package)})

    raise_invalid(f"unsupported review-package operation: {operation}", "/operation")


def run(command: str) -> int:
    request, parse_error = read_request()
    if parse_error:
        return emit(response(None, ok=False, status="invalid_input", errors=[error("E_SCHEMA_INVALID", parse_error)]))
    try:
        if command == "route-card":
            resp = route_card_command(request)
        elif command == "evidence-ledger":
            resp = evidence_ledger_command(request)
        elif command == "verify-stage":
            resp = verify_stage_command(request)
        elif command == "review-package":
            resp = review_package_command(request)
        else:
            raise RuntimeError(f"unknown command {command}")
        return emit(resp)
    except ScriptFailure as exc:
        return emit(
            response(
                request,
                ok=False,
                status=exc.status,
                blockers=exc.blockers,
                errors=exc.errors or ([error(exc.code, exc.message)] if exc.status in {"invalid_input", "runtime_error"} else []),
                warnings=exc.warnings,
                result=exc.result,
            )
        )
    except Exception as exc:
        return emit(
            response(
                request,
                ok=False,
                status="runtime_error",
                errors=[error("E_RUNTIME_FAILURE", str(exc))],
            )
        )


__all__ = [
    "blocker",
    "digest_json",
    "false_enforcement_claim",
    "reduce_stage",
    "response",
    "run",
    "validate_delivery_blocker",
    "validate_enforced_mode",
    "validate_hitl_approval",
    "validate_role_output",
    "validate_route_card",
    "validate_verdict",
]
