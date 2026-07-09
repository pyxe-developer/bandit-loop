# Subagent Dispatch Templates

Assisted mode passes the `codex-bandit.stage-dispatch-request.v1` object through
skills/prompts and treats role outputs as proposed evidence. Enforced mode uses
the same dispatch object, but addresses opt-in local Codex custom agents
installed by `scripts/install-agents`.

Plugin-packaged metadata does not install agents. `plugin.json` and
`agents/openai.yaml` are presentation surfaces only; they must not claim
sandbox, model, tool-policy, or role isolation.

## Installed-Agent Inventory

`scripts/install-agents install` writes these files under `~/.codex/agents/`
unless `input.agent_home` overrides the target for tests:

| Role ID | Installed agent address | File | Sandbox |
| --- | --- | --- | --- |
| `issue_planner` | `codex-bandit.issue-planner` | `codex-bandit.issue-planner.toml` | `workspace-write` |
| `test_writer` | `codex-bandit.test-writer` | `codex-bandit.test-writer.toml` | `workspace-write` |
| `code_writer` | `codex-bandit.code-writer` | `codex-bandit.code-writer.toml` | `workspace-write` |
| `adversarial_reviewer` | `codex-bandit.adversarial-reviewer` | `codex-bandit.adversarial-reviewer.toml` | `read-only` |
| `prepare_pr` | `codex-bandit.prepare-pr` | `codex-bandit.prepare-pr.toml` | `workspace-write` |
| `land_deploy` | `codex-bandit.land-and-deploy` | `codex-bandit.land-and-deploy.toml` | `workspace-write` |
| `closeout_retro` | `codex-bandit.closeout-retro` | `codex-bandit.closeout-retro.toml` | `workspace-write` |

The installer also writes
`~/.codex/agents/.codex-bandit-agents-manifest.json` as the uninstall ownership
record. The manifest is not runtime agent config and does not prove enforcement
by itself.

## Enforced Invocation Contract

Before any route card may use `capability_mode.mode=enforced`,
`scripts/install-agents validate` must pass and return an
`installed_agents_validated` actor-identity evidence event for
`codex-bandit-agents-v1`.

For an enforced role dispatch:

- Keep the dispatch schema and role output schema unchanged.
- Set `dispatch_request.capability_mode` to `enforced`.
- Address the local Codex custom agent by the installed agent address above.
- Provide the normal dispatch JSON as the role context.
- Require role output actor fields:
  `role`, `mode=enforced`, `agent_address`, `agent_set_id`, `config_digest`,
  and `session_id`.
- Reduce evidence before stage advancement using the normal reducer.

Fail closed when installed-agent validation evidence is missing, stale, drifted,
or not invocable by the current Codex runtime. The orchestrator must not silently
downgrade to assisted mode while recording `capability_mode.mode=enforced`.

## Assisted Invocation Contract

For assisted dispatch, keep using the public skills:
`plan-work-item`, `write-red-tests`, `implement-green`, `adversarial-gate`,
`prepare-pr`, `land-and-deploy`, and `closeout-retro`. Assisted role outputs use
declared actor identity and proposed evidence only.
