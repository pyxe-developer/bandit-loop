# Claude Code surface

## What Claude Code provides
The Claude Code surface packages bandit-loop as a native Claude plugin. It includes:

- a plugin manifest in [`claude/.claude-plugin/plugin.json`](../../claude/.claude-plugin/plugin.json)
- a Claude hook registration file in [`claude/hooks/hooks.json`](../../claude/hooks/hooks.json)
- native skills in [`claude/skills/`](../../claude/skills/)
- native agents in [`claude/agents/`](../../claude/agents/)
- MCP wiring in [`claude/.mcp.json`](../../claude/.mcp.json)
- host-specific validation in [`claude/tests/`](../../claude/tests/)

The Claude README says this surface provides the same assisted workflow and JSON evidence contracts as the Codex and Pi packages. See [`claude/README.md`](../../claude/README.md).

## User-facing behavior
The documented install/test paths are:

```sh
claude --plugin-dir ./claude
/plugin marketplace add .
/plugin install codex-bandit@bandit-loop
/reload-plugins
```

The session-start hook is advisory and non-blocking. It reports a route-card status message when a single work item is discoverable, but it does not mutate files or enforce gates.

## Skills and agents
The Claude package has eight public workflow skills and seven role agents. The test suite checks that the skills and agent prompts exist and have the required contracts.

Skills are the public stage entrypoints; agents are the role prompts that mirror those stages. If you change one, check the other.

## MCP and scripts
The Claude README describes MCP as a thin wrapper around the shared scripts. The repo's tests exercise plugin validation and the MCP surface, but they do not prove host discovery or runtime loading beyond what the plugin can validate locally.

## Validation and release readiness
The main Claude validation entrypoint is [`claude/tests/validate_claude_plugin.py`](../../claude/tests/validate_claude_plugin.py). The release checklist in [`claude/docs/release-readiness.md`](../../claude/docs/release-readiness.md) treats the Claude surface as shippable with documented v1 limitations.

## Important limitations

- The surface is assisted by default; docs do not claim runtime isolation or enforced policy.
- The hook is advisory only and never blocks Claude Code.
- Deploy contracts are presence-checked only.
- Host discovery/loading for MCP is not proven by the repository tests alone.
- The repo intentionally keeps Claude-specific functionality separate from Codex-only install-agent and Git-hook behavior.

## What to check before changing Claude Code

- If you modify skills or agents, re-run the Claude validation script and the stage-skill tests.
- If you modify hooks or MCP, inspect the manifest and hook registration alongside the implementation.
- If you modify shared workflow semantics, update the model and the root README as needed so all three surfaces stay aligned.

## Source anchors

- Claude README: [`claude/README.md`](../../claude/README.md)
- Plugin manifest: [`claude/.claude-plugin/plugin.json`](../../claude/.claude-plugin/plugin.json)
- Hooks file: [`claude/hooks/hooks.json`](../../claude/hooks/hooks.json)
- Hook runner: [`claude/hooks/claude-bandit-hook-runner.py`](../../claude/hooks/claude-bandit-hook-runner.py)
- MCP wrapper: [`claude/mcp/codex_bandit_mcp.py`](../../claude/mcp/codex_bandit_mcp.py)
- Validation: [`claude/tests/validate_claude_plugin.py`](../../claude/tests/validate_claude_plugin.py)
- Release checklist: [`claude/docs/release-readiness.md`](../../claude/docs/release-readiness.md)
