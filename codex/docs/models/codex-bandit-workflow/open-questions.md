# Open Questions

Proposed defaults are proposals only; they are **not** baked into the model until
a human decides. Q-001 and Q-002 are load-bearing and block Ticket 04 fixture
materialization (they carry into `GUARD-016`, `GUARD-017`, `INV-016`, and
`TEST-060`/`TEST-061`).

## Decisions (2026-07-09, Matt)

| ID | Decision | Refinement beyond the proposed default |
|----|----------|----------------------------------------|
| Q-001 | **Accepted.** Stamp `subject.head_sha` from real `git rev-parse HEAD` at append; first `command` record of a `stage_attempt_id` (append order) locks the attempt subject. | Hardening: reject if the working tree moved between command execution and append (dirty/drift check), so the stamped head is the tree that was actually tested. Reducer stays pure over the ledger. GUARD-017 + INV-016 now firm. |
| Q-002 | **Accepted, option (a).** HITL-approved head must equal the last active adversarial-approved review head; on drift, `hitl_merge_checkpoint` blocks `E_UNREVIEWED_MERGE_HEAD` and routes incremental re-review. | Sole escape: one explicit, closeout-flagged human `user_waiver` scoped to the exact `base..head` delta. It records conscious human acceptance of unreviewed code; it does **not** bypass the HITL approval. GUARD-016 now firm. |
| Q-009 | **Accepted.** Budget exhaustion holds the stage `blocked` for a human decision; no silent pass; resolves to `ManualContinuation` if the human does not act. | Constraint: only a human can raise `max_total` (route-card field via authorized `route_update`); the agent cannot expand its own repair budget. |
| Q-010 | **Accepted.** Independence = verdict from `adversarial_reviewer` ≠ the manual_patch editor, bound to a new review-package digest, `identity_strength` recorded. | Honesty: in assisted mode this is `declared` (process-level) independence only. `manual_patch` is scoped to explicit paths, consumed on use, and must be re-authorized for later edits. It always sets a closeout flag for explicit human sign-off and forces the HITL merge checkpoint (cannot ride a delivery-deferred/auto path). Real independence needs an installed read-only reviewer agent (Q-006). |
| Reviewer scope | **Confirmed: single adversarial reviewer for V1.** Correctness gating rests on deterministic predicates (`expected_failure`, exit codes, role boundaries) that don't involve the reviewer; the reviewer judges quality/bypass-risk; merge has the human backstop. | Risk-tiered multi-reviewer deferred → **Q-011** (roadmap, non-blocking). |

New error codes introduced by these decisions: `E_UNREVIEWED_MERGE_HEAD` (Q-002),
`E_REPAIR_BUDGET_EXHAUSTED` (already in `machine.ts`, confirmed by Q-009).

Q-003, Q-004, Q-005 remain open for GPT-5.5's Ticket 02 amendment. Q-006–Q-008
remain deferred to their owning tickets.

| ID | Question | What it blocks | Proposed default | Owner | Decision |
|----|----------|----------------|------------------|-------|----------|
| Q-011 | Should high-risk work items get a second independent reviewer (risk-tiered review), and what tiers a work item as high-risk? | Future review-topology contract; not V1. | Add a risk-tiering field to the route card that can dispatch N independent reviewers with a quorum rule; default tier = single reviewer. | Human (roadmap) | Deferred (non-blocking for V1). |

| ID | Question | What it blocks or changes | Proposed default | Owner | Decision |
|----|----------|---------------------------|------------------|-------|----------|
| Q-001 | How is a stage-attempt's subject head established, stamped, and stored, so the reducer can detect "conflicts with the locked subject for its own `stage_attempt_id`"? 02C role output carries no subject, and the GREEN dispatch `subject.expected_head_sha` is the pre-fix head. | The entire multi-commit RED/GREEN fix (INV-016), the reducer staleness rule (GUARD-017, decision-table GREEN row), Ticket 04 reducer, Ticket 05 orchestrator. | Product command evidence `subject.head_sha` is stamped by the appending script from the **actual repo HEAD at command execution time**, never copied from the dispatch `expected_head_sha`. The first command evidence of a `stage_attempt_id` locks that attempt's subject; later same-attempt product evidence must match it or reduce to `stale`. | Human + GPT-5.5 (Ticket 02) | |
| Q-002 | Must the HITL-approved head equal the last active adversarial-approved review head? Today `land_deploy` admissibility requires an active HITL approval but not an active adversarial approval at the merge head, and the 02D fixture shows review@`bbbb`, approval@`cccc`. | Delivery safety (INV-008 scope), `GUARD-016`, `hitl_merge_checkpoint`/`land_deploy` admissibility, `TEST-060`. | Require merge head == last active adversarial-approved review head; a head advance past the reviewed head forces re-review before `hitl_merge_checkpoint` can pass. If instead an unreviewed human-approved delta is intentionally allowed, record it as a named limitation with a Ticket 10 pressure test. | Human (delivery safety call) | |
| Q-003 | Where do enforced `actor` identity fields (`agent_address`, `agent_set_id`, `config_digest`, `session_id`) live in the 02B event schema? Currently only in 02E prose. | Ticket 04 evidence validator, Ticket 08. | Add an `actor` enforced-identity conditional extension to the 02B schema referencing the 02E fields. | GPT-5.5 (Ticket 02) | |
| Q-004 | Is there a valid **local, non-delivery** route-card fixture exercising the false branch of the conditional `enabled_stages` rule (gates absent)? | Ticket 04/05 coverage of the conditional rule; what "minimal" means. | Add `fixture_02a_valid_minimal_local_no_delivery` (no delivery authority, no delivery gates) and treat it as the true minimal; keep the full-delivery one as a separate fixture. | GPT-5.5 (Ticket 02) | |
| Q-005 | Which `subject_scope`/`subject` requiredness applies to `transition`, `route_update`, `waiver`, and `note` records that have no meaningful product head? | Ticket 04 validator strictness. | `subject` is required only for `command`/`verdict`/`approval`/delivery records; other record types set `subject_scope=product` without a head-bound `subject` (or a `none` scope). | GPT-5.5 (Ticket 02) | |
| Q-006 | Exact TOML agent schemas and install/uninstall safety for `install-agents`. | Ticket 08 enforced mode; INV-011 validation shape. | Defer to Ticket 08 spike against the 02E name/identity contract; do not change 02E addresses. | Human + Ticket 08 | |
| Q-007 | Where does personal plugin marketplace metadata live for this plugin? | Install/update flow (Ticket 03 scaffold). | `~/.agents/plugins/marketplace.json` per the phase-0 scaffold-naming note; provisional for repo/team marketplace. | Human | |
| Q-008 | Should optional MCP ship after script contracts stabilize, and only as a script wrapper? | Ticket 09 scope; release shape. | Defer; MCP wraps scripts only, no second behavioral surface. | Human | |
| Q-009 | On repair-budget exhaustion under `escalation_policy=block_and_ask_human`, what exact terminal/holding state results? | `T-023`, orchestrator escalation behavior. | Hold the stage in `blocked` awaiting a human decision (waiver, manual_patch, reroute with explicit budget increase, or exit_orchestration); no silent pass. | Human | |
| Q-010 | After `manual_patch`, the tech plan requires "independent adversarial review before pass" — but in assisted mode the reviewer is AI and the orchestrator made the edit. What makes the review "independent" enough to trust? | `T-020`, INV-001 integrity, AI-004 boundary. | Require the post-`manual_patch` verdict from a distinct actor/session bound to the new review-package digest, and flag manual-patch work items for human attention at closeout. | Human | |

## Conflicts between intended and current behavior

None blocking. The amended Ticket 02 and the tech plan agree. The only residual
tension is Q-002: the tech plan's delivery-safety intent ("merge requires a HITL
approval bound to PR/head SHA") is satisfied literally, but the contract does not
yet guarantee the approved head was the reviewed head — the model surfaces this
rather than smoothing it over.
