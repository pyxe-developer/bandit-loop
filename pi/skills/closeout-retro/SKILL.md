---
name: closeout-retro
description: Record Codex Bandit closeout evidence and retrospective notes.
---

# Closeout Retro

Use this skill for the public closeout stage. The internal stage ID is
`closeout` and the producer role is `closeout_retro`.

## Inputs

Accept either:

- a `codex-bandit.stage-dispatch-request.v1` with
  `target_role: "closeout_retro"` and `stage: "closeout"`
- a direct route-card path for a work item whose current stage is `closeout`

For direct route-card invocation, validate the route card and ledger status
before acting. If the terminal state is unclear, return a structured blocker.

Required prerequisites:

- valid `route_card.path` and `route_card.digest`
- terminal pass, terminal blocker, or deferred-delivery evidence
- evidence IDs or report paths that identify the final state

## Role Boundaries

Closeout may write or propose the closeout report and note/transition evidence
only. It must not edit production code, tests, route-card authority, delivery
authority, or capability mode.

## Output

Return exactly one `codex-bandit.role-output.v1` JSON object:

- on success, propose `note` or closeout `transition` evidence
- record final state, caveats, deferred delivery reason, unresolved blockers,
  and lessons
- do not silently mark partial work complete
- do not weaken RED, GREEN, adversarial, HITL, or delivery rules

Lessons are proposals only. Governance changes require explicit human approval
outside this role output.

For mode `assisted`, actor identity is declared only. Do not claim runtime
policy controls or durable role separation. In enforced mode, preserve supplied
actor identity fields exactly and do not invent them.

## Required Blockers

Use these codes when applicable:

- `E_CLOSEOUT_FINAL_STATE_REQUIRED`
- `E_CLOSEOUT_DEFERRED_REASON_REQUIRED`
- `E_PARTIAL_WORK_CANNOT_COMPLETE`
- `E_RULE_WEAKENING_PROPOSED`

## Prompt Asset

Use `agents/closeout-retro.md` for detailed role behavior and rubric rows.
