# OpenWiki quickstart

## What this repository is
`bandit-loop` is an evidence-led, stage-gated delivery workflow for coding agents. The repository packages the same core workflow for three host surfaces:

- **Pi**: a Pi package with skills, executable entrypoints, and extension tools
- **Codex**: a Codex plugin with assisted orchestration, optional agents, hooks, MCP, and delivery gates
- **Claude Code**: a Claude plugin with native skills, agents, hooks, MCP, and validation

The shared workflow runs through the same stage sequence everywhere:

`plan → red → green → adversarial → prepare_pr → hitl_merge_checkpoint → land_deploy → closeout`

The root README is the best one-page summary of the product shape: [`README.md`](../README.md).

## How to use this wiki
Start here, then follow the section pages that match what you are changing:

- [Architecture overview](architecture/overview.md)
- [Workflow and delivery](workflows/orchestration-and-delivery.md)
- [Pi surface](surfaces/pi.md)
- [Codex surface](surfaces/codex.md)
- [Claude Code surface](surfaces/claude-code.md)

## High-level repository map

| Area | Canonical source files | What to learn there |
| --- | --- | --- |
| Root package | [`package.json`](../package.json), [`README.md`](../README.md) | Package metadata and the cross-host overview |
| Pi package | [`pi/package.json`](../pi/package.json), [`pi/README.md`](../pi/README.md) | Pi install, CLI, skills, extension tools, and dashboard |
| Codex plugin | [`codex/README.md`](../codex/README.md), [`codex/hooks/README.md`](../codex/hooks/README.md) | Assisted workflow, optional enforcement, hooks, MCP, installer behavior |
| Claude plugin | [`claude/README.md`](../claude/README.md), [`claude/.claude-plugin/plugin.json`](../claude/.claude-plugin/plugin.json) | Claude-native plugin surface, skills, agents, hooks, MCP, validation |
| Shared workflow model | [`claude/docs/models/codex-bandit-workflow/MODEL.md`](../claude/docs/models/codex-bandit-workflow/MODEL.md) | States, events, invariants, and adjudication model |
| Contracts and fixtures | [`claude/references/workflow-contract.md`](../claude/references/workflow-contract.md), [`claude/references/route-card.md`](../claude/references/route-card.md), [`claude/references/script-contracts.md`](../claude/references/script-contracts.md) | Canonical workflow contracts and the JSON script surface |

## Core mental model

1. A **route card** defines the work item, stages, commands, subjects, evidence requirements, and delivery authority.
2. A **ledger** records evidence events in append-only form.
3. The **orchestrator** and **stage skills** advance the work item only when the validated evidence allows it.
4. **Human approval** is still required for merge and some delivery decisions.
5. Host integrations are adapters around the same contract; they do not replace the gates.

## What to watch out for

- The repo defaults to **assisted mode**. It does not claim runtime isolation or enforced policy unless host-specific enforcement has been installed and validated.
- Evidence is the source of truth. Chat text, remote comments, and stale projections are not authoritative.
- The Pi dashboard is a projection over the workflow state, not a second workflow system.
- Some contract docs under `claude/references/` are scaffolds that reserve paths and responsibilities; use the current source and tests when making behavioral changes.

## Best next reads

- For repo architecture and trust boundaries: [Architecture overview](architecture/overview.md)
- For stage flow and delivery gates: [Workflow and delivery](workflows/orchestration-and-delivery.md)
- For Pi-specific behavior: [Pi surface](surfaces/pi.md)
- For Codex install and runtime controls: [Codex surface](surfaces/codex.md)
- For Claude plugin packaging and validation: [Claude Code surface](surfaces/claude-code.md)
