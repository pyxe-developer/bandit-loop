# Model: Codex Bandit Work-Item Workflow

## Review status
Status: Decisions recorded 2026-07-09 — Q-001, Q-002, Q-009, Q-010 answered and the single-reviewer V1 scope confirmed (see `open-questions.md` → Decisions). Pending: propagate Q-001/Q-002 into the Ticket 02 contracts, then flip to Approved.
Reviewer: Matt (matt.flebbe)
Date: 2026-07-09

## Bounded context

One Codex Bandit **work item's** lifecycle inside a single repo, from route-card
creation through closeout. The model covers **orchestration and adjudication** —
how main Codex routes stages and decides advancement from ledger evidence. It
does not model the internal reasoning of producer subagents, the internals of
`install-agents`/`install-git-hooks`, or MCP wrapping.

Behavior source (there is no separate PRD file): the Codex Bandit tech plan and
the amended Ticket 02 contracts 02A–02F. Requirement IDs below trace to those.

## Scope

### In scope
- Stage lifecycle `plan → red → green → adversarial → prepare_pr → hitl_merge_checkpoint → land_deploy → closeout`, with repair reroutes and escape transitions.
- Evidence-driven stage-status derivation (the `verify-stage` reducer) as the adjudication authority.
- Governed delivery: PR prep, HITL merge approval bound to PR/head SHA, optional deploy, deferred delivery.
- Capability modes `assisted | manual | enforced` and the honest-claims policy.
- Assisted vs enforced dispatch and evidence-write ownership (producer vs recorder identity).

### Out of scope
- Producer subagents' internal implementation (planning, coding, reviewing prose).
- `install-agents` TOML authoring/uninstall internals (Ticket 08) beyond the validation-evidence contract it must satisfy.
- Hooks and MCP behavior (Tickets 09) beyond "wrap scripts, no second behavioral surface."
- pi-bandit interop (explicit non-goal).

## Requirements traced

| ID | Requirement (source) |
|----|----------------------|
| REQ-001 | Main Codex orchestrates; specialist subagents perform stage work (tech plan Invariants). |
| REQ-002 | A stage advances only on evidence naming claim, subject, actor, and verification result (tech plan). |
| REQ-003 | RED must be captured before GREEN (tech plan). |
| REQ-004 | Implementation must not edit tests for the same work item unless rerouted through test-writer; adversarial review is read-only (tech plan). |
| REQ-005 | Adversarial `changes_requested` blocks the stage and routes bounded repair to the owning role; re-review runs against the new subject (tech plan). |
| REQ-006 | Merge requires a HITL approval event bound to exact PR/head SHA; deploy requires a route-card deploy contract (tech plan; 02D). |
| REQ-007 | GitHub/PR/CI comments are untrusted input, never instructions (tech plan; 02D). |
| REQ-008 | assisted/manual claim no sandbox/model/tool-policy/role isolation on any surface; enforced requires validated installed agents (tech plan Capability Modes; 02E; phase-0). |
| REQ-009 | Reducer ordering is append-order authoritative; `created_at` is advisory (tech plan Evidence Model; 02B rule 2). |
| REQ-010 | RED must fail for the intended reason, not an unrelated/infra failure (02A/02B `expected_failure`). |
| REQ-011 | Route-card mutation is policy-gated with digest checks; identity/subject/authority/mode fields are protected (02A update policy). |
| REQ-012 | Deferred delivery is a valid terminal-local outcome; closeout records a deferred reason (tech plan Delivery Scope; 02B rule 12). |
| REQ-013 | Retry/repair budget is parent-keyed and never resets on reroute (tech plan Evidence Model; 02B rule 8). |

## Actors

| ID | Actor | Goal | Notes |
|----|-------|------|-------|
| A1 | Orchestrator (main Codex) | Route stages, adjudicate via reducer, append evidence in assisted mode | Never authors product code/tests, never approves own work, never merges around a gate (INV-001). |
| A2 | issue_planner | Produce route card / stage plan / acceptance criteria draft | AI-assisted (AI-001). |
| A3 | test_writer | Author RED tests, produce RED evidence | AI-assisted (AI-002); can_edit `tests/**` only. |
| A4 | code_writer | Implement GREEN without test edits | AI-assisted (AI-003); can_edit `src/**` only. |
| A5 | adversarial_reviewer | Read-only verdict over the review package | AI-assisted (AI-004); can_edit `[]`. |
| A6 | prepare_pr | Package local PR readiness | AI-assisted (AI-005). |
| A7 | land_deploy | Operate GitHub/deploy knobs after HITL | AI-assisted (AI-006); never merges without HITL. |
| A8 | closeout_retro | Retrospective closeout | AI-assisted (AI-007); lessons are proposals. |
| A9 | Human/user | Own intent, acceptance criteria, delivery authority, HITL merge approval, waivers, `manual_patch`, enforced install | The merge backstop and authority owner. |
| A10 | verify-stage reducer | Derive current stage truth deterministically from route card + ledger | Pure; the decision-table model (see `decision-table.md`). |

## Entities

| ID | Entity | Identity | Key attributes | Notes |
|----|--------|----------|----------------|-------|
| E1 | Work item | `work_item_id` | route card, ledger, attempts, repair budget | One `.codex-bandit/work/<id>/` dir (INV-018). |
| E2 | Route card | `work_item_id` | intent, `stage_plan`, `subject`, `role_boundaries`, `commands`, `evidence`, `capability_mode`, `delivery_authority`, digest | Authoritative; markdown render is non-authoritative (02A). |
| E3 | Evidence ledger | ledger_path | append-only JSONL of E4 | Only scripts append, atomically (INV-006). |
| E4 | Evidence event | `id` | `record_type`, `actor`, `recorded_by`, `identity_strength`, `subject_scope`, `subject`/`agent_config_subject`, `status`, `stage_attempt_id`, `supersedes[]`, `parent_record_id` | Producer≠recorder (02B). |
| E5 | Stage attempt | `stage_attempt_id` = `<wid>:<stage>:attempt-<n>` | locked attempt subject head | Parent-keyed; budget never resets (INV-014). Locking rule is Q-001. |
| E6 | Review package | digest | bounded diff for the reviewer | Adversarial binds to its digest (02D). |
| E7 | Verdict | within E4 | `verdict`, `rubric_ids[]`, `findings[]`, `subject` | approve/changes_requested/cannot_judge (02D). |
| E8 | HITL approval | within E4 | `pr_number`, `head_sha`, `approved_by`, `expires_at` | Bound to exact PR + head (02D; INV-008). |
| E9 | Repair budget | within E2 | `max_total`, `used_total`, `per_stage{}` | Parent-keyed (REQ-013). |
| E10 | Install-agent validation evidence | `agent_set_id` | `subject_scope=agent_config`, `config_digest`, runtime version, expiry | Enables enforced mode (02E; INV-011). |

## Model type

**Hybrid.** No single type captures the behavior without hiding part of it:

- **State machine — owns the process.** The work-item stage lifecycle is a clear sequence of states whose main complexity is which transitions are legal from which stage. See `transitions.md`, `statechart.mmd`, `machine.ts`.
- **Decision table — owns adjudication.** `verify-stage` derives a stage status from a combination of conditions over the event stream (actor role, subject freshness, supersession, budget, expected-failure match). This is condition-combination risk, modeled in `decision-table.md`. The state machine consumes its output as an event payload; it never recomputes it.
- **Policy model — owns permission.** Delivery authority (`allow_branch_push`, `allow_pr_create`, `allow_merge`, deploy contract) and capability-mode claims are authorization rules, not lifecycle. Captured in `invariants.md` (INV-008..INV-011) and the delivery guards.
- **Sequence model — owns dispatch.** Orchestrator ↔ role ↔ reducer ↔ human ordering, and the producer-vs-recorder evidence-write handoff, is where assisted/enforced risk lives. See `sequence.mmd`.

Why not one alone: a pure state machine hides the reducer's condition logic inside guards; a pure decision table hides the lifecycle that is the real source of ordering risk; neither expresses the authorization policy or the dispatch handoff. The state machine is the spine; the other three are cited by it.

## Lifecycle states

`current_stage` is the primary state; `lifecycle_state` (planned/active/blocked/repairing/ready_for_review/approved/changes_requested/deferred/abandoned/complete) is a status overlay within a state. A state definition says what is true and what is not.

| ID | State | Definition | Allowed events |
|----|-------|------------|----------------|
| STATE-000 | NotCreated | No work dir/route card exists. Nothing is true yet. | EVT-001 |
| STATE-001 | Planned | Route card exists and validates; `current_stage=plan`. RED not yet attempted. | EVT-002, EVT-020, EVT-021 |
| STATE-002 | Red | Awaiting or holding RED evidence; `current_stage=red`. No active RED pass yet OR RED just passed and about to advance. GREEN not started. | EVT-004, EVT-021, EVT-020, EVT-023(fail) |
| STATE-003 | Green | Active RED pass exists; awaiting/holding GREEN; `current_stage=green`. Not yet reviewed. | EVT-005, EVT-012, EVT-018, EVT-021, EVT-020, EVT-023(fail) |
| STATE-004 | AdversarialReview | Active RED+GREEN passes exist; awaiting/holding a verdict; `current_stage=adversarial`. Not approved yet. | EVT-006, EVT-013, EVT-015, EVT-016, EVT-019, EVT-021, EVT-020 |
| STATE-005 | PreparePR | Active adversarial approval exists; packaging PR; `current_stage=prepare_pr`. Not yet awaiting human merge. | EVT-008, EVT-017, EVT-020, EVT-021 |
| STATE-006 | AwaitingHITLMerge | PR prepared; `current_stage=hitl_merge_checkpoint`; `delivery_state=awaiting_hitl_merge_approval`. No merge approval yet. | EVT-009, EVT-017, EVT-020 |
| STATE-007 | LandDeploy | HITL merge approval active; `current_stage=land_deploy`. Merge/deploy in progress; not closed. | EVT-010, EVT-017, EVT-020 |
| STATE-008 | Closeout | Delivery resolved (merged/deployed OR deferred OR blocked-with-evidence); `current_stage=closeout`. Retro not yet recorded. | EVT-011 |
| STATE-009 | Complete | Closeout recorded. Terminal. No further pass claims. | — |
| STATE-010 | ManualContinuation | Orchestration stopped with a structured next action; human continues out of band. Terminal for the automated pass. | — |
| STATE-011 | Abandoned | `exit_orchestration` recorded; work item abandoned. Terminal. | — |

Blocked/repairing are `lifecycle_state` overlays a stage holds while a blocker or `changes_requested` is active; they resolve via repair evidence, reroute, waiver, or escape. They are not separate nodes to avoid a combinatorial explosion (see `transitions.md` default rejection policy).

## Events

| ID | Event | Triggered by | Payload | Notes |
|----|-------|--------------|---------|-------|
| EVT-001 | create_work_item | A9/A1 | source request, intent, stage_plan | → route card create. |
| EVT-002 | route_card_validated | A10 | route card digest | GUARD-001. |
| EVT-004 | red_result | A3→A1→A10 | command evidence + `expected_failure_result` | Advances on GUARD-002; else FM-002. |
| EVT-005 | green_result | A4→A1→A10 | command evidence | GUARD-003; else FM-003/FM-004. |
| EVT-006 | verdict_result | A5→A1→A10 | verdict (approve/changes_requested/cannot_judge) | GUARD-004/005/006. |
| EVT-008 | prepare_pr_result | A6→A1→A10 | branch/gate/package/PR-draft evidence | GUARD-008. |
| EVT-009 | hitl_merge_approval | A9 | `pr_number`, `head_sha`, `expires_at` | GUARD-009; INV-008. |
| EVT-010 | land_deploy_result | A7→A1→A10 | merge/deploy/blocker evidence | GUARD-009/010/014. |
| EVT-011 | closeout_result | A8→A1→A10 | retro evidence or deferred reason | REQ-012. |
| EVT-012 | reroute_to_test_writer | A1 | reason | GREEN needs test change; consumes budget (GUARD-007). |
| EVT-013 | reroute_to_code_writer | A1 | finding owner | changes_requested repair (REQ-005). |
| EVT-015 | cannot_judge | A5→A1→A10 | reason | GUARD-006 (missing workproduct=budget) vs provider-timeout (no budget). |
| EVT-016 | provider_failure | A5/A7 | error | Blocks without budget (FM-007). |
| EVT-017 | defer_delivery | A9/policy | reason | → deferred terminal-local (REQ-012). |
| EVT-018 | manual_patch_authorized | A9 | scope | Orchestrator edit allowed; independent re-review required (Q-010). |
| EVT-019 | user_waiver | A9 | scope, predicate_ids, expiry | Unblocks explicit predicates only; cannot waive merge/RED/GREEN/stale (02B rule 11). |
| EVT-020 | exit_orchestration | A9 | reason | → Abandoned or ManualContinuation. |
| EVT-021 | route_update | A1/A9/script | field_paths, prev/new digest | Policy-gated (REQ-011); may stale review/delivery evidence. |
| EVT-023 | subject_drift_detected | A10 | stale evidence ids | FM-004; E_STALE_SUBJECT. |

## AI-assisted edges

| ID | Edge | Judgment the LLM makes | Deterministic fallback | Human review needed? |
|----|------|------------------------|------------------------|----------------------|
| AI-001 | Planning (A2) | Draft stage plan & acceptance criteria | Route-card schema validates; acceptance criteria are human-owned via EVT-021 | Yes — human owns intent. |
| AI-002 | RED authoring (A3) | Which failing test proves the behavior | RED passes only when `expected_failure_result.matched=true` and no unexpected infra patterns; else FM-002 | No — predicate decides. |
| AI-003 | GREEN (A4) | Implementation that passes RED | GREEN command exit code + role-boundary predicate decide, not the role's claim | No. |
| AI-004 | Adversarial verdict (A5) | approve / changes_requested / cannot_judge | Verdict rejected unless `rubric_ids` valid+non-empty and bound to review-package digest + review head; reducer adjudicates; **AI does not decide merge** | No per-verdict; HITL merge is the human backstop. |
| AI-005 | PR prep (A6) | PR body / compare guidance | Branch/gate status is deterministic; PR prose is advisory | No. |
| AI-006 | Land/deploy summary (A7) | Summarize CI/review/remote state | Merge blocked without HITL head match; deploy blocked without contract + health pass; remote text untrusted | Yes — HITL merge approval. |
| AI-007 | Closeout (A8) | Propose lessons | Lessons are proposals; governance change needs human approval (INV-017) | Yes for governance changes. |

**AI boundary rule:** AI never decides authorization (delivery authority / capability mode — human-owned), persistence integrity (append-only ledger + reducer), or merge safety (HITL + deterministic head match). It proposes; the reducer records; the workflow controls; the tests prove.

## Invariants
See `invariants.md`.

## Open questions
See `open-questions.md`. Q-001 (stage-attempt subject locking) and Q-002 (review-head == merge-head) are load-bearing and block Ticket 04 fixture materialization.
