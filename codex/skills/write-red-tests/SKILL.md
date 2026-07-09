---
name: write-red-tests
description: Prepare RED-stage test evidence for a Codex Bandit work item.
---

# Write RED Tests

Use this skill for the public RED stage. The internal stage ID is `red` and the
producer role is `test_writer`.

## Inputs

Accept either:

- a `codex-bandit.stage-dispatch-request.v1` with
  `target_role: "test_writer"` and `stage: "red"`
- a direct route-card path for a work item whose current stage is `red`

For direct route-card invocation, validate the route card and run or request the
same prerequisite checks that `orchestrate-assisted next` would use. If a valid
dispatch cannot be derived, return a `codex-bandit.role-output.v1` blocker.

Required prerequisites:

- valid `route_card.path` and `route_card.digest`
- `required_inputs.commands` includes `red`
- route-card `commands.red.expected_failure` exists
- role contract permits test edits and forbids implementation edits

## Role Boundaries

Write RED tests only. Do not implement production behavior and do not edit
implementation paths such as `src/**`. A RED pass is valid only when the command
fails for the expected route-card failure and not for syntax, dependency,
environment, or unrelated failures.

## Output

Return exactly one `codex-bandit.role-output.v1` JSON object:

- on success, propose command evidence with
  `claim: "red_fails_for_expected_reason"`
- include `command.expected_failure_result`
- set `subject_source: "append_script_actual_repo_head"` for command evidence
- on ambiguity or wrong failure, use `outcome: "blocked"` or
  `outcome: "manual_continuation"`

For mode `assisted`, actor identity is declared only. Do not claim runtime
policy controls or durable role separation. In enforced mode, preserve supplied
actor identity fields exactly and do not invent them.

## Required Blockers

Use these codes when applicable:

- `E_ROUTE_CARD_REQUIRED`
- `E_RED_COMMAND_REQUIRED`
- `E_RED_UNEXPECTED_FAILURE`
- `E_FORBIDDEN_PATH_CHANGED`
- `E_MANUAL_CONTINUATION_REQUIRED`

## Prompt Asset

Use `agents/test-writer.md` for detailed role behavior and rubric rows.
