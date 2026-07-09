# Script And Stage Dispatch Contracts

Scaffold placeholder for JSON-in/JSON-out script contracts and stage dispatch
payloads.

Reserved script entrypoints:

- `scripts/route-card`
- `scripts/evidence-ledger`
- `scripts/verify-stage`
- `scripts/review-package`
- `scripts/install-agents`
- `scripts/install-git-hooks`

Ticket 04 owns the core script runtime for the first four commands. Ticket 08
owns installed-agent setup. Ticket 09 owns advisory hook installation and MCP
wrapping of the script entrypoints.
