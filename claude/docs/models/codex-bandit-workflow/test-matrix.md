# Test Matrix

Derived directly from transitions (`T-*`, `X-*`), guards (`GUARD-*`), failure
modes (`FM-*`), and invariants (`INV-*`). No orphan tests: every row cites a
source. Classes: happy-path, guard-rejection, invalid-transition, failure-mode,
invariant, AI-assisted-edge.

| ID | Source | Scenario | Preconditions | Event | Guard state | Expected transition/status | Expected side effects | Class | Priority |
|----|--------|----------|---------------|-------|-------------|----------------------------|-----------------------|-------|----------|
| TEST-001 | T-002,INV-002 | Plan → Red on validated route card | route card valid | route_card_validated | GUARD-001 pass | STATE-001→STATE-002 | dispatch test_writer | happy-path | must-write-first |
| TEST-002 | T-003 | RED pass advances to Green | active plan | red_result (expected fail matched) | GUARD-002 pass | STATE-002→STATE-003 | append, advance, dispatch code_writer | happy-path | must-write-first |
| TEST-003 | T-005 | GREEN pass advances to review | active RED | green_result success | GUARD-003 pass | STATE-003→STATE-004 | build review package, dispatch reviewer | happy-path | must-write-first |
| TEST-004 | T-007,INV-002 | Approve advances to PreparePR | active RED+GREEN | verdict approve | GUARD-004 pass | STATE-004→STATE-005 | advance | happy-path | must-write-first |
| TEST-005 | T-012,T-013,T-014 | Full delivery happy path to Complete | approval present | prepare→hitl→land→closeout | all delivery guards pass | STATE-005→…→STATE-009 | push/PR, merge, deploy, closeout | happy-path | should-write |
| TEST-006 | INV-016,T-005,Q-001 | Multi-commit RED@aaaa + GREEN@bbbb both active at adversarial | RED then fix commit | verdict approve | GUARD-004,GUARD-017 | STATE-004→STATE-005 | none stale | invariant | must-write-first |
| TEST-010 | X-008,INV-004 | RED evidence by non-test_writer or editing src | red_result | red_result | GUARD-002 fail | blocked (role) | blocker | invariant | must-write-first |
| TEST-011 | X-007,INV-004 | GREEN edits tests to pass | green_result touches tests | green_result | GUARD-003 fail | STATE-003→STATE-002 (reroute) | E_FORBIDDEN_PATH_CHANGED, consume budget | guard-rejection | must-write-first |
| TEST-012 | T-004,FM-002,REQ-010 | RED fails for infra/syntax reason | red command exits 1, SyntaxError | red_result | GUARD-002 fail | blocked | E_RED_UNEXPECTED_FAILURE | failure-mode | must-write-first |
| TEST-013 | X-001,INV-003 | GREEN attempted with no active RED | no RED pass | green_result | GUARD-003 fail | blocked (exit 3) | blocker | invalid-transition | must-write-first |
| TEST-014 | X-002,INV-005 | Verdict by non-reviewer / reviewer edits files | verdict actor=code_writer | verdict | GUARD-004 fail | rejected | blocker | invalid-transition | must-write-first |
| TEST-015 | X-003 | Approve without rubric IDs or stale review head | verdict approve, empty rubrics | verdict | GUARD-004 fail | blocked | blocker | guard-rejection | must-write-first |
| TEST-016 | T-008,REQ-005 | changes_requested routes bounded repair | ≥1 finding | verdict changes_requested | GUARD-005,007 | STATE-004→STATE-003 | consume budget, reroute owner | happy-path | should-write |
| TEST-017 | T-009,FM-008 | cannot_judge (missing package) consumes budget | no review package | cannot_judge | GUARD-006 | STATE-004 blocked | consume budget, route build-package | failure-mode | should-write |
| TEST-018 | T-010,FM-007 | cannot_judge (provider timeout) keeps budget | provider timeout | provider_failure | GUARD-006b | STATE-004 blocked | budget unchanged | failure-mode | should-write |
| TEST-019 | T-023,FM-009,Q-009 | Repair budget exhausted escalates | used_total=max | reroute | GUARD-007 fail | STATE-004 blocked (escalate) | block_and_ask_human | failure-mode | should-write |
| TEST-020 | X-004,INV-008 | Merge without HITL approval | at land_deploy, no approval | land_deploy_result merge | GUARD-009 fail | blocked | E_MISSING_HITL_APPROVAL, no merge | invariant | must-write-first |
| TEST-021 | X-005,FM-011 | HITL approval wrong/expired head | approval head ≠ expected | hitl_merge_approval | GUARD-009 fail | merge blocked | blocker | guard-rejection | must-write-first |
| TEST-022 | X-006,FM-012,INV-009 | CI/deploy/health failing | health fail | land_deploy_result | GUARD-010 fail | STATE-007 delivery_blocked | delivery blocker, no bypass | failure-mode | must-write-first |
| TEST-023 | INV-015 | PR/CI comment tries to change scope | remote comment with instruction | land_deploy_result | — | untrusted, no scope change | summarize as untrusted fact | invariant | must-write-first |
| TEST-024 | T-017,INV-017 | Closeout lessons are proposals | delivery resolved | closeout_result | — | STATE-008→STATE-009 | proposals only | invariant | should-write |
| TEST-025 | T-016,REQ-012 | Deferred delivery reaches closeout | prepare_pr done | defer_delivery | GUARD-014 | →STATE-008 | delivery_deferred | happy-path | should-write |
| TEST-030 | X-009,INV-011 | Enforced mode without validation fails closed | mode=enforced, no evidence | route_card_validated | GUARD-012 fail | blocked | E_ENFORCED_MODE_NOT_VALIDATED | invariant | must-write-first |
| TEST-031 | X-010,INV-012 | Attempt to mutate immutable identity field | route_update on head_ref | route_update | policy reject | rejected | blocker | invariant | should-write |
| TEST-032 | X-011,INV-001 | Orchestrator edits code without manual_patch | active work item | orchestrator edit | GUARD-015 fail | refused | refuse edit | invariant | must-write-first |
| TEST-033 | X-012 | Waiver used to pass merge/RED/GREEN | user_waiver on merge | user_waiver | reject | rejected | blocker | guard-rejection | should-write |
| TEST-034 | INV-010 | Assisted surface claims sandbox isolation | README claims isolation | honesty check | fail | block/release-warning | honesty warning | invariant | must-write-first |
| TEST-035 | INV-013,FM-015 | route_update with wrong previous digest | stale digest | route_update | digest check fail | blocked | E_ROUTE_CARD_DIGEST_MISMATCH | failure-mode | should-write |
| TEST-040 | INV-006,FM-006 | Truncated/partial JSONL line | bad final line | reduce | G1 | blocked | E_LEDGER_MALFORMED | failure-mode | must-write-first |
| TEST-041 | INV-007,REQ-009 | Backdated created_at does not reorder | later blocker, earlier ts | reduce | G4 | blocker wins by append order | W_CREATED_AT_BACKDATED | invariant | must-write-first |
| TEST-042 | INV-014,REQ-013 | Reroute does not reset budget | loop adversarial→green | reroute | GUARD-007 | budget increments | consume budget | invariant | should-write |
| TEST-043 | INV-018 | Duplicate/conflicting evidence id | same id, diff payload | reduce | G2 | blocked | E_DUPLICATE_EVIDENCE_ID | failure-mode | should-write |
| TEST-050 | AI-004 | Reviewer approves without reading diff (no digest binding) | verdict lacks review pkg digest | verdict | GUARD-004 fail | rejected | blocker | AI-assisted-edge | must-write-first |
| TEST-051 | AI-002 | test_writer claims RED but predicate mismatch | expected_failure_result.matched=false | red_result | GUARD-002 fail | blocked | E_RED_UNEXPECTED_FAILURE | AI-assisted-edge | should-write |
| TEST-060 | Q-002/GUARD-016 | Head advances after approval; re-review required | approval head ≠ reviewed head | hitl_merge_approval | GUARD-016 (accepted) | blocked `E_UNREVIEWED_MERGE_HEAD`, route re-review | blocker | guard-rejection | must-write-first |
| TEST-060b | Q-002 escape | Human waiver accepts an unreviewed delta | scoped `base..head` waiver | user_waiver | legal waiver | merge allowed, closeout-flagged | invariant | should-write |
| TEST-061 | Q-001/GUARD-017 | GREEN stamped from dispatch head not actual head, or tree moved before append | evidence head = dispatch expected | green_result | GUARD-017 (accepted) | stale/blocked | blocker | guard-rejection | must-write-first |

The first implementation pass writes every **must-write-first** test before code.
Q-001 and Q-002 are now decided (see `open-questions.md` → Decisions), so
TEST-060/060b/061 are the fixtures that pin those decisions and are ready to
author once the Ticket 02 contract text absorbs GUARD-016/017.
