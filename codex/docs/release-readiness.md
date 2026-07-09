# Release Readiness Checklist

Release scope: full optional surface.

| Surface | Ships? | Validation |
| --- | --- | --- |
| Assisted orchestration | Yes | `run_orchestrate_checks.py` passes 13 scenario groups. |
| Manual stage skills | Yes | `run_stage_skill_checks.py` passes prompt, rubric, role-output, and dispatch checks. |
| Enforced mode opt-in | Yes | `install-agents` fixtures pass, with documented validated-not-proven-loaded limit. |
| Hooks | Yes | Hook install, advisory default, blocking opt-in, and uninstall safety fixtures pass. |
| MCP | Yes | Plugin validation passes and wrapper subprocess parity passes. |
| Delivery HITL | Yes | HITL, remote-head, CI, deploy, health, and untrusted-comment fixtures pass. |

## Required Commands

```sh
python3 tests/run_fixture_checks.py
python3 tests/run_orchestrate_checks.py
python3 tests/run_stage_skill_checks.py
/Library/Frameworks/Python.framework/Versions/3.11/bin/python3 /Users/matthewflebbe/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
python3 tests/run_pressure_report.py
```

## Verdict

Release readiness: pass for the full optional surface, with documented v1
limits.

No optional integrations are intentionally deferred in this release.

Unsupported or limited claims:

- Enforced mode validation does not prove Codex loaded/enforced named custom
  agents.
- Deploy contracts are presence-checked only.
- MCP host discovery/loading is not exercised beyond plugin validation and
  wrapper parity.
- Hooks do not block by default.
- Delivery monitoring is limited to supplied operation-time remote state and
  configured health-check result.
