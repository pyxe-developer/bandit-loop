# Script And Stage Dispatch Contracts

JSON-in/JSON-out script contracts and stage dispatch payloads.

Pi entrypoints, available through the installed `bandit-loop` command:

- `bandit-loop route-card`
- `bandit-loop evidence-ledger`
- `bandit-loop verify-stage`
- `bandit-loop review-package`
- `bandit-loop delivery-operation`
- `bandit-loop orchestrate-assisted`

The Pi package delegates these commands to the same core script runtime as the
Codex plugin. Codex-only installed-agent, Git-hook, and MCP entrypoints are not
part of this package's runtime surface.
