---
name: implement-green
description: Prepare GREEN-stage implementation evidence for a Codex Bandit work item.
---

# Implement GREEN

Use this skill for the public GREEN stage. The internal stage ID is `green` and
the producer role is `code_writer`.

## Inputs

Accept either:

- a `codex-bandit.stage-dispatch-request.v1` with
  `target_role: "code_writer"` and `stage: "green"`
- a direct route-card path for a work item whose current stage is `green`

For direct route-card invocation, validate the route card and active RED
evidence before acting. If active RED evidence is missing, return a structured
reroute to `red` owned by `test_writer`.

Required prerequisites:

- valid `route_card.path` and `route_card.digest`
- active RED evidence IDs in `required_inputs.evidence_ids`
- `required_inputs.commands` includes `green`
- role contract permits implementation edits and forbids test edits

## Role Boundaries

Implement production code only inside allowed paths. Do not edit `tests/**`,
snapshots, fixtures, or assertions in GREEN. If a test change is needed, return
`outcome: "reroute"` with `target_stage: "red"` and
`owner_role: "test_writer"`; do not make the test edit.

## Output

Return exactly one `codex-bandit.role-output.v1` JSON object:

- on success, propose command evidence with
  `claim: "green_passes_required_commands"`
- set `subject_source: "append_script_actual_repo_head"` for command evidence
- on forbidden test edits, return `outcome: "blocked"` with
  `E_FORBIDDEN_PATH_CHANGED`
- on necessary test-surface repair, return `outcome: "reroute"` to RED

For mode `assisted`, actor identity is declared only. Do not claim runtime
policy controls or durable role separation. In enforced mode, preserve supplied
actor identity fields exactly and do not invent them.

## Required Blockers

Use these codes when applicable:

- `E_ROUTE_CARD_REQUIRED`
- `E_RED_REQUIRED`
- `E_GREEN_COMMAND_REQUIRED`
- `E_FORBIDDEN_PATH_CHANGED`
- `E_SCOPE_CREEP`

## Prompt Asset

Use `agents/code-writer.md` for detailed role behavior and rubric rows.
