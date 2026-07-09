# Pressure Test Report

Release scope: full optional surface. Assisted mode, opt-in enforced mode,
opt-in hooks, MCP script wrappers, and delivery HITL all ship in this release.
No optional integration is deferred.

Run the report with:

```sh
python3 tests/run_pressure_report.py
```

The report runs `run_fixture_checks.py`, `run_orchestrate_checks.py`,
`run_stage_skill_checks.py`, and plugin validation.

## Final Suite Numbers

| Suite | Final result |
| --- | --- |
| `tests/run_fixture_checks.py` | pass, `covered=85`, `route_cards=8`, `evidence_reducer=11`, `script_envelopes=5`, `stage_dispatch=6`, `verdict_delivery=25`, `enforced_compatibility=7`, `install_agents=13`, `hooks_mcp=10`, `runtime_regressions=17` |
| `tests/run_orchestrate_checks.py` | pass, 13 scenario groups |
| `tests/run_stage_skill_checks.py` | pass, `rubric_sections=7`, `prompt_contracts=12`, `role_output_samples=11`, `stage_dispatch_fixtures=6`, `delivery_behavior=15` |
| Plugin validation | pass |

## Scenario Matrix

| Scenario | Expected result | Actual result |
| --- | --- | --- |
| Role-boundary violation | Inadmissible evidence blocks. | Passed: runtime regression covers `E_APPEND_AUTHORITY_INVALID`. |
| Stale evidence | Stale head/subject blocks with `E_STALE_SUBJECT`. | Passed: fixture and orchestrator stale-evidence checks. |
| Missing route-card fields | Invalid route cards fail closed with schema/stage errors. | Passed: route-card fixtures and blocked-route orchestrator check. |
| Manual patch | Product/test edits block until explicit scoped `manual_patch` authorization. | Passed: orchestrator manual-patch check. |
| Missing HITL approval | Merge remains blocked without exact PR/head SHA human approval. | Passed: delivery fixture and orchestrator check. |
| Failing CI or deploy health | Failing CI, failed deploy, or unhealthy post-deploy health blocks delivery. | Passed: delivery fixtures. |
| Untrusted PR comments | Remote comments are untrusted and have no instruction effect. | Passed: remote-comment fixture keeps CI blocker authoritative. |
| Enforced mode validation | `install-agents` validates TOML, digests, schema, selected evidence, and Codex CLI availability. | Passed: 13 install-agent fixtures. |
| Enforced installed-but-not-proven-loaded | Known limit: validation is not proof that Codex loaded or enforced named custom agents. | Documented: no non-interactive Codex named-agent list/dry-run is exercised. |
| Hooks advisory default | Reducer-blocking hook work exits 0 by default and exits non-zero only with `CODEX_BANDIT_HOOK_BLOCKING=1`. | Passed: Ticket 10 hook fixture. |
| Hook uninstall safety | Tampered manifest paths, drifted hooks, and symlinked managed paths are skipped and preserved. | Passed: three Ticket 10 hook uninstall fixtures. |
| MCP wrapper | MCP wrapper output matches direct script subprocess output. | Passed: parity fixture. Host MCP discovery/loading is not exercised. |
| Deploy contract completeness | Known v1 limit: a non-null deploy contract is enough; subfields are not validated. | Passed as a known-limit fixture: incomplete contract still deploys when remote deploy and health are pass. |

## Known Limits

- Enforced validation is `validated`, not proven loaded: it proves Codex CLI
  availability plus TOML/schema/digest checks. It does not prove the Codex
  runtime loaded or enforced the installed custom agents.
- Delivery deploy-contract validation is presence-only. It does not validate
  deploy command, health command, environment, timeout, or provider-specific
  subfields.
- MCP validation covers plugin-validator acceptance and subprocess parity only.
  It does not exercise host MCP discovery/loading.
- Hooks are advisory by default. Blocking hook mode is only active when the user
  explicitly sets `CODEX_BANDIT_HOOK_BLOCKING=1`.
- Delivery checks are bounded to supplied operation-time remote state and
  configured health-check results. There is no broad deploy monitoring.
