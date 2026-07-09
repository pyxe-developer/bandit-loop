# Codex Bandit for Claude Code

Codex Bandit is an evidence-led, stage-gated delivery workflow for Claude
Code. This port provides the same assisted workflow and JSON evidence contracts
as the Codex and Pi packages, using Claude Code's native skills, custom agents,
hooks, and MCP plugin surfaces.

## Install locally

Test or use the plugin directly from this repository:

```sh
claude --plugin-dir ./claude
```

Then invoke the namespaced skills, for example:

```text
/codex-bandit:orchestrate
/codex-bandit:plan-work-item
/codex-bandit:write-red-tests
/codex-bandit:implement-green
```

For a shared installation, add the repository as a local marketplace from the
repository root, then install `codex-bandit`:

```text
/plugin marketplace add .
/plugin install codex-bandit@bandit-loop
```

Run `/reload-plugins` after changing plugin files during development.

## Surface

- `skills/` contains the eight public workflow stages.
- `agents/` contains Claude-native role agents with the same role contracts as
  the Codex prompt assets.
- `.mcp.json` exposes the stable route-card, evidence, verification, review,
  delivery, and orchestration helpers through MCP.
- `hooks/hooks.json` installs one non-blocking `SessionStart` advisory. It only
  reports an unambiguous active work item; it does not mutate files or bypass
  workflow gates.
- `scripts/` contains the shared JSON runtime and is self-contained so the
  plugin still works after Claude Code caches it.

The workflow remains assisted by default. Actor identity is declared in role
output and is not presented as runtime isolation or enforced policy.
