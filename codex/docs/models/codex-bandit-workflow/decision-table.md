# Decision Table — `verify-stage` reducer stage-status derivation

This is the adjudication layer the state machine consumes. `verify-stage` is a
**pure reducer** over the route card + append-ordered event stream. It returns a
stage status; the orchestrator (state machine) maps that status to a transition.
Reducer statuses: `not_started, pass, fail, changes_requested, cannot_judge,
blocked, stale, deferred, abandoned` (02B).

## Global ledger conditions (evaluated before any stage rule)

| # | Condition | Result | Source |
|---|-----------|--------|--------|
| G1 | Any line is non-JSON / truncated | `blocked` `E_LEDGER_MALFORMED` | 02B rule 1, 13 |
| G2 | Duplicate `id`, not byte-identical | `blocked` `E_DUPLICATE_EVIDENCE_ID` | 02B rule 4 |
| G3 | Event `work_item_id` ≠ route card | reject event | 02B rule 3 |
| G4 | `created_at` moves backward vs prior append | keep append order; warn `W_CREATED_AT_BACKDATED` | 02B rule 2 (INV-007) |
| G5 | `supersedes[]` / supersession present | superseded evidence → inactive (audit-visible) | 02B rule 5 |

## RED (`stage=red`)

| actor.role | exit code | expected_failure_result.matched | unexpected_patterns | src edits | ⇒ status |
|------------|-----------|--------------------------------|---------------------|-----------|----------|
| test_writer | expected failing (e.g. 1) | true | empty | none | **pass** |
| test_writer | expected failing | false | — | none | **blocked** `E_RED_UNEXPECTED_FAILURE` |
| test_writer | expected failing | true | non-empty (infra error) | none | **blocked** `E_RED_UNEXPECTED_FAILURE` |
| test_writer | success (0) | — | — | none | **fail** (test did not fail) |
| ≠ test_writer | any | — | — | — | **blocked** (role) — X-008 |
| test_writer | any | — | — | edits `src/**` | **blocked** (forbidden path) |

## GREEN (`stage=green`)

| prior active RED pass | actor.role | exit code | test edits | attempt subject | ⇒ status |
|-----------------------|------------|-----------|------------|-----------------|----------|
| yes | code_writer | success | none | matches locked (Q-001) | **pass** |
| no | code_writer | success | none | — | **blocked** (RED missing) — X-001 |
| yes | code_writer | fail | none | — | **fail** |
| yes | code_writer | success | edits `tests/**` | — | **blocked** → reroute test_writer |
| yes | ≠ code_writer | — | — | — | **blocked** (role) — X-007 |
| yes | code_writer | success | none | conflicts with locked attempt subject | **stale** `E_STALE_SUBJECT` |

Note: a fresh GREEN pass does **not** stale the earlier RED pass (INV-016). RED
and GREEN legitimately bind to different heads.

## ADVERSARIAL (`stage=adversarial`)

| prior active RED+GREEN | verdict | rubric_ids | bound to review pkg digest + review head | ⇒ status |
|------------------------|---------|-----------|------------------------------------------|----------|
| yes | approve | valid, non-empty | yes | **pass** |
| yes | approve | empty/invalid OR stale head | — | **blocked** (invalid approval) — X-003 |
| yes | changes_requested (≥1 finding) | valid | yes | **changes_requested** → route owner |
| yes | cannot_judge (missing work product) | — | — | **cannot_judge**, budget consumed |
| yes | cannot_judge (provider/timeout) | — | — | **blocked**, budget unchanged |
| no (RED or GREEN stale/missing) | any | — | — | **blocked** (prereq) |
| — | verdict actor ≠ adversarial_reviewer | — | — | **blocked** (role) — X-002 |

## Later-record precedence & repair

| # | Condition | Result | Source |
|---|-----------|--------|--------|
| P1 | Later `blocked`/`changes_requested`/`cannot_judge` for same attempt after a `pass` | overrides the pass, unless superseded by a higher-attempt repair record | 02B rule 9 |
| P2 | Repair `verdict` claims to resolve findings but no `parent_record_id` | **blocked** | 02B rule 14 |
| P3 | Repair `command` missing `parent_record_id` | warning (not block) | 02B rule 14 |
| P4 | reroute adversarial→green | same parent-keyed budget increments (never resets) | 02B rule 8, INV-014 |

## DELIVERY (`prepare_pr`, `hitl_merge_checkpoint`, `land_deploy`, `closeout`)

| stage | condition | ⇒ status |
|-------|-----------|----------|
| prepare_pr | active adversarial approval + branch/gate/package/PR-draft evidence + GUARD-008 | **pass** |
| hitl_merge_checkpoint | `approval.kind=merge`, human actor, GUARD-009 (+ GUARD-016 if Q-002 accepted) | **pass** |
| hitl_merge_checkpoint | no approval OR head mismatch/expired | **blocked** — X-004/X-005 |
| land_deploy | active HITL approval + merge/deploy evidence, health pass | **pass** |
| land_deploy | CI/deploy/health failing OR no deploy contract for deploy | **blocked** (delivery_blocked) — X-006 |
| any delivery stage | `defer_delivery` recorded | **deferred** (terminal-local) — 02B rule 12 |
| closeout | retro bound to final state; deferred delivery needs deferred reason | **pass** |

## Enforced-mode overlay (applies before dispatch when `capability_mode=enforced`)

| condition | ⇒ result |
|-----------|----------|
| No active `installed_agents_validated` event | **blocked** `E_ENFORCED_MODE_NOT_VALIDATED` (fail closed) — X-009 |
| Agent-config digest/path/runtime drift | **blocked** `E_ENFORCED_AGENT_CONFIG_STALE` |
| Requested role has no installed-agent address | **blocked** `E_ENFORCED_AGENT_MISSING` |
| Runtime identity mismatch (role/address/config/set) | **blocked** `E_ENFORCED_IDENTITY_INVALID` |
| Product HEAD moved during GREEN/repair | **not** a staleness cause for agent-config evidence (subject_scope=agent_config) |

Impossible combinations are covered by the RED/GREEN/adversarial role rows above
and the default rejection policy in `transitions.md`.
