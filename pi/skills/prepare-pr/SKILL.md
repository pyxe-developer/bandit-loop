---
name: prepare-pr
description: Prepare PR-readiness evidence for a Codex Bandit work item.
---

# Prepare PR

Use this skill for the public PR preparation stage. The internal stage ID is
`prepare_pr` and the producer role is `prepare_pr`.

## Inputs

Accept either:

- a `codex-bandit.stage-dispatch-request.v1` with
  `target_role: "prepare_pr"` and `stage: "prepare_pr"`
- a direct route-card path for a work item whose current stage is `prepare_pr`

For direct route-card invocation, first run `orchestrate-assisted next` or
`verify-stage prepare_pr` to prove active adversarial approval. Do not prepare a
PR package from chat-only state.

Required prerequisites:

- valid `route_card.path` and `route_card.digest`
- active adversarial approval evidence bound to the current review package
- route-card `subject.base_ref`, `subject.head_ref`, and
  `subject.expected_head_sha`
- local gate status and review-package references

## Role Boundaries

Prepare deterministic local PR readiness evidence: branch status, local gate
status, review-package references, PR body, and compare guidance. Creating a
remote PR is allowed only when `delivery_authority.allow_pr_create` is true and
the branch is pushed or already exists remotely. If remote tooling is unavailable
or authority is absent, produce compare guidance and a blocker/deferred result
instead of inventing remote state.

For mode `assisted`, actor identity is declared only. Do not claim runtime
policy controls or durable role separation. In enforced mode, preserve supplied
actor identity fields exactly and do not invent them.

## Output

Return exactly one `codex-bandit.role-output.v1` JSON object:

- `success` with `record_type: "command"` or `record_type: "note"` evidence for
  a deterministic PR package
- `deferred` delivery may be represented as a transition evidence event with
  `status: "deferred"` and `delivery_state: "delivery_deferred"`
- `blocked` with structured blockers when local gates, branch authority, or PR
  preparation prerequisites are missing
- no merge, deploy, or HITL approval claims from this stage

Use `bandit-loop delivery-operation` with `operation: "prepare-pr-package"` when a
deterministic package envelope is useful. The helper returns `pr_prepared` or
`delivery_deferred` without depending on remote land/deploy state.

## Required Blockers

Use these codes when applicable:

- `E_ADVERSARIAL_APPROVAL_REQUIRED`
- `E_LOCAL_GATE_FAILED`
- `E_BRANCH_PUSH_AUTHORITY_REQUIRED`
- `E_PR_CREATE_AUTHORITY_REQUIRED`
- `E_REVIEW_PACKAGE_DIGEST_REQUIRED`
- `E_DELIVERY_DEFERRED`

## Prompt Asset

Use `agents/prepare-pr.md` for detailed role behavior and rubric rows.
