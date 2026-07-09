# Subagent Dispatch Templates

Assisted mode passes the `codex-bandit.stage-dispatch-request.v1` object through
skills/prompts and treats role outputs as proposed evidence. Claude Code maps
the role prompts to native plugin agents in `agents/`, but this port does not
claim durable role isolation or Codex-style enforced mode.

Plugin-packaged metadata loads native agent frontmatter. The role prompts and
tool scopes must not claim durable sandbox, model, or role isolation beyond
what Claude Code actually configures.

## Native Agent Inventory

The plugin ships these Claude Code agents under `agents/`:

| Role ID | Installed agent address | File | Sandbox |
| --- | --- | --- | --- |
| `issue_planner` | `codex-bandit:issue-planner` | `agents/issue-planner.md` | read-only tools |
| `test_writer` | `codex-bandit:test-writer` | `agents/test-writer.md` | test edits |
| `code_writer` | `codex-bandit:code-writer` | `agents/code-writer.md` | implementation edits |
| `adversarial_reviewer` | `codex-bandit:adversarial-reviewer` | `agents/adversarial-reviewer.md` | read-only tools |
| `prepare_pr` | `codex-bandit:prepare-pr` | `agents/prepare-pr.md` | workspace tools |
| `land_deploy` | `codex-bandit:land-and-deploy` | `agents/land-and-deploy.md` | Bash and read tools |
| `closeout_retro` | `codex-bandit:closeout-retro` | `agents/closeout-retro.md` | workspace tools |

## Capability Contract

Use assisted mode for Claude Code. Native agent tool restrictions improve role
boundaries, but they do not prove durable identity isolation. Keep the dispatch
and role-output schemas unchanged, and preserve their evidence-bound behavior.

## Assisted Invocation Contract

For assisted dispatch, keep using the public skills:
`plan-work-item`, `write-red-tests`, `implement-green`, `adversarial-gate`,
`prepare-pr`, `land-and-deploy`, and `closeout-retro`. Assisted role outputs use
declared actor identity and proposed evidence only.
