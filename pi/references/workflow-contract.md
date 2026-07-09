# Workflow Contract

Scaffold placeholder for the Codex Bandit workflow overview.

Canonical work item files live under `.codex-bandit/work/<work_item_id>/`:

- `route-card.json`
- `evidence.jsonl`
- `reports/`

Internal stage IDs:

- `plan`
- `red`
- `green`
- `adversarial`
- `prepare_pr`
- `hitl_merge_checkpoint`
- `land_deploy`
- `closeout`

Public skill names:

- `orchestrate`
- `plan-work-item`
- `write-red-tests`
- `implement-green`
- `adversarial-gate`
- `prepare-pr`
- `land-and-deploy`
- `closeout-retro`

This file is a scaffold reference only. Ticket 04 must consume the materialized
schemas and fixtures under `references/schemas/` and `references/fixtures/`
when those Ticket 02 payloads are available.
