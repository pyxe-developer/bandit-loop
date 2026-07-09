# Transitions

State IDs and event IDs are defined in `MODEL.md`. Guard IDs are defined in
`invariants.md` (guards section) and `decision-table.md`. The orchestrator applies
a transition only after `verify-stage` (A10) returns a status for the current
stage; the reducer status is carried on the event payload, so the machine stays
pure (see `machine.ts`).

## Legal transitions

| ID | From state | Event | Guard(s) | To state | Side effects | Reason | Source |
|----|------------|-------|----------|----------|--------------|--------|--------|
| T-001 | STATE-000 NotCreated | EVT-001 create_work_item | GUARD-001 | STATE-001 Planned | FX-001 append plan evidence, FX-003 write route card | A work item begins from a validated route card, not chat | REQ-001, 02A |
| T-002 | STATE-001 Planned | EVT-002 route_card_validated | GUARD-001, GUARD-012 | STATE-002 Red | FX-006 dispatch test_writer | Plan complete; route to RED first | REQ-003 |
| T-003 | STATE-002 Red | EVT-004 red_result | GUARD-002, GUARD-011, GUARD-017 | STATE-003 Green | FX-001, FX-002, FX-003 advance, FX-006 dispatch code_writer | RED passed for the intended failure; GREEN may start | REQ-003, REQ-010, 02B |
| T-004 | STATE-002 Red | EVT-004 red_result | ¬GUARD-002 (unexpected failure) | STATE-002 Red (blocked) | FX-008 blocker E_RED_UNEXPECTED_FAILURE | RED failed for an unrelated/infra reason; not proof | REQ-010, FM-002 |
| T-005 | STATE-003 Green | EVT-005 green_result | GUARD-003, GUARD-011, GUARD-017 | STATE-004 AdversarialReview | FX-001, FX-002, FX-003, FX-005 build review package, FX-006 dispatch reviewer | GREEN passed without forbidden test edits | REQ-002, REQ-004, 02B |
| T-006 | STATE-003 Green | EVT-005 green_result | ¬GUARD-003 (forbidden test edit) | STATE-002 Red (repairing) | FX-007 consume budget, FX-008 blocker E_FORBIDDEN_PATH_CHANGED, FX-006 reroute test_writer | Code writer touched tests; route back through test_writer | REQ-004, FM-003 |
| T-007 | STATE-004 AdversarialReview | EVT-006 verdict_result (approve) | GUARD-004 | STATE-005 PreparePR | FX-001, FX-002, FX-003 | Independent read-only approval bound to the review subject | REQ-002, REQ-004, 02D |
| T-008 | STATE-004 AdversarialReview | EVT-006 verdict_result (changes_requested) | GUARD-005, GUARD-007 | STATE-003 Green (repairing) | FX-007 consume budget, FX-008 route to finding owner, FX-006 reroute code_writer | Findings block advancement; bounded repair to owner | REQ-005, FM-003 |
| T-009 | STATE-004 AdversarialReview | EVT-006/EVT-015 cannot_judge (missing workproduct) | GUARD-006, GUARD-007 | STATE-004 (blocked) | FX-007 consume budget, FX-008 route build-review-package | Reviewer lacks a package; regenerate then re-review | 02B rule 10, FM-008 |
| T-010 | STATE-004 AdversarialReview | EVT-016 provider_failure | GUARD-006b | STATE-004 (blocked) | FX-008 blocker (retryable), budget unchanged | Provider/timeout is not a work-product failure | 02B rule 10, FM-007 |
| T-011 | STATE-004 AdversarialReview | EVT-013 reroute_to_test_writer | GUARD-007 | STATE-002 Red (repairing) | FX-007, FX-006 reroute test_writer | Review shows the test surface is wrong | REQ-004 |
| T-012 | STATE-005 PreparePR | EVT-008 prepare_pr_result | GUARD-008, GUARD-014 | STATE-006 AwaitingHITLMerge | FX-001, FX-003, FX-009 push/create PR within authority | PR is packaged and remote-ready | REQ-006, 02D |
| T-013 | STATE-006 AwaitingHITLMerge | EVT-009 hitl_merge_approval | GUARD-009, GUARD-016 | STATE-007 LandDeploy | FX-001 append approval, FX-003 delivery_state=merge_approved | Human approved the exact PR/head; merge may proceed | REQ-006, INV-008 |
| T-014 | STATE-007 LandDeploy | EVT-010 land_deploy_result (merged[/deployed]) | GUARD-009, GUARD-010, GUARD-014 | STATE-008 Closeout | FX-009 merge, FX-010 deploy+health, FX-001, FX-003 delivery_state=merged/deployed | Merge/deploy succeeded under authority + health | REQ-006 |
| T-015 | STATE-007 LandDeploy | EVT-010 land_deploy_result (blocker) | ¬GUARD-010 or CI/health fail | STATE-007 (delivery_blocked) | FX-008 delivery blocker, no merge/bypass | CI/deploy/health failing is a hard block, not a bypass | REQ-006, FM-012 |
| T-016 | STATE-005/006/007 | EVT-017 defer_delivery | GUARD-014 | STATE-008 Closeout | FX-003 delivery_state=delivery_deferred | Deferred delivery is a valid terminal-local outcome | REQ-012 |
| T-017 | STATE-008 Closeout | EVT-011 closeout_result | GUARD (retro bound to final state; deferred needs reason) | STATE-009 Complete | FX-001, FX-003 lifecycle_state=complete | Outcome + lessons recorded honestly | REQ-012, INV-017 |
| T-018 | STATE-001..006 | EVT-020 exit_orchestration | — | STATE-011 Abandoned | FX-001 transition evidence, FX-012 stop | User ends the automated pass | tech plan escape |
| T-019 | STATE-001..006 | EVT-020 exit_orchestration (manual continue) | — | STATE-010 ManualContinuation | FX-012 stop with next action | User continues out of band | tech plan escape |
| T-020 | STATE-003 Green | EVT-018 manual_patch_authorized | GUARD-015 | STATE-004 AdversarialReview | FX-001 record manual_patch, FX-006 dispatch reviewer | Orchestrator edit is authorized; independent review still required | tech plan escape, Q-010 |
| T-021 | STATE-004 | EVT-019 user_waiver | GUARD (waiver.scope + expiry + human; not merge/RED/GREEN/stale) | STATE-005 PreparePR | FX-001 waiver evidence | User owns a bounded risk decision; not a technical pass | 02B rule 11 |
| T-022 | any active stage | EVT-021 route_update (review/delivery head) | GUARD-011, GUARD-016, digest check | same state | FX-003 update route card, FX-011 supersede stale review/delivery evidence, FX-013 warnings | Controlled subject move with digest + supersession impact | REQ-011, 02A |
| T-023 | STATE-004 | EVT-006 verdict_result (approve) | GUARD-007 exhausted | STATE-004 (blocked, escalate) | FX-008 block_and_ask_human | Budget exhausted routes to human, not silent pass | REQ-013, Q-009 |

## Invalid / impossible transitions (safety-relevant)

| ID | From state | Event | Why it cannot happen | Where it is rejected | Test ID |
|----|------------|-------|----------------------|----------------------|---------|
| X-001 | STATE-002 Red | EVT-005 green_result with no active RED pass | RED must precede GREEN | GUARD-003 / reducer; exit 3 | TEST-013 |
| X-002 | any | EVT-006 verdict where `actor.role != adversarial_reviewer` | Only the read-only reviewer verdicts | GUARD-004; reducer admissibility | TEST-014 |
| X-003 | STATE-004 | EVT-006 approve with empty/invalid `rubric_ids` or stale review subject | Approval must bind to rubric + current review head | GUARD-004; 02D | TEST-015 |
| X-004 | STATE-006 | merge with no HITL approval event | Merge requires HITL bound to exact PR/head | GUARD-009; land_deploy admissibility | TEST-020 |
| X-005 | STATE-006/007 | EVT-009 approval where `approval.head_sha != expected_head_sha` (or expired) | Approval must match the exact current head | GUARD-009; FM-011 | TEST-021 |
| X-006 | STATE-007 | merge/deploy while CI/health failing | No bypass of failed checks | T-015; FM-012 | TEST-022 |
| X-007 | any | GREEN command evidence with `actor.role != code_writer` OR editing `tests/**` | Role boundary violation | GUARD-003; reducer; INV-004 | TEST-011 |
| X-008 | any | RED evidence with `actor.role != test_writer` OR editing `src/**` | Role boundary violation | GUARD-002; reducer; INV-004 | TEST-010 |
| X-009 | any | `capability_mode=enforced` with no active install-agent validation | Enforced claims require validated agents; else fail closed | GUARD-012; 02E | TEST-030 |
| X-010 | any | direct route-card edit to `work_item_id`/`source.request`/`base_ref`/`head_ref` | Immutable after creation | 02A update policy; INV-012 | TEST-031 |
| X-011 | any | orchestrator edits `src/**`/`tests/**` with no `manual_patch`/reroute recorded | Orchestrator does not implement | GUARD-015; INV-001 | TEST-032 |
| X-012 | any | `waiver` used to pass merge / stale subject / missing RED-GREEN | Waivers cannot convert failed technical evidence to pass | 02B rule 11 | TEST-033 |

## Default rejection policy

Every state/event combination not listed above is **rejected** by default. The
orchestrator holds the current state, appends a structured `blocker` (never an
implicit advance), and routes the owning role or the human. `machine.ts`
implements this as the `default` arm of the transition switch returning the
unchanged state plus an `E_UNSUPPORTED_TRANSITION` effect.
