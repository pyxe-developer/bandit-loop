# Codex surface

## What Codex provides
The Codex surface is the repository's Codex plugin package. It packages an evidence-led workflow with:

- assisted orchestration
- manual stage skills
- optional enforced agents
- optional advisory hooks
- MCP wrappers over the JSON scripts
- delivery gates for merge and deploy

The canonical summary is in [`codex/README.md`](../../codex/README.md).

## Main operational modes

### Assisted mode
Assisted mode is the default. The orchestrator and scripts guide stage advancement while role output declares identity. No runtime isolation or durable policy enforcement is claimed in assisted mode.

The assisted commands documented in the Codex README are:

```sh
scripts/orchestrate-assisted < request.json
scripts/route-card < request.json
scripts/evidence-ledger < request.json
scripts/verify-stage < request.json
scripts/review-package < request.json
```

### Enforced mode opt-in
Enforced mode is intentionally separate from the default plugin surface. The installer can generate and validate custom agents, but the README warns that validation does not prove the runtime loaded them in a non-interactive way.

### Hooks
Hooks are advisory by default and only block when explicitly enabled with `CODEX_BANDIT_HOOK_BLOCKING=1`. The hook uninstall path preserves drifted or tampered files for inspection instead of deleting everything blindly.

### MCP
The MCP wrapper delegates to the same scripts, which keeps behavior aligned across the host surface and the command-line helpers.

## Important files

- [`codex/README.md`](../../codex/README.md) — product and operational overview
- [`codex/hooks/README.md`](../../codex/hooks/README.md) — hook behavior and caveats
- [`codex/.codex-plugin/plugin.json`](../../codex/.codex-plugin/plugin.json) — plugin manifest
- [`codex/scripts/install-plugin`](../../codex/scripts/install-plugin) — install/uninstall entrypoint
- [`codex/scripts/install-agents`](../../codex/scripts/install-agents) — optional enforced-agent installer
- [`codex/scripts/install-git-hooks`](../../codex/scripts/install-git-hooks) — optional Git hook installer
- [`codex/mcp/`](../../codex/mcp/) — MCP wrapper implementation
- [`codex/skills/`](../../codex/skills/) — manual stage skills
- [`codex/tests/`](../../codex/tests/) — validation scripts
- [`codex/references/`](../../codex/references/) — route-card, workflow, schemas, fixtures, and dispatch references

## Delivery and merge behavior
The Codex README is explicit that merge and deploy decisions depend on operation-time evidence:

- human approval must be bound to the exact PR and head SHA
- remote comments are untrusted input
- deploy contracts are only presence-checked in v1

That means the plugin should be changed carefully whenever you touch delivery behavior, because it is part of the repo's trust boundary rather than a cosmetic feature.

## Change guidance for future agents

When changing Codex behavior:

1. Inspect the README plus the relevant installer, hook, MCP, or test file.
2. Update the shared workflow docs if the change alters stage or evidence semantics.
3. Re-run the Codex validation scripts mentioned in the README.
4. Check whether the change also needs a Pi or Claude surface update so the host adapters remain aligned.

## Source anchors

- Product overview: [`codex/README.md`](../../codex/README.md)
- Hook overview: [`codex/hooks/README.md`](../../codex/hooks/README.md)
- Root plugin manifest: [`codex/.codex-plugin/plugin.json`](../../codex/.codex-plugin/plugin.json)
- Workflow contract scaffold: [`codex/references/workflow-contract.md`](../../codex/references/workflow-contract.md)
- Route-card scaffold: [`codex/references/route-card.md`](../../codex/references/route-card.md)
- Script contracts scaffold: [`codex/references/script-contracts.md`](../../codex/references/script-contracts.md)
- Validation entrypoints: [`codex/tests/`](../../codex/tests/)
