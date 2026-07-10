# Workflow and delivery

## End-to-end flow
The shared workflow advances a work item through:

`plan → red → green → adversarial → prepare_pr → hitl_merge_checkpoint → land_deploy → closeout`

The orchestrator skill documents the same sequence and explains that assisted mode is the default. See [`claude/skills/orchestrate/SKILL.md`](../../claude/skills/orchestrate/SKILL.md).

## Core artifacts

### Route card
The route card defines the work item and the rules for progressing it. The documented contract reserves the canonical path:

`.codex-bandit/work/<work_item_id>/route-card.json`

The scaffold reference is in [`claude/references/route-card.md`](../../claude/references/route-card.md), while the orchestrator reads and updates route-card state as part of its helper requests.

### Evidence ledger
The ledger is append-only JSONL under the work-item directory. Evidence events carry the claims that the reducer uses to decide stage status. The workflow model treats the ledger as the source of truth for stage advancement.

### Review package
Before adversarial review, the orchestrator builds a review package and stores its digest in the route card. The workflow model makes the review package digest part of the adjudication chain so the adversarial reviewer is bound to a specific subject.

## Assisted mode versus enforced mode

### Assisted mode
Assisted mode is the default across the repository. In assisted mode:

- the role output declares identity
- the orchestrator records evidence
- the workflow does not claim sandboxing or durable role isolation
- validation still matters; the reducer and scripts remain authoritative

This is stated in the root README, the Codex README, and the orchestrate skill.

### Enforced mode
Enforced mode is opt-in. The Codex README says installed-agent validation is required before enforced claims are made, and that validation does not mean the runtime has been proven to load those agents non-interactively.

## Delivery gates

### Merge checkpoint
At `hitl_merge_checkpoint`, merge is gated by human approval bound to the exact PR number and head SHA. The root README and Codex README both stress that operation-time state must be supplied by tools when the merge decision is made.

### Deploy
Deploy is gated by a contract and operational checks. The Codex README notes that deploy contracts in v1 are presence-checked only; the presence of a contract is required, but subfields are not deeply validated.

### Closeout
If delivery is deferred, the workflow still has a valid terminal-local outcome and moves to closeout with that reason recorded.

## Operational rules that matter during implementation

- The orchestrator must not edit product code, tests, or verdicts during active work unless a scoped manual patch is explicitly authorized.
- Review requests and delivery decisions must be based on validated evidence, not remote text or chat claims.
- The `verify-stage` reducer is the authority for current stage truth; other scripts and skills are inputs around that reducer.
- When a stage is blocked, the workflow expects repair, reroute, waiver, or escape evidence rather than ad hoc advancement.

## Change guidance for future agents

If you change anything in the workflow chain:

1. Update the contract or model first.
2. Check the relevant host README so the user-facing docs stay aligned.
3. Re-run the shared workflow tests in `codex/tests/` and the host-specific checks that cover the changed surface.
4. Re-read the stage skill and orchestrator docs to make sure any new stage or gate is reflected in the role surface.

## Source anchors

- Orchestrator skill: [`claude/skills/orchestrate/SKILL.md`](../../claude/skills/orchestrate/SKILL.md)
- Workflow model: [`claude/docs/models/codex-bandit-workflow/MODEL.md`](../../claude/docs/models/codex-bandit-workflow/MODEL.md)
- Workflow contract scaffold: [`claude/references/workflow-contract.md`](../../claude/references/workflow-contract.md)
- Route-card scaffold: [`claude/references/route-card.md`](../../claude/references/route-card.md)
- Script contracts scaffold: [`claude/references/script-contracts.md`](../../claude/references/script-contracts.md)
- Root product overview: [`README.md`](../../README.md)
