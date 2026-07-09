---
name: plan-work-item
description: Draft or refine a Codex Bandit route card for a work item.
---

# Plan Work Item

Use this skill for the public planning stage. The internal stage ID is `plan`
and the producer role is `issue_planner`.

## Inputs

Accept either:

- a `codex-bandit.stage-dispatch-request.v1` with
  `target_role: "issue_planner"` and `stage: "plan"`
- a direct route-card creation/update request containing the future route-card
  payload and enough user-owned intent to validate it

Before acting, validate that the request includes route-card intent,
acceptance criteria, non-goals, subject, stage plan, commands, role boundaries,
capability mode, and delivery authority. Missing information is a structured
blocker, not something to infer from chat history.

## Role Boundaries

Planning may propose route-card content only. Do not write the route card,
append evidence, edit product code, edit tests, or expand delivery authority.
Protected fields such as `work_item_id`, `source.request`, `subject.base_ref`,
`subject.head_ref`, and `capability_mode.mode` remain governed by the route-card
update policy.

## Output

Return exactly one `codex-bandit.role-output.v1` JSON object:

- `actor.role`: `issue_planner`
- `actor.mode`: the dispatch capability mode, usually `assisted`
- `outcome`: `success`, `blocked`, `manual_continuation`, or `reroute`
- `proposed_evidence`: transition or blocker proposals only
- `route_card_patch`: proposed changes only; the orchestrator must review and
  apply route-card updates through the route-card script

For mode `assisted`, actor identity is declared only. Do not claim runtime
policy controls or durable role separation. In enforced mode, preserve supplied
actor identity fields exactly and do not invent them.

## Required Blockers

Use these codes when applicable:

- `E_ROUTE_CARD_REQUIRED`
- `E_ACCEPTANCE_CRITERIA_REQUIRED`
- `E_DELIVERY_AUTHORITY_UNCLEAR`
- `E_CAPABILITY_MODE_UNVALIDATED`

## Prompt Asset

Use `agents/issue-planner.md` for detailed role behavior and rubric rows.
