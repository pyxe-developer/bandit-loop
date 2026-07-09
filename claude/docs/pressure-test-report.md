# Pressure Test Report

Release scope: Claude Code native surface. Assisted mode, native plugin agents,
the SessionStart advisory hook, MCP script wrappers, and delivery HITL all ship
in this release.

Run the validation suite with:

```sh
python3 tests/validate_claude_plugin.py
```

The report runs `run_fixture_checks.py`, `run_orchestrate_checks.py`,
`run_stage_skill_checks.py`, and plugin validation.

## Final Suite Numbers

| Suite | Final result |
| --- | --- |
| `tests/run_fixture_checks.py` | pass, core fixtures covered; Codex-only installer and Git-hook fixtures skipped |
| `tests/run_orchestrate_checks.py` | pass, 13 scenario groups |
| `tests/run_stage_skill_checks.py` | pass, `rubric_sections=7`, `prompt_contracts=12`, `role_output_samples=11`, `stage_dispatch_fixtures=6`, `delivery_behavior=15` |
| `tests/validate_claude_plugin.py` | pass, packaging and persistent MCP stream |
| Claude plugin validation | pass |

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
| Native agent boundaries | Claude agent frontmatter exposes role-specific tools and prompts. | Passed: stage skill and packaging checks. |
| Capability claims | The Claude port remains assisted by default and does not claim durable role isolation. | Documented in the plugin README and dispatch contract. |
| SessionStart hook | Active work item status is reported without blocking Claude Code. | Passed: hook runner and plugin validation. |
| MCP wrapper | MCP server responds to multiple framed messages without waiting for EOF. | Passed: persistent stream test. |
| Deploy contract completeness | Known v1 limit: a non-null deploy contract is enough; subfields are not validated. | Passed as a known-limit fixture: incomplete contract still deploys when remote deploy and health are pass. |

## Known Limits

- Native Claude agent restrictions are configuration guidance and tool scoping;
  they do not prove durable role isolation.
- Delivery deploy-contract validation is presence-only. It does not validate
  deploy command, health command, environment, timeout, or provider-specific
  subfields.
- MCP validation covers plugin-validator acceptance and the persistent stdio
  protocol only. It does not exercise host MCP discovery/loading.
- The Claude SessionStart hook is advisory and never blocks by default.
- Delivery checks are bounded to supplied operation-time remote state and
  configured health-check results. There is no broad deploy monitoring.
