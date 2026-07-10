# Architecture overview

## System shape
`bandit-loop` is a shared workflow product with three host adapters:

- **Pi package** in [`pi/`](../../pi/)
- **Codex plugin** in [`codex/`](../../codex/)
- **Claude Code plugin** in [`claude/`](../../claude/)

The repository root README describes the product as a single evidence-led workflow that is surfaced through each host's native plugin mechanism. See [`README.md`](../../README.md).

## Canonical workflow spine
The workflow is stage-gated and evidence-driven. The common stage sequence is:

`plan → red → green → adversarial → prepare_pr → hitl_merge_checkpoint → land_deploy → closeout`

The shared model doc explains why the system is not just a simple state machine: lifecycle, reducer logic, authorization policy, and dispatch ordering are separate concerns. See [`claude/docs/models/codex-bandit-workflow/MODEL.md`](../../claude/docs/models/codex-bandit-workflow/MODEL.md).

## Main architectural responsibilities

### 1. Host adapters
Each host package adapts the same workflow to its own surface:

- **Pi** exposes package metadata, skills, a CLI entrypoint, and bridge tools.
- **Codex** exposes assisted orchestration, optional enforced agents, optional hooks, and MCP wrappers.
- **Claude Code** exposes skills, agents, hooks, and MCP through the plugin manifest.

The host-specific README files are the fastest way to see each adapter's intended surface:

- [`pi/README.md`](../../pi/README.md)
- [`codex/README.md`](../../codex/README.md)
- [`claude/README.md`](../../claude/README.md)

### 2. Workflow contract
The authoritative contract lives in evidence-oriented files rather than chat text. The key inputs are:

- route card
- evidence ledger
- stage reducer / verification scripts
- review package digest
- human merge approval and delivery state

These are documented across the reference files in `claude/references/` and modeled in `claude/docs/models/codex-bandit-workflow/`.

### 3. Evidence and adjudication
Evidence is append-only and the reducer decides whether a stage can advance. The model doc calls out a **verify-stage reducer** as the adjudication authority and treats other surfaces as producers or recorders, not truth sources.

### 4. Trust boundaries
The repo is explicit that:

- assisted mode only **declares** identity; it does not promise runtime isolation
- enforced mode requires installed-agent validation evidence
- chat, remote comments, and stale projections are not authoritative
- delivery safety depends on evidence present at the time of validation

Those limits are described in the root README, the Codex README, and the Claude workflow model.

## Design implications for future changes

- Prefer changing the shared contracts and validation logic before changing a host-specific adapter.
- If a behavior differs between hosts, document it as an adapter difference, not a new workflow.
- When adding a stage, evidence field, or delivery gate, inspect the workflow model and the host README files together so the surface stays consistent.
- If you touch operational behavior, also check the validation scripts in `*/tests/` because they are part of the product contract.

## Good source entry points

- Root summary: [`README.md`](../../README.md)
- Workflow model: [`claude/docs/models/codex-bandit-workflow/MODEL.md`](../../claude/docs/models/codex-bandit-workflow/MODEL.md)
- Orchestrator skill: [`claude/skills/orchestrate/SKILL.md`](../../claude/skills/orchestrate/SKILL.md)
- Workflow contract scaffold: [`claude/references/workflow-contract.md`](../../claude/references/workflow-contract.md)
