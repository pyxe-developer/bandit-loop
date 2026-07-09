# Invariants

Each is phrased as something that is **always** true for an active work item.

| ID | Invariant | Why it must hold | Enforced by | Tested by |
|----|-----------|------------------|-------------|-----------|
| INV-001 | The orchestrator never authors product code, tests, or verdicts on its own work, and never merges around a failed gate. | Separation of duties is the whole trust story; a self-approving orchestrator makes every gate theater. | GUARD-015; role_boundaries; `manual_patch` requirement | TEST-032 |
| INV-002 | A stage advances only on evidence that is active, non-stale, and names claim + subject + actor + result. | Advancement on prose is how gates get bypassed. | Reducer (decision-table); GUARD-011 | TEST-001, TEST-004 |
| INV-003 | An active RED pass for a work item exists before any GREEN pass is admissible. | TDD proof requires the test to fail first. | Reducer `green` admissibility; GUARD-003 | TEST-013 |
| INV-004 | `code_writer` never edits `tests/**`; `test_writer` never edits `src/**` — unless a reroute is recorded. | Prevents "edit the test to make GREEN pass" and vice versa. | role_boundaries; reducer forbidden-path check | TEST-010, TEST-011 |
| INV-005 | The adversarial reviewer is read-only (`can_edit == []`). | A reviewer that can edit can launder its own findings. | role_boundaries; reducer | TEST-014 |
| INV-006 | The evidence ledger is append-only; roles never hand-edit it; only scripts append, atomically and file-locked. | The ledger is the trust root; hand edits destroy auditability. | protected_paths (`evidence.jsonl`); script atomic append; 02B rule 13 | TEST-040 |
| INV-007 | Reduction is authoritative by append order; `created_at` is advisory and cannot reorder evidence. | `created_at` is actor-supplied; ordering must not be gameable. | Reducer rule 2; `W_CREATED_AT_BACKDATED` | TEST-041 |
| INV-008 | A merge occurs only with a HITL `approval` event whose `pr_number` and `head_sha` equal the route-card `expected_head_sha` and the remote PR head, and is unexpired. | Merge is the irreversible, outward-facing act; the human authorizes the exact artifact. | GUARD-009; land_deploy admissibility | TEST-020, TEST-021 |
| INV-009 | A deploy occurs only when the route card names a `deploy_contract` and health evidence passes. | Ungated deploy is an explicit non-goal. | GUARD-010; T-015 | TEST-022 |
| INV-010 | In `assisted`/`manual` mode, no surface (plugin.json, agents/openai.yaml, README, role prompt, route-card markdown) claims sandbox, model, tool-policy, or role isolation. | Phase-0 proved packaging cannot enforce isolation; a false claim is a safety lie. | 02E honesty check; release-blocking warning | TEST-034 |
| INV-011 | `capability_mode=enforced` is valid only with active, non-stale install-agent validation evidence (`subject_scope=agent_config`); otherwise the workflow fails closed. | Enforced separation must be proven, not asserted. | GUARD-012; 02E fail-closed | TEST-030 |
| INV-012 | `work_item_id`, `source.request`, `subject.base_ref`, `subject.head_ref` never change in place; `capability_mode` and `delivery_authority` change only via an authorized `route_update`. | Mutable identity/authority makes prior gate results meaningless. | 02A update policy; digest check | TEST-031 |
| INV-013 | Every route-card mutation records previous and new route-card digest, actor, and reason. | Silent mutation breaks the audit chain and enables authority creep. | `route_update` payload; `E_ROUTE_CARD_DIGEST_MISMATCH` | TEST-035 |
| INV-014 | The repair-loop budget is parent-keyed to the work item and never resets on reroute. | Otherwise infinite repair loops evade the budget by rerouting. | Reducer rule 8; `stage_attempt_id` keying | TEST-042 |
| INV-015 | Remote/PR/CI/comment text is untrusted input and never an instruction that changes scope or authority. | Prompt-injection via PR comments is a real attack surface. | 02D delivery blocker `untrusted_remote_input`; land_deploy | TEST-023 |
| INV-016 | A passing stage's evidence stays active across later commits in other stages: RED at its pre-fix head and GREEN at its post-fix head are both active prerequisites at adversarial. | Without this, normal two-commit TDD self-blocks (the bug the amendment fixed). Resolved by Q-001 (accepted): the per-attempt subject lock keeps each stage's pass bound to its own head. | Reducer rules 6–7; per-attempt subject lock (GUARD-017) | TEST-006 |
| INV-017 | Closeout records lessons as proposals; governance/process changes take effect only on explicit human approval. | The agent proposes; humans own process change. | closeout admissibility; INV-001 | TEST-024 |
| INV-018 | One work item owns exactly one `.codex-bandit/work/<work_item_id>/` directory holding its route card, ledger, attempts, and budget. | Shared/duplicated state destroys parent-keying and auditability. | route-card path rule; script write-scoping | TEST-043 |

## Guards (referenced by `transitions.md`)

| ID | Guard | True when | On false |
|----|-------|-----------|----------|
| GUARD-001 | route_card_valid | All required 02A fields present and well-typed | Block; exit 2; `E_ROUTE_CARD_*` |
| GUARD-002 | red_admissible | `actor.role=test_writer`, expected failing exit code, `expected_failure_result.matched=true`, `unexpected_patterns` empty, no `src/**` edits, valid `recorded_by` | Block; `E_RED_UNEXPECTED_FAILURE` |
| GUARD-003 | green_admissible | Prior active RED pass, `actor.role=code_writer`, success exit, no `tests/**` edits | Reroute test_writer or block |
| GUARD-004 | adversarial_approve_admissible | Active RED+GREEN passes (may be different attempt heads), `verdict=approve`, `rubric_ids` valid+non-empty, bound to review-package digest + review head | Reject verdict |
| GUARD-005 | changes_requested_valid | Verdict has ≥1 finding with owner role | Reject malformed verdict |
| GUARD-006 | cannot_judge_missing_workproduct | `cannot_judge` caused by missing/invalid work product | consumes budget |
| GUARD-006b | cannot_judge_provider | `cannot_judge`/failure caused by provider/timeout | blocks, budget unchanged |
| GUARD-007 | repair_budget_available | `used_total < max_total` and `per_stage` limit not exceeded | Escalate `block_and_ask_human` |
| GUARD-008 | pr_create_authorized | `allow_pr_create` AND (`allow_branch_push` OR branch exists remotely) | Block; `fixture_02a_invalid_pr_create_without_push_or_remote_branch` |
| GUARD-009 | hitl_merge_match | `pr_number` + `approval.head_sha` + route-card `expected_head_sha` + remote head all equal; unexpired; `actor.role=human` | Merge blocked |
| GUARD-010 | deploy_contract_present | Route card names a `deploy_contract` and health passes | Delivery blocked |
| GUARD-011 | not_stale | Evidence fresh per its stage binding (command→attempt subject; review/approval→expected_head_sha) | `E_STALE_SUBJECT`; exit 3 |
| GUARD-012 | enforced_validated | Mode≠enforced, OR active non-stale install-agent validation for all enabled roles | Fail closed; `E_ENFORCED_MODE_NOT_VALIDATED` |
| GUARD-014 | delivery_authority_grants(op) | Route-card `delivery_authority` grants the specific op | Block; agent cannot self-expand authority |
| GUARD-015 | manual_edit_authorized | Orchestrator edit is covered by a recorded `manual_patch` or reroute | Refuse edit |
| GUARD-016 | review_head_equals_merge_head | The HITL-approved head equals the last active adversarial-approved review head | **ACCEPTED (Q-002).** On drift: block `E_UNREVIEWED_MERGE_HEAD` and route incremental re-review. Sole escape: one explicit, closeout-flagged human `user_waiver` scoped to the exact `base..head` delta — never bypasses the HITL approval itself. |
| GUARD-017 | attempt_subject_from_actual_head | Command evidence `subject.head_sha` matches the attempt's locked subject | **ACCEPTED (Q-001).** The appending script stamps `head_sha` from real `git rev-parse HEAD` at append (never from dispatch `expected_head_sha`); the first `command` record of a `stage_attempt_id` (append order) locks the attempt subject; tree drift between command run and append blocks. |
