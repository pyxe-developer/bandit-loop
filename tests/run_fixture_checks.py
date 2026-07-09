#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from bandit_runtime import (  # noqa: E402
    false_enforcement_claim,
    reduce_stage,
    validate_delivery_blocker,
    validate_enforced_mode,
    validate_hitl_approval,
    validate_role_output,
    validate_route_card,
    validate_verdict,
)
from delivery_governance import evaluate_land_deploy, prepare_pr_result  # noqa: E402


class FixtureError(AssertionError):
    pass


def load_fixture_file(name: str):
    return json.loads((ROOT / "references" / "fixtures" / name).read_text(encoding="utf-8"))


def assert_true(condition, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise FixtureError(f"{message}: expected {expected!r}, got {actual!r}")


def fixture_names() -> set[str]:
    manifest = load_fixture_file("fixture-manifest.json")
    assert_equal(manifest["status"], "materialized", "fixture manifest status")
    return {entry["name"] for entry in manifest["fixtures"]}


def route_card_base() -> dict:
    return copy.deepcopy(load_fixture_file("route-cards.json")["valid"][1]["route_card"])


def route_for_evidence(fixture: dict) -> dict:
    route = route_card_base()
    if fixture["name"] == "fixture_02b_adversarial_changes_requested_then_repair":
        route["subject"]["expected_head_sha"] = "cccccccccccccccccccccccccccccccccccccccc"
    return route


def check_route_cards(covered: set[str]) -> int:
    data = load_fixture_file("route-cards.json")
    count = 0
    for fixture in data["valid"]:
        errors = validate_route_card(fixture["route_card"])
        assert_equal(errors, [], fixture["name"])
        covered.add(fixture["name"])
        count += 1
    for fixture in data["invalid"]:
        errors = validate_route_card(fixture["route_card"])
        text = "\n".join(error.get("message", "") for error in errors)
        for expected in fixture["expected_errors"]:
            assert_true(expected in text, f"{fixture['name']} missing expected error {expected!r}; got {text!r}")
        covered.add(fixture["name"])
        count += 1
    return count


def check_expected_subset(name: str, actual: dict, expected: dict) -> None:
    if "status" in expected:
        assert_equal(actual.get("status"), expected["status"], f"{name} status")
    if "stage" in expected:
        assert_equal(actual.get("stage"), expected["stage"], f"{name} stage")
    if "active_evidence_ids" in expected:
        assert_equal(actual.get("active_evidence_ids"), expected["active_evidence_ids"], f"{name} active evidence")
    if "inactive_evidence_ids" in expected:
        assert_equal(actual.get("inactive_evidence_ids"), expected["inactive_evidence_ids"], f"{name} inactive evidence")
    if "delivery_state" in expected:
        assert_equal(actual.get("delivery_state"), expected["delivery_state"], f"{name} delivery state")
    if expected.get("blockers"):
        codes = [item.get("code") for item in actual.get("blockers", [])]
        for item in expected["blockers"]:
            assert_true(item["code"] in codes, f"{name} missing blocker {item['code']}; got {codes}")
    if expected.get("warnings"):
        codes = [item.get("code") for item in actual.get("warnings", [])]
        for item in expected["warnings"]:
            assert_true(item["code"] in codes, f"{name} missing warning {item['code']}; got {codes}")
    if "attempt" in expected:
        for key, value in expected["attempt"].items():
            assert_equal(actual.get("attempt", {}).get(key), value, f"{name} attempt.{key}")


def check_evidence_reducer(covered: set[str]) -> int:
    data = load_fixture_file("evidence-reducer.json")
    count = 0
    for fixture in data["fixtures"]:
        expected = fixture["expected"]
        route = route_for_evidence(fixture)
        stage = expected.get("stage") or "red"
        actual = reduce_stage(route, fixture.get("events", []), stage, jsonl_lines=fixture.get("jsonl_lines"))
        check_expected_subset(fixture["name"], actual, expected)
        covered.add(fixture["name"])
        count += 1
    return count


def init_git_repo(tmp: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
    subprocess.run(["git", "config", "user.email", "bandit@example.test"], cwd=tmp, check=True)
    subprocess.run(["git", "config", "user.name", "Codex Bandit"], cwd=tmp, check=True)
    (tmp / "src").mkdir()
    (tmp / "tests").mkdir()
    (tmp / "src" / "invoice.ts").write_text("export const total = 1;\n", encoding="utf-8")
    (tmp / "tests" / "invoice.test.ts").write_text("test('invoice', () => {});\n", encoding="utf-8")
    subprocess.run(["git", "add", "src", "tests"], cwd=tmp, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=tmp, check=True)
    subprocess.run(["git", "branch", "-M", "main"], cwd=tmp, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", "codex-bandit/cb-123"], cwd=tmp, check=True)
    (tmp / "src" / "invoice.ts").write_text("export const total = 2;\n", encoding="utf-8")
    subprocess.run(["git", "add", "src/invoice.ts"], cwd=tmp, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "head"], cwd=tmp, check=True)


def write_workdir(tmp: Path, route: dict, events: list[dict]) -> None:
    work = tmp / ".codex-bandit" / "work" / route["work_item_id"]
    work.mkdir(parents=True, exist_ok=True)
    (work / "route-card.json").write_text(json.dumps(route, indent=2) + "\n", encoding="utf-8")
    (work / "evidence.jsonl").write_text(
        "".join(json.dumps(event, separators=(",", ":")) + "\n" for event in events),
        encoding="utf-8",
    )


def run_script(tmp: Path, request: dict, command: str | None = None, env: dict[str, str] | None = None) -> tuple[int, dict]:
    request = copy.deepcopy(request)
    request["repo_root"] = str(tmp)
    script = command or request["command"]
    proc_env = None
    if env:
        proc_env = {**os.environ, **env}
    proc = subprocess.run(
        [str(ROOT / "scripts" / script)],
        input=json.dumps(request),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(ROOT),
        env=proc_env,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise FixtureError(f"script did not emit JSON: exit={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}") from exc
    return proc.returncode, payload


def events_by_name(name: str) -> list[dict]:
    fixtures = {item["name"]: item for item in load_fixture_file("evidence-reducer.json")["fixtures"]}
    return copy.deepcopy(fixtures[name]["events"])


def script_events_for(name: str) -> tuple[dict, list[dict]]:
    route = route_card_base()
    if name == "fixture_02c_script_success_verify_green":
        events = events_by_name("fixture_02b_multi_commit_red_green_active")[:2]
    elif name == "fixture_02c_script_predicate_failure_forbidden_path":
        events = events_by_name("fixture_02b_multi_commit_red_green_active")[:2]
        events[-1]["files_changed"] = ["tests/invoice.test.ts"]
    elif name == "fixture_02c_script_drift_blocker":
        events = events_by_name("fixture_02b_green_stale_head")
    elif name == "fixture_02c_script_runtime_failure_no_partial_append":
        events = events_by_name("fixture_02b_multi_commit_red_green_active")[:2]
    else:
        events = events_by_name("fixture_02b_multi_commit_red_green_active")[:2]
    return route, events


def check_script_envelopes(covered: set[str]) -> int:
    data = load_fixture_file("script-envelopes.json")
    count = 0
    for fixture in data["fixtures"]:
        request = copy.deepcopy(fixture["request"])
        route, events = script_events_for(fixture["name"])
        if fixture["name"] == "fixture_02c_script_invalid_input_bad_schema":
            request["schema_version"] = "bad"
        if fixture["name"] == "fixture_02c_script_runtime_failure_no_partial_append":
            request["input"]["force_runtime_error"] = True
        with tempfile.TemporaryDirectory(prefix="codex-bandit-fixture-") as td:
            tmp = Path(td)
            init_git_repo(tmp)
            write_workdir(tmp, route, events)
            env = {"CODEX_BANDIT_TEST_RUNTIME_ERROR": "1"} if fixture["name"] == "fixture_02c_script_runtime_failure_no_partial_append" else None
            exit_code, payload = run_script(tmp, request, env=env)
        expected = fixture["response"]
        assert_equal(exit_code, fixture["process_exit_code"], f"{fixture['name']} exit code")
        assert_equal(payload.get("schema_version"), "codex-bandit.script-response.v1", f"{fixture['name']} response schema")
        assert_equal(payload.get("ok"), expected["ok"], f"{fixture['name']} ok")
        assert_equal(payload.get("status"), expected["status"], f"{fixture['name']} status")
        for expected_blocker in expected.get("blockers", []):
            codes = [item.get("code") for item in payload.get("blockers", [])]
            assert_true(expected_blocker["code"] in codes, f"{fixture['name']} missing blocker {expected_blocker['code']}")
        for expected_error in expected.get("errors", []):
            codes = [item.get("code") for item in payload.get("errors", [])]
            assert_true(expected_error["code"] in codes, f"{fixture['name']} missing error {expected_error['code']}")
        covered.add(fixture["name"])
        count += 1
    return count


def check_stage_dispatch(covered: set[str]) -> int:
    data = load_fixture_file("stage-dispatch.json")
    count = 0
    for fixture in data["fixtures"]:
        result = validate_role_output(fixture["request"], fixture["role_output"])
        assert_true(result["valid"], f"{fixture['name']} invalid role output: {result}")
        covered.add(fixture["name"])
        count += 1
    return count


def check_verdict_delivery(covered: set[str]) -> int:
    data = load_fixture_file("verdict-delivery.json")
    count = 0
    for fixture in data["fixtures"]:
        name = fixture["name"]
        if "verdict" in fixture:
            result = validate_verdict(fixture["verdict"])
            if "expected_errors" in fixture:
                assert_true(not result["valid"], f"{name} should be invalid")
                expected_text = "\n".join(fixture["expected_errors"])
                assert_true(
                    result["message"] in expected_text or expected_text in result["message"],
                    f"{name} expected errors do not include {result['message']}",
                )
            else:
                assert_true(result["valid"], f"{name} verdict invalid: {result}")
                assert_equal(result["status"], fixture["expected"]["status"], f"{name} status")
                if "owner_roles" in fixture["expected"]:
                    owners = {finding["owner_role"] for finding in fixture["verdict"].get("findings", []) + fixture["verdict"].get("test_surface_findings", [])}
                    assert_equal(sorted(owners), sorted(fixture["expected"]["owner_roles"]), f"{name} owner roles")
        elif "evidence_event" in fixture and fixture["evidence_event"].get("record_type") == "approval":
            route = route_card_base()
            if name == "fixture_02d_invalid_hitl_unreviewed_head_sha":
                route["subject"]["expected_head_sha"] = fixture["remote_pr_head_sha"]
            result = validate_hitl_approval(
                route,
                fixture["evidence_event"],
                last_active_adversarial_head=fixture["last_active_adversarial_head"],
                remote_pr_head_sha=fixture["remote_pr_head_sha"],
            )
            if fixture["expected"]["delivery_state"] == "merge_approved":
                assert_true(result["valid"], f"{name} should be valid: {result}")
            else:
                assert_true(not result["valid"], f"{name} should block")
                assert_equal(result["code"], fixture["expected"]["blocker_code"], f"{name} blocker code")
        elif "evidence_event" in fixture:
            assert_equal(fixture["evidence_event"]["status"], "deferred", f"{name} deferred status")
        elif "delivery_blocker" in fixture:
            result = validate_delivery_blocker(fixture["delivery_blocker"])
            for key, value in fixture["expected"].items():
                assert_equal(result.get(key), value, f"{name} {key}")
        elif "delivery_scenario" in fixture:
            scenario = fixture["delivery_scenario"]
            route = route_card_base()
            route["stage_plan"]["current_stage"] = scenario.get("stage", "land_deploy")
            route["evidence"]["review_package"] = {"digest": "sha256:reviewpkg", "diff_digest": "sha256:diff", "path": ".codex-bandit/work/cb-123/reports/review-package.json"}
            if scenario.get("deploy_contract"):
                route["delivery_authority"]["deploy_contract"] = scenario["deploy_contract"]
            if "allow_deploy" in scenario:
                route["delivery_authority"]["allow_deploy"] = scenario["allow_deploy"]
            if scenario.get("expected_head_sha"):
                route["subject"]["expected_head_sha"] = scenario["expected_head_sha"]
            if scenario["operation"] == "prepare_pr":
                result = prepare_pr_result(route, scenario.get("local") or {})
            else:
                events = events_by_name("fixture_02b_multi_commit_red_green_active")
                if scenario.get("include_hitl", True):
                    hitl = copy.deepcopy(next(item for item in data["fixtures"] if item["name"] == "fixture_02d_hitl_merge_approval_valid")["evidence_event"])
                    if scenario.get("approval_head_sha"):
                        hitl["approval"]["head_sha"] = scenario["approval_head_sha"]
                        hitl["subject"]["head_sha"] = scenario["approval_head_sha"]
                    if scenario.get("approval_pr_number"):
                        hitl["approval"]["pr_number"] = scenario["approval_pr_number"]
                    events.append(hitl)
                result = evaluate_land_deploy(route, events, scenario.get("remote") or {}, now=scenario.get("now"))
            expected = fixture["expected"]
            if "status" in expected:
                assert_equal(result.get("status"), expected["status"], f"{name} status")
            if "delivery_state" in expected:
                assert_equal(result.get("delivery_state"), expected["delivery_state"], f"{name} delivery_state")
            if "blocker_code" in expected:
                codes = [item.get("code") for item in result.get("blockers", [])]
                assert_true(expected["blocker_code"] in codes, f"{name} missing blocker {expected['blocker_code']}: {codes}")
            if "terminal" in expected:
                assert_equal(result.get("terminal"), expected["terminal"], f"{name} terminal")
            if "merge_allowed" in expected:
                assert_equal(result.get("merge_allowed"), expected["merge_allowed"], f"{name} merge_allowed")
            if "deploy_allowed" in expected:
                assert_equal(result.get("deploy_allowed"), expected["deploy_allowed"], f"{name} deploy_allowed")
            if expected.get("untrusted_remote_inputs"):
                assert_true(all(item.get("treated_as_untrusted") and item.get("instruction_effect") == "none" for item in result.get("untrusted_remote_inputs", [])), f"{name} remote inputs not untrusted")
        covered.add(name)
        count += 1
    return count


def check_enforced_compatibility(covered: set[str]) -> int:
    data = load_fixture_file("enforced-compatibility.json")
    count = 0
    for fixture in data["fixtures"]:
        name = fixture["name"]
        if "claim" in fixture:
            invalid = false_enforcement_claim(fixture["claim"])
            assert_equal(not invalid, fixture["expected"]["valid"], f"{name} false enforcement claim")
        else:
            result = validate_enforced_mode(
                fixture["route_card"],
                fixture.get("evidence_events", []),
                requested_role=fixture.get("requested_role"),
                observed_agent_address=fixture.get("observed_agent_address"),
                observed_agent_config_digest=fixture.get("observed_agent_config_digest"),
                role_output_actor=fixture.get("role_output_actor"),
            )
            assert_equal(result["valid"], fixture["expected"]["valid"], f"{name} valid")
            if not fixture["expected"]["valid"]:
                assert_equal(result.get("blocker_code"), fixture["expected"]["blocker_code"], f"{name} blocker")
        covered.add(name)
        count += 1
    return count


def install_agent_request(agent_home: Path, operation: str, *, input_value: dict | None = None) -> dict:
    req = request_base("install-agents", operation)
    stub = agent_home.parent / "codex-stub"
    if not stub.exists():
        stub.write_text("#!/usr/bin/env sh\nprintf '%s\\n' 'codex-cli 0.137.0'\n", encoding="utf-8")
        stub.chmod(0o755)
    req["input"] = {
        "agent_home": str(agent_home),
        "model": "gpt-5.5",
        "codex_cli_path": str(stub),
        "installed_by": "fixture",
        **(input_value or {}),
    }
    return req


def install_valid_agents(tmp: Path, agent_home: Path) -> dict:
    req = install_agent_request(agent_home, "install", input_value={"approval": "INSTALL codex-bandit agents"})
    payload = assert_script(tmp, req, exit_code=0, status="pass", command="install-agents")
    assert_true(payload["result"].get("installed"), "install-agents installed flag missing")
    return payload


def validate_agents(tmp: Path, agent_home: Path, *, input_value: dict | None = None, exit_code: int = 0, status: str = "pass", blocker_code: str | None = None) -> dict:
    req = install_agent_request(agent_home, "validate", input_value=input_value)
    return assert_script(tmp, req, exit_code=exit_code, status=status, command="install-agents", blocker_code=blocker_code)


def assert_enforced_route_blocks_without_validation(tmp: Path, blocker_code: str = "E_ENFORCED_MODE_NOT_VALIDATED") -> None:
    route = route_card_base()
    route["capability_mode"] = {
        "mode": "enforced",
        "validation_evidence_ids": ["ev_install_agents_fixture"],
        "enforced_agent_set": "codex-bandit-agents-v1",
    }
    write_workdir(tmp, route, [])
    req = request_base("route-card", "status")
    req["input"] = {"route_card": route, "evidence_events": []}
    payload = assert_script(tmp, req, exit_code=2, status="invalid_input", command="route-card", error_code=blocker_code)
    assert_true(not payload["ok"], "enforced route card passed without validation evidence")


def assert_route_card_status_for_event(tmp: Path, event: dict, *, validation_ids: list[str], agent_set: str, exit_code: int, status: str, error_code: str | None = None) -> dict:
    route = route_card_base()
    route["capability_mode"] = {
        "mode": "enforced",
        "validation_evidence_ids": validation_ids,
        "enforced_agent_set": agent_set,
    }
    write_workdir(tmp, route, [])
    req = request_base("route-card", "status")
    req["input"] = {"route_card": route, "evidence_events": [event]}
    return assert_script(tmp, req, exit_code=exit_code, status=status, command="route-card", error_code=error_code)


def manifest_path(agent_home: Path) -> Path:
    return agent_home / ".codex-bandit-agents-manifest.json"


def load_install_manifest(agent_home: Path) -> dict:
    return json.loads(manifest_path(agent_home).read_text(encoding="utf-8"))


def write_install_manifest(agent_home: Path, manifest: dict) -> None:
    manifest_path(agent_home).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def skipped_paths(payload: dict) -> dict[str, str]:
    return {item["path"]: item["reason"] for item in payload["result"].get("skipped", [])}


def check_install_agents(covered: set[str]) -> int:
    data = load_fixture_file("install-agents.json")
    count = 0
    for fixture in data["fixtures"]:
        name = fixture["name"]
        scenario = fixture["scenario"]
        expected = fixture["expected"]
        with tempfile.TemporaryDirectory(prefix="codex-bandit-install-agents-") as td:
            tmp = Path(td).resolve()
            agent_home = tmp / "agents"
            if scenario == "plan":
                req = install_agent_request(agent_home, "plan")
                payload = assert_script(tmp, req, exit_code=0, status=expected["status"], command="install-agents")
                plan = payload["result"]["plan"]
                assert_equal(len(plan["managed_paths"]), expected["managed_path_count"], f"{name} managed path count")
                assert_equal(len(plan["policy_changes"]), expected["managed_path_count"], f"{name} policy count")
                assert_equal(plan["approval_required"], expected["approval_required"], f"{name} approval")
                assert_true(all(Path(path).name.startswith("codex-bandit.") for path in plan["managed_paths"]), f"{name} paths not exact namespaced agent files")
            elif scenario == "install_without_approval":
                req = install_agent_request(agent_home, "install")
                assert_script(tmp, req, exit_code=1, status=expected["status"], command="install-agents", blocker_code=expected["blocker_code"])
                assert_true(not agent_home.exists(), f"{name} mutated agent_home without approval")
            elif scenario == "installed":
                install_valid_agents(tmp, agent_home)
                validation = validate_agents(tmp, agent_home)
                event = validation["result"]["validation_evidence"]
                route_status = assert_route_card_status_for_event(tmp, event, validation_ids=[event["id"]], agent_set="codex-bandit-agents-v1", exit_code=0, status="pass")
                assert_equal(route_status["result"]["valid"], expected["route_card_enforced_valid"], f"{name} route enforced valid")
                assert_enforced_route_blocks_without_validation(tmp)
            elif scenario == "missing":
                install_valid_agents(tmp, agent_home)
                (agent_home / "codex-bandit.test-writer.toml").unlink()
                validate_agents(tmp, agent_home, exit_code=1, status=expected["status"], blocker_code=expected["blocker_code"])
                assert_enforced_route_blocks_without_validation(tmp)
            elif scenario == "drifted":
                install_valid_agents(tmp, agent_home)
                target = agent_home / "codex-bandit.adversarial-reviewer.toml"
                target.write_text(target.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
                validate_agents(tmp, agent_home, exit_code=1, status=expected["status"], blocker_code=expected["blocker_code"])
                assert_enforced_route_blocks_without_validation(tmp)
            elif scenario == "non_invocable":
                install_valid_agents(tmp, agent_home)
                validate_agents(
                    tmp,
                    agent_home,
                    input_value={"codex_cli_path": str(tmp / "missing-codex")},
                    exit_code=1,
                    status=expected["status"],
                    blocker_code=expected["blocker_code"],
                )
                assert_enforced_route_blocks_without_validation(tmp)
            elif scenario == "uninstall_safety":
                install_valid_agents(tmp, agent_home)
                unrelated = agent_home / "user-owned-agent.toml"
                unrelated.write_text('name = "user-owned-agent"\n', encoding="utf-8")
                req = install_agent_request(agent_home, "uninstall", input_value={"approval": "UNINSTALL codex-bandit agents"})
                payload = assert_script(tmp, req, exit_code=0, status=expected["status"], command="install-agents")
                assert_true(unrelated.exists() == expected["unrelated_file_preserved"], f"{name} unrelated file preservation")
                assert_true(not any((agent_home / filename).exists() for filename in [
                    "codex-bandit.issue-planner.toml",
                    "codex-bandit.test-writer.toml",
                    "codex-bandit.code-writer.toml",
                    "codex-bandit.adversarial-reviewer.toml",
                    "codex-bandit.prepare-pr.toml",
                    "codex-bandit.land-and-deploy.toml",
                    "codex-bandit.closeout-retro.toml",
                ]), f"{name} plugin agent files remain after uninstall")
                second = assert_script(tmp, req, exit_code=0, status=expected["second_uninstall_status"], command="install-agents")
                assert_true(second["result"].get("idempotent"), f"{name} second uninstall not idempotent")
                assert_true(unrelated.exists(), f"{name} unrelated file removed on second uninstall")
            elif scenario == "expired_validation_evidence":
                install_valid_agents(tmp, agent_home)
                validation = validate_agents(tmp, agent_home)
                event = validation["result"]["validation_evidence"]
                event["actor_identity"]["expires_at"] = "2000-01-01T00:00:00Z"
                assert_route_card_status_for_event(tmp, event, validation_ids=[event["id"]], agent_set="codex-bandit-agents-v1", exit_code=2, status=expected["status"], error_code=expected["error_code"])
            elif scenario == "wrong_agent_set":
                install_valid_agents(tmp, agent_home)
                validation = validate_agents(tmp, agent_home)
                event = validation["result"]["validation_evidence"]
                assert_route_card_status_for_event(tmp, event, validation_ids=[event["id"]], agent_set="codex-bandit-agents-v2", exit_code=2, status=expected["status"], error_code=expected["error_code"])
            elif scenario == "wrong_validation_evidence_id":
                install_valid_agents(tmp, agent_home)
                validation = validate_agents(tmp, agent_home)
                event = validation["result"]["validation_evidence"]
                assert_route_card_status_for_event(tmp, event, validation_ids=["ev_install_agents_dangling"], agent_set="codex-bandit-agents-v1", exit_code=2, status=expected["status"], error_code=expected["error_code"])
            elif scenario == "uninstall_manifest_tamper":
                install_valid_agents(tmp, agent_home)
                outside = tmp / "outside-user-agent.toml"
                outside.write_text('name = "outside-user-agent"\n', encoding="utf-8")
                manifest = load_install_manifest(agent_home)
                manifest["managed_paths"].append(str(outside))
                write_install_manifest(agent_home, manifest)
                req = install_agent_request(agent_home, "uninstall", input_value={"approval": "UNINSTALL codex-bandit agents"})
                payload = assert_script(tmp, req, exit_code=0, status=expected["status"], command="install-agents")
                assert_true(outside.exists() == expected["outside_file_preserved"], f"{name} outside file preservation")
                assert_equal(skipped_paths(payload).get(str(outside)), expected["skip_reason"], f"{name} skip reason")
                assert_true(manifest_path(agent_home).exists() == expected["manifest_retained"], f"{name} manifest retention")
            elif scenario == "uninstall_drifted_managed":
                install_valid_agents(tmp, agent_home)
                target = agent_home / "codex-bandit.adversarial-reviewer.toml"
                target.write_text(target.read_text(encoding="utf-8") + "\n# user drift\n", encoding="utf-8")
                req = install_agent_request(agent_home, "uninstall", input_value={"approval": "UNINSTALL codex-bandit agents"})
                payload = assert_script(tmp, req, exit_code=0, status=expected["status"], command="install-agents")
                assert_true(target.exists() == expected["drifted_file_retained"], f"{name} drifted file retention")
                assert_equal(skipped_paths(payload).get(str(target)), expected["skip_reason"], f"{name} skip reason")
                assert_true(manifest_path(agent_home).exists() == expected["manifest_retained"], f"{name} manifest retention")
            elif scenario == "uninstall_symlinked_managed":
                install_valid_agents(tmp, agent_home)
                outside = tmp / "outside-precious.txt"
                outside.write_text("keep me\n", encoding="utf-8")
                link = agent_home / "codex-bandit.code-writer.toml"
                link.unlink()
                os.symlink(outside, link)
                req = install_agent_request(agent_home, "uninstall", input_value={"approval": "UNINSTALL codex-bandit agents"})
                payload = assert_script(tmp, req, exit_code=0, status=expected["status"], command="install-agents")
                assert_true(outside.exists() == expected["outside_file_preserved"], f"{name} outside target preservation")
                assert_equal(outside.read_text(encoding="utf-8"), "keep me\n", f"{name} outside target content")
                assert_equal(skipped_paths(payload).get(str(link)), expected["skip_reason"], f"{name} skip reason")
                assert_true(manifest_path(agent_home).exists() == expected["manifest_retained"], f"{name} manifest retention")
            else:
                raise FixtureError(f"unknown install-agents scenario {scenario}")
        covered.add(name)
        count += 1
    return count


def install_hook_request(operation: str, *, input_value: dict | None = None) -> dict:
    req = request_base("install-git-hooks", operation)
    req["input"] = {"installed_by": "fixture", **(input_value or {})}
    return req


def install_valid_hooks(tmp: Path) -> dict:
    req = install_hook_request("install", input_value={"approval": "INSTALL codex-bandit git hooks"})
    payload = assert_script(tmp, req, exit_code=0, status="pass", command="install-git-hooks")
    assert_true(payload["result"].get("installed"), "install-git-hooks installed flag missing")
    return payload


def hook_manifest_path(tmp: Path) -> Path:
    return tmp / ".git" / "hooks" / ".codex-bandit-hooks-manifest.json"


def load_hook_manifest(tmp: Path) -> dict:
    return json.loads(hook_manifest_path(tmp).read_text(encoding="utf-8"))


def write_hook_manifest(tmp: Path, manifest: dict) -> None:
    hook_manifest_path(tmp).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def check_hooks_mcp(covered: set[str]) -> int:
    data = load_fixture_file("hooks-mcp.json")
    count = 0
    for fixture in data["fixtures"]:
        name = fixture["name"]
        scenario = fixture["scenario"]
        expected = fixture["expected"]
        with tempfile.TemporaryDirectory(prefix="codex-bandit-hooks-mcp-") as td:
            tmp = Path(td).resolve()
            init_git_repo(tmp)
            if scenario == "hook_plan":
                req = install_hook_request("plan")
                payload = assert_script(tmp, req, exit_code=0, status=expected["status"], command="install-git-hooks")
                plan = payload["result"]["plan"]
                assert_equal(len(plan["managed_paths"]), expected["managed_path_count"], f"{name} managed path count")
                assert_equal(plan["approval_required"], expected["approval_required"], f"{name} approval")
                assert_true(any(path.endswith(".git/hooks/pre-commit") for path in plan["managed_paths"]), f"{name} missing pre-commit path")
                assert_true(any(path.endswith(".git/hooks/pre-push") for path in plan["managed_paths"]), f"{name} missing pre-push path")
                assert_true(any(path.endswith(".codex-bandit/hooks/session-start") for path in plan["managed_paths"]), f"{name} missing session-start path")
                assert_true(all(not item["blocking_default"] for item in plan["files"]), f"{name} hooks are not advisory by default")
                assert_true(not (tmp / ".git" / "hooks" / "pre-commit").exists(), f"{name} plan mutated pre-commit")
            elif scenario == "hook_install_without_approval":
                req = install_hook_request("install")
                assert_script(tmp, req, exit_code=1, status=expected["status"], command="install-git-hooks", blocker_code=expected["blocker_code"])
                assert_true(not (tmp / ".git" / "hooks" / "pre-commit").exists(), f"{name} mutated without approval")
            elif scenario == "hook_user_conflict":
                user_hook = tmp / ".git" / "hooks" / "pre-commit"
                user_hook.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
                req = install_hook_request("install", input_value={"approval": "INSTALL codex-bandit git hooks"})
                assert_script(tmp, req, exit_code=1, status=expected["status"], command="install-git-hooks", blocker_code=expected["blocker_code"])
                assert_equal(user_hook.read_text(encoding="utf-8"), "#!/usr/bin/env sh\nexit 0\n", f"{name} user hook preservation")
            elif scenario == "hook_uninstall":
                install_valid_hooks(tmp)
                hook_paths = [
                    tmp / ".git" / "hooks" / "pre-commit",
                    tmp / ".git" / "hooks" / "pre-push",
                    tmp / ".codex-bandit" / "hooks" / "session-start",
                ]
                assert_true(all(path.exists() for path in hook_paths), f"{name} installed hook missing")
                assert_true(all(os.access(path, os.X_OK) for path in hook_paths), f"{name} installed hook not executable")
                req = install_hook_request("uninstall", input_value={"approval": "UNINSTALL codex-bandit git hooks"})
                assert_script(tmp, req, exit_code=0, status=expected["status"], command="install-git-hooks")
                assert_true(not any(path.exists() for path in hook_paths), f"{name} plugin hook files remain after uninstall")
                second = assert_script(tmp, req, exit_code=0, status=expected["second_uninstall_status"], command="install-git-hooks")
                assert_true(second["result"].get("idempotent"), f"{name} second uninstall not idempotent")
            elif scenario == "hook_missing_state_advisory":
                install_valid_hooks(tmp)
                hook_paths = [
                    tmp / ".git" / "hooks" / "pre-commit",
                    tmp / ".git" / "hooks" / "pre-push",
                    tmp / ".codex-bandit" / "hooks" / "session-start",
                ]
                for hook_path in hook_paths:
                    proc = subprocess.run(
                        [str(hook_path)],
                        input="",
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        cwd=str(tmp),
                    )
                    assert_equal(proc.returncode, expected["exit_code"], f"{name} {hook_path.name} advisory exit")
            elif scenario == "hook_blocking_stage_advisory_default":
                install_valid_hooks(tmp)
                route = route_card_base()
                route["stage_plan"]["current_stage"] = "green"
                write_workdir(tmp, route, events_by_name("fixture_02b_red_pass_active"))
                hook_path = tmp / ".git" / "hooks" / "pre-commit"
                default = subprocess.run(
                    [str(hook_path)],
                    input="",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=str(tmp),
                )
                assert_equal(default.returncode, expected["default_exit_code"], f"{name} advisory default exit")
                assert_true("E_STAGE_NOT_STARTED" in default.stderr, f"{name} advisory run did not report blocking-stage reducer output")
                blocking = subprocess.run(
                    [str(hook_path)],
                    input="",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=str(tmp),
                    env={**os.environ, "CODEX_BANDIT_HOOK_BLOCKING": "1"},
                )
                assert_equal(blocking.returncode, expected["blocking_exit_code"], f"{name} opt-in blocking exit")
                assert_true("E_STAGE_NOT_STARTED" in blocking.stderr, f"{name} blocking run did not report reducer blocker")
            elif scenario == "hook_uninstall_manifest_tamper":
                install_valid_hooks(tmp)
                outside = tmp / "outside-user-hook"
                outside.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
                manifest = load_hook_manifest(tmp)
                manifest["managed_paths"].append(str(outside))
                write_hook_manifest(tmp, manifest)
                req = install_hook_request("uninstall", input_value={"approval": "UNINSTALL codex-bandit git hooks"})
                payload = assert_script(tmp, req, exit_code=0, status=expected["status"], command="install-git-hooks")
                assert_true(outside.exists() == expected["outside_file_preserved"], f"{name} outside file preservation")
                assert_equal(skipped_paths(payload).get(str(outside)), expected["skip_reason"], f"{name} skip reason")
                assert_true(hook_manifest_path(tmp).exists() == expected["manifest_retained"], f"{name} manifest retention")
            elif scenario == "hook_uninstall_drifted_managed":
                install_valid_hooks(tmp)
                target = tmp / ".git" / "hooks" / "pre-commit"
                target.write_text(target.read_text(encoding="utf-8") + "\n# user drift\n", encoding="utf-8")
                req = install_hook_request("uninstall", input_value={"approval": "UNINSTALL codex-bandit git hooks"})
                payload = assert_script(tmp, req, exit_code=0, status=expected["status"], command="install-git-hooks")
                assert_true(target.exists() == expected["drifted_file_retained"], f"{name} drifted hook retention")
                assert_equal(skipped_paths(payload).get(str(target)), expected["skip_reason"], f"{name} skip reason")
                assert_true(hook_manifest_path(tmp).exists() == expected["manifest_retained"], f"{name} manifest retention")
            elif scenario == "hook_uninstall_symlinked_managed":
                install_valid_hooks(tmp)
                outside = tmp / "outside-precious-hook"
                outside.write_text("keep me\n", encoding="utf-8")
                link = tmp / ".git" / "hooks" / "pre-push"
                link.unlink()
                os.symlink(outside, link)
                req = install_hook_request("uninstall", input_value={"approval": "UNINSTALL codex-bandit git hooks"})
                payload = assert_script(tmp, req, exit_code=0, status=expected["status"], command="install-git-hooks")
                assert_true(outside.exists() == expected["outside_file_preserved"], f"{name} outside target preservation")
                assert_equal(outside.read_text(encoding="utf-8"), "keep me\n", f"{name} outside target content")
                assert_equal(skipped_paths(payload).get(str(link)), expected["skip_reason"], f"{name} skip reason")
                assert_true(hook_manifest_path(tmp).exists() == expected["manifest_retained"], f"{name} manifest retention")
            elif scenario == "mcp_verify_stage_parity":
                route = route_card_base()
                events = events_by_name("fixture_02b_multi_commit_red_green_active")[:2]
                write_workdir(tmp, route, events)
                req = request_base("verify-stage", "verify", stage="green")
                req["repo_root"] = str(tmp)
                request_json = json.dumps(req, separators=(",", ":"))
                direct = subprocess.run(
                    [str(ROOT / "scripts" / "verify-stage")],
                    input=request_json,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=str(ROOT),
                )
                wrapped = subprocess.run(
                    [str(ROOT / "mcp" / "codex_bandit_mcp.py"), "--call", expected["tool"]],
                    input=request_json,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=str(ROOT),
                )
                assert_equal(wrapped.returncode, direct.returncode, f"{name} exit parity")
                assert_equal(wrapped.stdout, direct.stdout, f"{name} stdout parity")
                assert_equal(wrapped.stderr, direct.stderr, f"{name} stderr parity")
            else:
                raise FixtureError(f"unknown hooks/MCP scenario {scenario}")
        covered.add(name)
        count += 1
    return count


def request_base(command: str, operation: str, *, stage: str | None = None) -> dict:
    req = {
        "schema_version": "codex-bandit.script-request.v1",
        "command": command,
        "operation": operation,
        "repo_root": ".",
        "work_item_id": "cb-123",
        "route_card_path": ".codex-bandit/work/cb-123/route-card.json",
        "ledger_path": ".codex-bandit/work/cb-123/evidence.jsonl",
        "input": {},
        "caller": {"role": "orchestrator", "mode": "assisted"},
        "request_id": f"req_{command}_{operation}",
    }
    if stage:
        req["stage"] = stage
    return req


def blocker_codes(payload: dict) -> list[str]:
    return [item.get("code") for item in payload.get("blockers", [])]


def error_codes(payload: dict) -> list[str]:
    return [item.get("code") for item in payload.get("errors", [])]


def assert_script(tmp: Path, request: dict, *, exit_code: int, status: str, command: str | None = None, blocker_code: str | None = None, error_code: str | None = None, env: dict[str, str] | None = None) -> dict:
    actual_exit, payload = run_script(tmp, request, command=command, env=env)
    assert_equal(actual_exit, exit_code, f"{request['request_id']} exit")
    assert_equal(payload.get("status"), status, f"{request['request_id']} status")
    if blocker_code:
        assert_true(blocker_code in blocker_codes(payload), f"{request['request_id']} missing blocker {blocker_code}: {payload}")
    if error_code:
        assert_true(error_code in error_codes(payload), f"{request['request_id']} missing error {error_code}: {payload}")
    return payload


def check_runtime_regressions() -> dict:
    checks = 0

    # 1. Path traversal and request/route-card ID mismatch.
    with tempfile.TemporaryDirectory(prefix="codex-bandit-path-") as td:
        tmp = Path(td)
        route = route_card_base()
        req = request_base("route-card", "create")
        req["work_item_id"] = "../../../../tmp/evil"
        req["route_card_path"] = ".codex-bandit/work/../../../../tmp/evil/route-card.json"
        req["input"] = {"route_card": route}
        assert_script(tmp, req, exit_code=2, status="invalid_input", command="route-card", error_code="E_SCHEMA_INVALID")
        assert_true(not (tmp / "evil" / "route-card.json").exists(), "traversal route-card write escaped work dir")
        checks += 1

    with tempfile.TemporaryDirectory(prefix="codex-bandit-mismatch-") as td:
        tmp = Path(td)
        route = route_card_base()
        route["work_item_id"] = "cb-999"
        req = request_base("route-card", "create")
        req["input"] = {"route_card": route}
        assert_script(tmp, req, exit_code=2, status="invalid_input", command="route-card", error_code="E_ROUTE_CARD_WORK_ITEM_MISMATCH")
        checks += 1

    # 2. GREEN not-started and superseded-green paths do not crash.
    with tempfile.TemporaryDirectory(prefix="codex-bandit-green-") as td:
        tmp = Path(td)
        init_git_repo(tmp)
        route = route_card_base()
        red = events_by_name("fixture_02b_red_pass_active")
        write_workdir(tmp, route, red)
        req = request_base("verify-stage", "verify", stage="green")
        assert_script(tmp, req, exit_code=1, status="blocked", blocker_code="E_STAGE_NOT_STARTED")
        checks += 1

    with tempfile.TemporaryDirectory(prefix="codex-bandit-green-sup-") as td:
        tmp = Path(td)
        init_git_repo(tmp)
        route = route_card_base()
        events = events_by_name("fixture_02b_multi_commit_red_green_active")[:2]
        supersession = {
            "schema_version": "codex-bandit.evidence.v1",
            "id": "ev_supersede_green_001",
            "work_item_id": "cb-123",
            "stage_attempt_id": "cb-123:green:attempt-1",
            "record_type": "supersession",
            "stage": "green",
            "actor": {"role": "orchestrator", "mode": "assisted"},
            "recorded_by": {"role": "orchestrator", "mode": "assisted"},
            "identity_strength": "system",
            "claim": "green superseded",
            "subject_scope": "audit",
            "status": "superseded",
            "supersedes": ["ev_green_001"],
            "tool_version": "0.1.0",
            "created_at": "2026-07-09T12:30:00Z",
        }
        write_workdir(tmp, route, events + [supersession])
        req = request_base("verify-stage", "verify", stage="green")
        assert_script(tmp, req, exit_code=1, status="blocked", blocker_code="E_STAGE_NOT_STARTED")
        checks += 1

    # 3. Reducer rejects inadmissible recording authority, stale adversarial heads, and land_deploy without prereqs.
    with tempfile.TemporaryDirectory(prefix="codex-bandit-authority-") as td:
        tmp = Path(td)
        init_git_repo(tmp)
        route = route_card_base()
        events = events_by_name("fixture_02b_red_pass_active")
        events[0]["recorded_by"] = {"role": "code_writer", "mode": "assisted"}
        write_workdir(tmp, route, events)
        req = request_base("verify-stage", "verify", stage="red")
        assert_script(tmp, req, exit_code=1, status="blocked", blocker_code="E_APPEND_AUTHORITY_INVALID")
        checks += 1

    with tempfile.TemporaryDirectory(prefix="codex-bandit-stale-adv-") as td:
        tmp = Path(td)
        init_git_repo(tmp)
        route = route_card_base()
        route["subject"]["expected_head_sha"] = "cccccccccccccccccccccccccccccccccccccccc"
        events = events_by_name("fixture_02b_multi_commit_red_green_active")
        write_workdir(tmp, route, events)
        req = request_base("verify-stage", "verify", stage="adversarial")
        assert_script(tmp, req, exit_code=3, status="stale", blocker_code="E_STALE_SUBJECT")
        checks += 1

    with tempfile.TemporaryDirectory(prefix="codex-bandit-land-") as td:
        tmp = Path(td)
        init_git_repo(tmp)
        route = route_card_base()
        land_event = {
            "schema_version": "codex-bandit.evidence.v1",
            "id": "ev_land_pass_001",
            "work_item_id": "cb-123",
            "stage_attempt_id": "cb-123:land_deploy:attempt-1",
            "record_type": "command",
            "stage": "land_deploy",
            "actor": {"role": "land_deploy", "mode": "assisted"},
            "recorded_by": {"role": "orchestrator", "mode": "assisted"},
            "identity_strength": "declared",
            "claim": "land_deploy_passed",
            "subject_scope": "product",
            "subject": {"base_ref": "main", "head_ref": "codex-bandit/cb-123", "head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
            "status": "pass",
            "command": {"name": "land_deploy", "argv": ["true"], "cwd": ".", "exit_code": 0},
            "tool_version": "0.1.0",
            "created_at": "2026-07-09T12:30:00Z",
        }
        write_workdir(tmp, route, [land_event])
        req = request_base("verify-stage", "verify", stage="land_deploy")
        assert_script(tmp, req, exit_code=3, status="blocked", blocker_code="E_ADVERSARIAL_APPROVAL_REQUIRED")
        checks += 1

    # 4. Route-card update authority and audit.
    with tempfile.TemporaryDirectory(prefix="codex-bandit-route-update-") as td:
        tmp = Path(td)
        init_git_repo(tmp)
        route = route_card_base()
        write_workdir(tmp, route, [])
        req = request_base("route-card", "update")
        req["input"] = {
            "expected_previous_digest": __import__("bandit_runtime").digest_json(route),
            "set": {"source.request": "mutated", "delivery_authority.allow_merge": True},
            "reason": "bad mutation",
        }
        assert_script(tmp, req, exit_code=1, status="blocked", command="route-card", blocker_code="E_ROUTE_CARD_IMMUTABLE_FIELD")
        unchanged = json.loads((tmp / ".codex-bandit/work/cb-123/route-card.json").read_text())
        assert_equal(unchanged["source"]["request"], route["source"]["request"], "blocked update left route card unchanged")
        assert_equal((tmp / ".codex-bandit/work/cb-123/evidence.jsonl").read_text(), "", "blocked update did not append audit")
        checks += 1

        req = request_base("route-card", "update")
        req["input"] = {
            "expected_previous_digest": __import__("bandit_runtime").digest_json(route),
            "set": {"stage_plan.current_stage": "green"},
            "reason": "advance to green",
            "route_update_event_id": "ev_route_update_regression",
        }
        payload = assert_script(tmp, req, exit_code=0, status="pass", command="route-card")
        assert_true("ev_route_update_regression" in payload["evidence_ids"], "route update returned audit evidence id")
        ledger = (tmp / ".codex-bandit/work/cb-123/evidence.jsonl").read_text()
        assert_true('"record_type":"route_update"' in ledger, "route update audit event appended")
        checks += 1

    # 5. Command append stamps from a real clean git head, and blocks missing/dirty git.
    with tempfile.TemporaryDirectory(prefix="codex-bandit-nongit-") as td:
        tmp = Path(td)
        route = route_card_base()
        write_workdir(tmp, route, [])
        event = events_by_name("fixture_02b_red_pass_active")[0]
        req = request_base("evidence-ledger", "append", stage="red")
        req["input"] = {"event": event}
        assert_script(tmp, req, exit_code=3, status="blocked", command="evidence-ledger", blocker_code="E_GIT_HEAD_UNAVAILABLE")
        checks += 1

    with tempfile.TemporaryDirectory(prefix="codex-bandit-dirty-") as td:
        tmp = Path(td)
        init_git_repo(tmp)
        route = route_card_base()
        write_workdir(tmp, route, [])
        (tmp / "src" / "invoice.ts").write_text("dirty\n", encoding="utf-8")
        event = events_by_name("fixture_02b_red_pass_active")[0]
        req = request_base("evidence-ledger", "append", stage="red")
        req["input"] = {"event": event}
        assert_script(tmp, req, exit_code=3, status="stale", command="evidence-ledger", blocker_code="E_DIRTY_WORKTREE")
        checks += 1

    with tempfile.TemporaryDirectory(prefix="codex-bandit-append-") as td:
        tmp = Path(td)
        init_git_repo(tmp)
        route = route_card_base()
        write_workdir(tmp, route, [])
        event = events_by_name("fixture_02b_red_pass_active")[0]
        req = request_base("evidence-ledger", "append", stage="red")
        req["input"] = {"event": event}
        assert_script(tmp, req, exit_code=0, status="pass", command="evidence-ledger")
        dup = assert_script(tmp, req, exit_code=0, status="pass", command="evidence-ledger")
        assert_true(any(w.get("code") == "W_DUPLICATE_IDEMPOTENT_APPEND" for w in dup.get("warnings", [])), "idempotent duplicate append warning")
        conflict = copy.deepcopy(req)
        conflict["input"]["event"]["claim"] = "conflicting_duplicate_payload"
        assert_script(tmp, conflict, exit_code=1, status="blocked", command="evidence-ledger", blocker_code="E_DUPLICATE_EVIDENCE_ID")
        checks += 1

    # 6. Review package includes a diff digest and adversarial pass enforces package binding.
    with tempfile.TemporaryDirectory(prefix="codex-bandit-reviewpkg-") as td:
        tmp = Path(td)
        init_git_repo(tmp)
        route = route_card_base()
        write_workdir(tmp, route, events_by_name("fixture_02b_multi_commit_red_green_active")[:2])
        req = request_base("review-package", "build", stage="adversarial")
        payload = assert_script(tmp, req, exit_code=0, status="pass", command="review-package")
        package = payload["result"]["review_package"]
        assert_true(package.get("diff_digest", "").startswith("sha256:"), "review package includes diff digest")
        assert_true("diff" in package, "review package includes diff content")
        route["evidence"]["review_package"] = {"digest": package["digest"]}
        events = events_by_name("fixture_02b_multi_commit_red_green_active")
        events[-1]["verdict"]["review_package_digest"] = "sha256:bogus"
        events[-1]["verdict"]["subject"]["review_package_digest"] = "sha256:bogus"
        write_workdir(tmp, route, events)
        req = request_base("verify-stage", "verify", stage="adversarial")
        assert_script(tmp, req, exit_code=1, status="blocked", blocker_code="E_REVIEW_PACKAGE_DIGEST_MISMATCH")
        checks += 1

    # 7. Invalid dispatch outputs are rejected.
    dispatch = load_fixture_file("stage-dispatch.json")["fixtures"][0]
    bad = copy.deepcopy(dispatch["role_output"])
    bad["dispatch_id"] = "wrong"
    result = validate_role_output(dispatch["request"], bad)
    assert_true(not result["valid"] and result["code"] == "E_DISPATCH_ID_MISMATCH", "invalid dispatch id rejected")
    bad = copy.deepcopy(dispatch["role_output"])
    bad["outcome"] = "blocked"
    bad["blockers"] = []
    result = validate_role_output(dispatch["request"], bad)
    assert_true(not result["valid"] and result["code"] == "E_BLOCKER_REQUIRED", "blocked output without blocker rejected")
    checks += 1

    # 8. Runtime-error backdoor is env-gated.
    with tempfile.TemporaryDirectory(prefix="codex-bandit-backdoor-") as td:
        tmp = Path(td)
        init_git_repo(tmp)
        route = route_card_base()
        events = events_by_name("fixture_02b_multi_commit_red_green_active")[:2]
        write_workdir(tmp, route, events)
        req = request_base("verify-stage", "verify", stage="green")
        req["input"]["force_runtime_error"] = True
        assert_script(tmp, req, exit_code=0, status="pass")
        checks += 1

    # 9. Ticket 07 public helper keeps invalid input distinct from runtime failure.
    proc = subprocess.run(
        [str(ROOT / "scripts" / "delivery-operation")],
        input="{bad json",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(ROOT),
    )
    payload = json.loads(proc.stdout)
    assert_equal(proc.returncode, 2, "delivery-operation malformed json exit")
    assert_equal(payload.get("status"), "invalid_input", "delivery-operation malformed json status")
    assert_true("E_SCHEMA_INVALID" in error_codes(payload), "delivery-operation malformed json error code")
    checks += 1

    # 10. Enforced mode must select the validation event named by the route card,
    # not any later passing installed_agents_validated event.
    with tempfile.TemporaryDirectory(prefix="codex-bandit-enforced-selection-") as td:
        tmp = Path(td).resolve()
        agent_home = tmp / "agents"
        install_valid_agents(tmp, agent_home)
        validation = validate_agents(tmp, agent_home)
        passing_not_named = validation["result"]["validation_evidence"]
        passing_not_named["id"] = "ev_install_agents_not_named"
        named_expired = copy.deepcopy(passing_not_named)
        named_expired["id"] = "ev_install_agents_named"
        named_expired["actor_identity"]["expires_at"] = "2000-01-01T00:00:00Z"
        route = route_card_base()
        route["capability_mode"] = {
            "mode": "enforced",
            "validation_evidence_ids": [named_expired["id"]],
            "enforced_agent_set": "codex-bandit-agents-v1",
        }
        write_workdir(tmp, route, [])
        req = request_base("route-card", "status")
        req["input"] = {"route_card": route, "evidence_events": [named_expired, passing_not_named]}
        assert_script(tmp, req, exit_code=2, status="invalid_input", command="route-card", error_code="E_ENFORCED_MODE_NOT_VALIDATED")
        checks += 1

    return {"runtime_regressions": checks}


def main() -> int:
    expected_names = fixture_names()
    covered: set[str] = set()
    counts = {
        "route_cards": check_route_cards(covered),
        "evidence_reducer": check_evidence_reducer(covered),
        "script_envelopes": check_script_envelopes(covered),
        "stage_dispatch": check_stage_dispatch(covered),
        "verdict_delivery": check_verdict_delivery(covered),
        "enforced_compatibility": check_enforced_compatibility(covered),
        "install_agents": check_install_agents(covered),
        "hooks_mcp": check_hooks_mcp(covered),
    }
    counts.update(check_runtime_regressions())
    missing = expected_names - covered
    extra = covered - expected_names
    assert_true(not missing, f"manifest fixtures not covered: {sorted(missing)}")
    assert_true(not extra, f"covered fixtures absent from manifest: {sorted(extra)}")
    print(json.dumps({"ok": True, "covered": len(covered), "counts": counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FixtureError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
