# Release Readiness Checklist

Release scope: Claude Code native surface.

| Surface | Ships? | Validation |
| --- | --- | --- |
| Assisted orchestration | Yes | `run_orchestrate_checks.py` passes 13 scenario groups. |
| Manual stage skills | Yes | `run_stage_skill_checks.py` passes prompt, rubric, role-output, and dispatch checks. |
| Claude-native role agents | Yes | Agent frontmatter and stage role contract checks pass. |
| Hooks | Yes | Claude `SessionStart` advisory hook is validated and non-blocking. |
| MCP | Yes | Plugin validation and persistent stdio tool-list checks pass. |
| Delivery HITL | Yes | HITL, remote-head, CI, deploy, health, and untrusted-comment fixtures pass. |

## Required Commands

```sh
python3 tests/run_fixture_checks.py
python3 tests/run_orchestrate_checks.py
python3 tests/run_stage_skill_checks.py
python3 tests/validate_claude_plugin.py
claude plugin validate ./claude
claude plugin validate .
```

## Verdict

Release readiness: pass for the Claude Code native surface, with documented v1
limits.

Codex-only TOML agent installation and Git hook installation are intentionally
not duplicated; Claude Code uses native plugin agents and lifecycle hooks.

Unsupported or limited claims:

- Claude agent frontmatter does not claim durable role isolation or enforced
  capability mode.
- Deploy contracts are presence-checked only.
- MCP host discovery/loading is not exercised beyond plugin validation and the
  persistent stdio protocol test.
- The SessionStart hook never blocks Claude Code.
- Delivery monitoring is limited to supplied operation-time remote state and
  configured health-check result.
