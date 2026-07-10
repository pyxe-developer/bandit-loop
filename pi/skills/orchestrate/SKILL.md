---
name: orchestrate
description: Coordinate a Codex Bandit work item through the assisted stage-gated workflow.
---

# Orchestrate

Coordinate one Codex Bandit work item through the assisted workflow:

`plan -> red -> green -> adversarial -> prepare_pr -> hitl_merge_checkpoint -> land_deploy -> closeout`

## Epic tracking

When the user is coordinating an epic, initialize or update its visual tracker
with `codex_bandit_dashboard` operation `upsert`. Include every known work item
in `input.work_item_ids`; do not infer missing IDs. The durable files are
`.codex-bandit/epics/<epic_id>/epic.json` and `dashboard.html`.

The dashboard is a generated projection only. Route cards and evidence ledgers
remain authoritative. Assisted orchestration refreshes every epic dashboard
that contains the current work item. Return the dashboard path to the user when
the orchestrator response includes `result.dashboard_paths`.

## Capability Mode

Default mode is assisted. Assisted mode is a guided evidence workflow:

- stage roles produce `codex-bandit.role-output.v1` proposals
- the orchestrator records evidence through the core scripts
- actor identity is declared, not isolated or enforced
- no sandbox, model, tool-policy, or durable role-isolation claim is made

If a route card requests `capability_mode.mode=enforced`, do not dispatch a role
unless the core script validation succeeds with active install-agent evidence.
Installing or validating enforced agents is outside this skill.

## Runtime Surface

Use `bandit-loop orchestrate-assisted` as the orchestration layer. It is a thin
state machine over the Ticket 04 JSON scripts:

- `bandit-loop route-card`
- `bandit-loop evidence-ledger`
- `bandit-loop verify-stage`
- `bandit-loop review-package`

Every helper request is JSON on stdin:

```json
{
  "schema_version": "codex-bandit.orchestrate-request.v1",
  "operation": "next",
  "repo_root": ".",
  "work_item_id": "cb-123",
  "route_card_path": ".codex-bandit/work/cb-123/route-card.json",
  "ledger_path": ".codex-bandit/work/cb-123/evidence.jsonl",
  "input": {},
  "request_id": "orch_cb_123_next"
}
```

Supported operations:

| Operation | Use |
| --- | --- |
| `create` | Create and validate a route card supplied in `input.route_card`. |
| `status` | Validate the route card and return the current reducer envelope. |
| `next` | Advance only when the current stage reducer response permits it; otherwise return a dispatch request or blocker. |
| `apply-role-output` | Validate a `codex-bandit.role-output.v1`, append assisted evidence, and rerun the reducer. |
| `record-escape` | Record `manual_patch`, `exit_orchestration`, or `defer_delivery` as evidence. `manual_patch` requires scoped `input.paths`. |
| `guard-edit` | Normalize requested paths, refuse orchestrator edits to `src/**` or `tests/**` unless a scoped unconsumed `manual_patch` or `exit_orchestration` is recorded, and consume `manual_patch` on use. |

## Workflow Rules

Create or resume from the route card and ledger under
`.codex-bandit/work/<work_item_id>/`. Missing required route-card fields block;
do not reconstruct them from chat.

For each stage, call `next`. When it returns `next_action=dispatch_role`, pass
the returned `stage-dispatch-request.v1` to the appropriate public stage skill
and feed the role's JSON output back through `apply-role-output`.

Before adversarial review, `next` builds a review package and writes its digest
into `route_card.evidence.review_package.digest` through `route-card update`.
Do not dispatch adversarial review against an unwired or chat-only digest.

At `hitl_merge_checkpoint`, a `verify-stage` pass with
`W_OPERATION_TIME_REMOTE_HEAD_REQUIRED` means ledger consistency only. Treat the
orchestrator response `E_OPERATION_TIME_REMOTE_HEAD_REQUIRED` as not merge-ready;
Ticket 07 owns the operation-time remote PR head and approval-expiry checks.

At `land_deploy`, respect runtime blocks for missing adversarial approval or
missing HITL approval. Do not reroute around exit-code 3 prerequisite blockers.

Delivery may be deferred with `record-escape` kind `defer_delivery`; the next
step routes to `closeout`.

The orchestrator must not edit product code, tests, or verdicts during active
work. If a human authorizes a manual patch, first record `manual_patch` with the
exact paths being authorized, then run `guard-edit` for those paths. The
authorization is consumed by that check; subsequent edits require a fresh
authorization. Manual-patched work still needs a new review package and
adversarial pass before delivery.
