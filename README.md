# bandit-loop

bandit-loop is an evidence-led, stage-gated delivery workflow for coding
agents. It provides the same core route-card, evidence, review, and delivery
contracts across Pi, Codex, and Claude Code, with each host using its native
plugin surface.

## Package layout

| Host | Resources | Native surface |
| --- | --- | --- |
| Pi | [`package.json`](package.json), [`pi/`](pi/) | Pi package, skills, executable, and bridge tools |
| Codex | [`codex/`](codex/) | Codex plugin, scripts, MCP, optional agents, and hooks |
| Claude Code | [`claude/`](claude/) | Claude plugin, skills, agents, MCP, and hooks |

All hosts share the same evidence-led workflow:

```text
plan → red → green → adversarial → prepare_pr → hitl_merge_checkpoint → land_deploy → closeout
```

Assisted mode is the default. Role identity is declared in assisted output;
the workflow does not claim runtime isolation or enforced policy unless the
host-specific enforcement surface has been explicitly installed and validated.

## Install for Pi

Install the repository as a user-level Pi package:

```sh
pi install git:github.com/pyxe-developer/bandit-loop
```

For a local checkout:

```sh
pi install /path/to/bandit-loop
```

For a project-local Pi installation, add `-l`:

```sh
pi install -l /path/to/bandit-loop
```

Start a new Pi session after installation. The package provides native stage
skills, the `bandit-loop` executable, and in-session `codex_bandit_*` bridge
tools. Install `pi-subagents` separately to expose the package's role agents:

```sh
pi install npm:pi-subagents
```

See [`pi/README.md`](pi/README.md) for the complete Pi surface.

## Install for Codex

From a checkout, install the Codex plugin with:

```sh
codex/scripts/install-plugin
```

Optional Codex integrations are explicit:

```sh
codex/scripts/install-plugin --with-agents
codex/scripts/install-plugin --with-hooks
codex/scripts/install-plugin --with-all
```

See [`codex/README.md`](codex/README.md) for assisted orchestration, enforced
agent validation, hooks, MCP, delivery HITL, and uninstall instructions.

## Install for Claude Code

Test the Claude Code plugin directly from a checkout:

```sh
claude --plugin-dir ./claude
```

For a local marketplace installation, run these commands from the repository
root:

```text
/plugin marketplace add .
/plugin install codex-bandit@bandit-loop
```

See [`claude/README.md`](claude/README.md) for the Claude-native skills,
agents, hooks, MCP surface, and reload instructions.

## Validation

The shared deterministic checks live with the Codex package and exercise the
workflow contracts independently of the host UI:

```sh
python3 codex/tests/run_fixture_checks.py
python3 codex/tests/run_stage_skill_checks.py
python3 codex/tests/run_orchestrate_checks.py
```

The Claude package also includes a host-specific validator:

```sh
python3 claude/tests/validate_claude_plugin.py
```

## Trust model

The engine treats evidence as the source of truth. Route-card authority,
stage prerequisites, subject freshness, review-package digests, human merge
approval, and operation-time delivery state must be present in the validated
evidence before the workflow advances. Missing, stale, or ambiguous evidence
blocks progress rather than being inferred from chat or remote text.

The host integrations are adapters around that contract; they do not replace
the engine's gates.
