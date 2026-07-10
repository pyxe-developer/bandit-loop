#!/usr/bin/env python3
"""Generate durable, static epic dashboards from Bandit work-item state."""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from bandit_runtime import reduce_stage, validate_route_card


REQUEST_SCHEMA = "codex-bandit.dashboard-request.v1"
RESPONSE_SCHEMA = "codex-bandit.dashboard-response.v1"
MANIFEST_SCHEMA = "codex-bandit.epic.v1"
STAGES = ["plan", "red", "green", "adversarial", "prepare_pr", "hitl_merge_checkpoint", "land_deploy", "closeout"]
STAGE_LABELS = {
    "plan": "Plan",
    "red": "Red tests",
    "green": "Implementation",
    "adversarial": "Review",
    "prepare_pr": "Prepare PR",
    "hitl_merge_checkpoint": "Human approval",
    "land_deploy": "Land & deploy",
    "closeout": "Closeout",
}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class DashboardError(Exception):
    pass


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def safe_repo_root(raw: Any) -> Path:
    if not isinstance(raw, str) or not raw:
        raise DashboardError("repo_root is required")
    return Path(raw).expanduser().resolve()


def safe_id(raw: Any, label: str) -> str:
    if not isinstance(raw, str) or not ID_RE.fullmatch(raw):
        raise DashboardError(f"{label} must match {ID_RE.pattern}")
    return raw


def epic_dir(repo_root: Path, epic_id: str) -> Path:
    return repo_root / ".codex-bandit" / "epics" / epic_id


def manifest_path(repo_root: Path, epic_id: str) -> Path:
    return epic_dir(repo_root, epic_id) / "epic.json"


def dashboard_path(repo_root: Path, epic_id: str) -> Path:
    return epic_dir(repo_root, epic_id) / "dashboard.html"


def validate_manifest(value: Any, epic_id: str | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DashboardError("epic manifest must be an object")
    if value.get("schema_version") != MANIFEST_SCHEMA:
        raise DashboardError(f"epic manifest schema_version must be {MANIFEST_SCHEMA}")
    actual_id = safe_id(value.get("epic_id"), "epic_id")
    if epic_id is not None and actual_id != epic_id:
        raise DashboardError("epic manifest epic_id does not match its directory")
    if not isinstance(value.get("title"), str) or not value["title"].strip():
        raise DashboardError("epic title is required")
    work_item_ids = value.get("work_item_ids")
    if not isinstance(work_item_ids, list) or not work_item_ids:
        raise DashboardError("work_item_ids must be a non-empty array")
    clean_ids = [safe_id(item, "work_item_id") for item in work_item_ids]
    if len(clean_ids) != len(set(clean_ids)):
        raise DashboardError("work_item_ids must be unique")
    result = dict(value)
    result["title"] = value["title"].strip()
    result["work_item_ids"] = clean_ids
    description = value.get("description")
    if description is not None and not isinstance(description, str):
        raise DashboardError("description must be a string")
    return result


def read_manifest(repo_root: Path, epic_id: str) -> dict[str, Any]:
    path = manifest_path(repo_root, epic_id)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DashboardError(f"epic manifest does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DashboardError(f"epic manifest is not valid JSON: {path}") from exc
    return validate_manifest(value, epic_id)


def read_events(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    if not path.exists():
        return [], []
    lines = path.read_text(encoding="utf-8").splitlines()
    events: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            break
        if isinstance(value, dict):
            events.append(value)
    return events, lines


def work_item_summary(repo_root: Path, work_item_id: str) -> dict[str, Any]:
    work_dir = repo_root / ".codex-bandit" / "work" / work_item_id
    route_path = work_dir / "route-card.json"
    if not route_path.exists():
        return {
            "work_item_id": work_item_id,
            "title": work_item_id,
            "problem": "Route card has not been created yet.",
            "stage": "plan",
            "lifecycle": "planned",
            "status": "missing",
            "progress": 0,
            "blockers": ["Waiting for route card"],
            "updated_at": None,
            "enabled_stages": STAGES,
        }
    try:
        route = json.loads(route_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "work_item_id": work_item_id,
            "title": work_item_id,
            "problem": "Route card is invalid JSON.",
            "stage": "plan",
            "lifecycle": "blocked",
            "status": "invalid",
            "progress": 0,
            "blockers": ["Invalid route-card.json"],
            "updated_at": None,
            "enabled_stages": STAGES,
        }
    events, lines = read_events(work_dir / "evidence.jsonl")
    stage_plan = route.get("stage_plan") if isinstance(route.get("stage_plan"), dict) else {}
    stage = stage_plan.get("current_stage") if isinstance(stage_plan.get("current_stage"), str) else "plan"
    lifecycle = stage_plan.get("lifecycle_state") if isinstance(stage_plan.get("lifecycle_state"), str) else "planned"
    enabled = stage_plan.get("enabled_stages") if isinstance(stage_plan.get("enabled_stages"), list) else STAGES
    enabled = [item for item in STAGES if item in enabled] or STAGES
    route_errors = validate_route_card(route, install_events=events)
    blockers: list[str] = []
    reducer_status = "invalid" if route_errors else "not_started"
    if route_errors:
        blockers = [str(item.get("message") or item.get("code")) for item in route_errors[:3]]
    else:
        try:
            reduced = reduce_stage(route, events, stage, jsonl_lines=lines)
            reducer_status = str(reduced.get("status") or "not_started")
            blockers = [str(item.get("message") or item.get("code")) for item in reduced.get("blockers", [])[:3]]
        except Exception as exc:  # Dashboard failure must remain descriptive, never authoritative.
            reducer_status = "invalid"
            blockers = [f"Could not reduce stage: {exc}"]
    if lifecycle == "complete":
        status = "complete"
    elif lifecycle == "abandoned":
        status = "abandoned"
    elif reducer_status in {"blocked", "fail", "changes_requested", "cannot_judge", "stale", "invalid"}:
        status = reducer_status
    elif reducer_status == "pass":
        status = "ready"
    else:
        status = "active" if lifecycle in {"active", "repairing", "ready_for_review", "approved"} else lifecycle
    try:
        stage_index = enabled.index(stage)
    except ValueError:
        stage_index = 0
    progress = 100 if status == "complete" else round((stage_index / max(1, len(enabled))) * 100)
    source = route.get("source") if isinstance(route.get("source"), dict) else {}
    intent = route.get("intent") if isinstance(route.get("intent"), dict) else {}
    title = source.get("title") or intent.get("title") or source.get("request") or work_item_id
    problem = intent.get("problem") or source.get("request") or ""
    updated_at = None
    if events:
        updated_at = events[-1].get("created_at")
    if not updated_at:
        repo = route.get("repo") if isinstance(route.get("repo"), dict) else {}
        updated_at = repo.get("updated_at") or repo.get("created_at")
    return {
        "work_item_id": work_item_id,
        "title": str(title),
        "problem": str(problem),
        "stage": stage,
        "lifecycle": lifecycle,
        "status": status,
        "reducer_status": reducer_status,
        "progress": progress,
        "blockers": blockers,
        "updated_at": updated_at,
        "enabled_stages": enabled,
    }


def epic_summary(repo_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    items = [work_item_summary(repo_root, item) for item in manifest["work_item_ids"]]
    counts = {
        "total": len(items),
        "complete": sum(item["status"] == "complete" for item in items),
        "blocked": sum(item["status"] in {"blocked", "fail", "changes_requested", "cannot_judge", "stale", "invalid"} for item in items),
        "active": sum(item["status"] in {"active", "ready"} for item in items),
        "waiting": sum(item["status"] in {"planned", "missing"} for item in items),
    }
    progress = round(sum(item["progress"] for item in items) / max(1, len(items)))
    return {"manifest": manifest, "items": items, "counts": counts, "progress": progress}


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def render_html(summary: dict[str, Any], generated_at: str) -> str:
    manifest = summary["manifest"]
    counts = summary["counts"]
    rows: list[str] = []
    for item in summary["items"]:
        stage_cells: list[str] = []
        current_idx = item["enabled_stages"].index(item["stage"]) if item["stage"] in item["enabled_stages"] else 0
        for stage in item["enabled_stages"]:
            idx = item["enabled_stages"].index(stage)
            state = "done" if item["status"] == "complete" or idx < current_idx else ("current" if idx == current_idx else "future")
            stage_cells.append(f'<span class="step {state}" title="{esc(STAGE_LABELS[stage])}">{idx + 1}</span>')
        blocker_html = "".join(f"<li>{esc(message)}</li>" for message in item["blockers"])
        blocker_section = f'<ul class="blockers">{blocker_html}</ul>' if blocker_html else '<span class="quiet">No current blockers</span>'
        rows.append(
            f'''<article class="work-item status-{esc(item['status'])}">
  <div class="item-head"><div><span class="item-id">{esc(item['work_item_id'])}</span><h2>{esc(item['title'])}</h2></div><span class="status">{esc(item['status'].replace('_', ' '))}</span></div>
  <p class="problem">{esc(item['problem'])}</p>
  <div class="stage-row"><strong>{esc(STAGE_LABELS.get(item['stage'], item['stage']))}</strong><div class="pipeline">{''.join(stage_cells)}</div><span>{item['progress']}%</span></div>
  <div class="progress"><span style="width:{item['progress']}%"></span></div>
  <div class="item-foot"><div>{blocker_section}</div><span class="updated">Updated {esc(item['updated_at'] or 'unknown')}</span></div>
</article>'''
        )
    description = f'<p class="description">{esc(manifest.get("description"))}</p>' if manifest.get("description") else ""
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(manifest['title'])} · Bandit</title>
<style>
:root{{--bg:#0c1017;--panel:#151b25;--panel2:#1b2330;--text:#f4f7fb;--muted:#9ba8ba;--line:#2a3545;--blue:#62a8ff;--green:#4bd08b;--amber:#f0b85a;--red:#ff6b78}}
*{{box-sizing:border-box}} body{{margin:0;background:radial-gradient(circle at top right,#18263b 0,var(--bg) 42%);color:var(--text);font:15px/1.5 ui-sans-serif,system-ui,-apple-system,sans-serif;min-height:100vh}}
main{{max-width:1120px;margin:auto;padding:56px 24px 80px}} .eyebrow,.item-id{{text-transform:uppercase;letter-spacing:.13em;font-size:11px;font-weight:750;color:var(--blue)}}
h1{{font-size:clamp(34px,6vw,64px);line-height:1.02;margin:8px 0 12px;letter-spacing:-.045em}} .description{{color:var(--muted);max-width:720px;font-size:17px}}
.summary{{display:grid;grid-template-columns:2fr repeat(4,1fr);gap:12px;margin:32px 0}} .metric{{background:rgba(21,27,37,.86);border:1px solid var(--line);border-radius:16px;padding:18px}}
.metric b{{display:block;font-size:28px;letter-spacing:-.04em}} .metric span{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em}} .metric.primary b{{font-size:38px}}
.epic-progress,.progress{{height:7px;background:#273141;border-radius:99px;overflow:hidden}} .epic-progress{{margin-top:10px}} .epic-progress span,.progress span{{display:block;height:100%;background:linear-gradient(90deg,var(--blue),var(--green));border-radius:inherit}}
.items{{display:grid;gap:14px}} .work-item{{background:rgba(21,27,37,.9);border:1px solid var(--line);border-left:4px solid var(--blue);border-radius:16px;padding:20px;box-shadow:0 12px 40px rgba(0,0,0,.16)}}
.work-item.status-complete{{border-left-color:var(--green)}} .work-item.status-blocked,.work-item.status-fail,.work-item.status-stale,.work-item.status-invalid,.work-item.status-changes_requested,.work-item.status-cannot_judge{{border-left-color:var(--red)}} .work-item.status-missing,.work-item.status-planned{{border-left-color:var(--amber)}}
.item-head,.stage-row,.item-foot{{display:flex;align-items:center;justify-content:space-between;gap:18px}} h2{{font-size:20px;margin:3px 0 0}} .status{{border:1px solid var(--line);border-radius:99px;padding:5px 10px;color:var(--muted);white-space:nowrap;text-transform:capitalize}}
.problem{{color:var(--muted);margin:10px 0 18px}} .stage-row{{font-size:13px}} .pipeline{{display:flex;gap:6px;flex:1;justify-content:center}} .step{{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;background:#283243;color:#78869a;font-size:10px}} .step.done{{background:#214f3c;color:#7ae2aa}} .step.current{{background:#245287;color:#9dccff;outline:3px solid rgba(98,168,255,.12)}}
.progress{{margin:11px 0 16px}} .item-foot{{align-items:flex-end;color:var(--muted);font-size:12px}} .blockers{{color:#ff9da6;margin:0;padding-left:18px}} .quiet,.updated{{color:var(--muted)}} footer{{color:var(--muted);margin-top:24px;font-size:12px}}
@media(max-width:760px){{.summary{{grid-template-columns:repeat(2,1fr)}}.metric.primary{{grid-column:1/-1}}.item-head,.stage-row,.item-foot{{align-items:flex-start;flex-direction:column}}.pipeline{{justify-content:flex-start;flex-wrap:wrap}}}}
</style></head><body><main>
<header><div class="eyebrow">Bandit epic · {esc(manifest['epic_id'])}</div><h1>{esc(manifest['title'])}</h1>{description}</header>
<section class="summary"><div class="metric primary"><b>{summary['progress']}%</b><span>Epic progress</span><div class="epic-progress"><span style="width:{summary['progress']}%"></span></div></div><div class="metric"><b>{counts['complete']}</b><span>Complete</span></div><div class="metric"><b>{counts['active']}</b><span>Active</span></div><div class="metric"><b>{counts['blocked']}</b><span>Blocked</span></div><div class="metric"><b>{counts['waiting']}</b><span>Waiting</span></div></section>
<section class="items">{''.join(rows)}</section><footer>Generated {esc(generated_at)} from route cards and evidence ledgers. This dashboard is a projection, not workflow authority.</footer>
</main></body></html>'''


def render_epic(repo_root: Path, epic_id: str) -> dict[str, Any]:
    manifest = read_manifest(repo_root, epic_id)
    summary = epic_summary(repo_root, manifest)
    generated_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    path = dashboard_path(repo_root, epic_id)
    atomic_write(path, render_html(summary, generated_at))
    return {**summary, "dashboard_path": str(path), "generated_at": generated_at}


def upsert_epic(repo_root: Path, epic_id: str, input_value: dict[str, Any]) -> dict[str, Any]:
    existing: dict[str, Any] = {}
    path = manifest_path(repo_root, epic_id)
    if path.exists():
        existing = read_manifest(repo_root, epic_id)
    manifest = validate_manifest(
        {
            "schema_version": MANIFEST_SCHEMA,
            "epic_id": epic_id,
            "title": input_value.get("title", existing.get("title")),
            "description": input_value.get("description", existing.get("description")),
            "work_item_ids": input_value.get("work_item_ids", existing.get("work_item_ids")),
        },
        epic_id,
    )
    atomic_write(path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return render_epic(repo_root, epic_id)


def refresh_for_work_item(repo_root: Path, work_item_id: str) -> list[str]:
    paths: list[str] = []
    root = repo_root / ".codex-bandit" / "epics"
    if not root.exists():
        return paths
    for path in sorted(root.glob("*/epic.json")):
        try:
            manifest = validate_manifest(json.loads(path.read_text(encoding="utf-8")), path.parent.name)
            if work_item_id in manifest["work_item_ids"]:
                paths.append(render_epic(repo_root, manifest["epic_id"])["dashboard_path"])
        except (DashboardError, json.JSONDecodeError):
            continue
    return paths


def run_request(request: Any) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise DashboardError("request must be an object")
    if request.get("schema_version") != REQUEST_SCHEMA:
        raise DashboardError(f"schema_version must be {REQUEST_SCHEMA}")
    repo_root = safe_repo_root(request.get("repo_root"))
    epic_id = safe_id(request.get("epic_id"), "epic_id")
    operation = request.get("operation")
    input_value = request.get("input", {})
    if not isinstance(input_value, dict):
        raise DashboardError("input must be an object")
    if operation == "upsert":
        result = upsert_epic(repo_root, epic_id, input_value)
    elif operation == "render":
        result = render_epic(repo_root, epic_id)
    elif operation == "status":
        result = epic_summary(repo_root, read_manifest(repo_root, epic_id))
    else:
        raise DashboardError("operation must be upsert, render, or status")
    return {
        "schema_version": RESPONSE_SCHEMA,
        "request_id": request.get("request_id"),
        "ok": True,
        "status": "pass",
        "epic_id": epic_id,
        "result": result,
        "errors": [],
    }

