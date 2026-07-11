# Conveyor Protocol — canonical states, moves, budgets, statuses

The single reference for what the scorekeeper may authorize. Role prompts and the orchestrator
skill defer to this file; the ledger records against these names. Snapshotted per ticket with
the other assets.

## Lifecycle states

`queued · planning · testing · implementing · reviewing · pr-open · landing · landed-staging ·
deploy-failed · blocked · closed · canceled`

**State-change rule:** a `YES` opens an *outstanding action*; the `from → to` transition takes
effect **only at a `succeeded` result_close**. A `failed` close leaves the ticket in its
`from` state *by default* — but where a row's **On failure** column names an explicit failure
state (written `→ <state>`), that transition takes effect at the failed close and **overrides
the default**. Gate moves with branch-specific outcomes resolve their resulting state at
close, per branch.

## Legal moves

Every ledger `requested_move` uses an exact name from this table — the scorekeeper refuses any
other name. **Authorization evidence** must exist *before* the `YES` (it is what the proposal
references). **Result evidence** is produced *by* the authorized action and arrives at
result_close — never required at proposal time.

| Move | From → To (success) | Authorization prerequisites & evidence | Result evidence (at close) | On failure |
|---|---|---|---|---|
| `enter_conveyor` | queued → planning | none (first move); intended base = current staging HEAD | pinned SHA, worktree path, snapshot path | retry once, else `block_ticket` |
| `dispatch_issue_planner` | planning → planning | enter_conveyor closed | planner handoff received | per handoff status |
| `accept_handoff:<role>` | same-state | open dispatch for that role/attempt; the handoff text | validation: all required sections present, subject matches | NEEDS_CONTEXT/BLOCKED path per status mapping |
| `dispatch_plan_review` | planning → planning | plan artifact materialized; NEW reviewer agent id | verdict artifact | reviewer failure → fresh reviewer, no burn |
| `plan_gate` | approve: planning → testing | plan-review verdict artifact | none (gate resolves on the verdict) | changes_requested: **burn plan**; if budget_after > 0, authorizes one repair dispatch; if 0 → `block_ticket`. cannot_judge → `block_ticket` |
| `dispatch_test_writer` | testing → testing | plan_gate passed, or open repair authorization, or an explicit re-entry route (test mutation, test-touching rebase conflict) | test-writer handoff received | per handoff status |
| `verify_red` | testing → testing | accepted test-writer handoff; the exact failing-test command; subject worktree state | **orchestrator's own** failing-test run artifact (command, exit code, tail). Meaningful red = succeeded | not-meaningful red = failed: **burn test**; budget_after > 0 → repair dispatch, else `block_ticket` |
| `dispatch_test_review` | testing → testing | verify_red succeeded; RED artifact; NEW reviewer id | verdict artifact | reviewer failure → fresh reviewer, no burn |
| `test_gate` | approve: testing → implementing | test-review verdict artifact | approved-test checkpoint commit SHA (committed after YES) | changes_requested: **burn test**; budget_after > 0 → repair, else `block_ticket`. cannot_judge → `block_ticket` |
| `dispatch_code_writer` | implementing → implementing | test_gate passed, or open repair authorization, or an explicit re-entry route (semantic pr_mutation, code-touching rebase conflict, undeclared PR change); one candidate per dispatch | code-writer handoff received | per handoff status |
| `verify_green` | implementing → reviewing | accepted code-writer handoff; suite command; checkpoint SHA | **orchestrator's own** suite run artifact + test-surface diff vs checkpoint | red = failed: **burn code**; budget_after > 0 → repair, else `block_ticket`. Test mutation detected = failed, **no burn**, explicit failure state **→ testing**; next move `dispatch_test_writer` (restore or legitimize the mutated test surface), then the full testing chain — `verify_red` on the current test subject → `dispatch_test_review` → `test_gate` (new checkpoint) |
| `dispatch_impl_review` | reviewing → reviewing | verify_green succeeded; GREEN artifact; checkpoint diff; exact head SHA; NEW reviewer id | verdict artifact | reviewer failure → fresh reviewer, no burn |
| `impl_gate` | approve: reviewing → reviewing (ship-ready) | impl-review verdict artifact | none | changes_requested (code defect): **burn code**; explicit failure state **→ implementing**; budget_after > 0 → repair at `dispatch_code_writer`, else `block_ticket`. A6 test defect: no burn, explicit failure state **→ testing** → `dispatch_test_writer`. Requirements defect: escalate to user; on a recorded re-plan decision explicit failure state **→ planning**, else `block_ticket`. cannot_judge → `block_ticket` |
| `pr_creation` | reviewing → pr-open | impl_gate approved; reviewed SHA. **Atomic**: create PR + declared mechanical edits only | PR number/URL, post-edit head SHA, declared-edit list, CI run refs | failed: state unchanged; **burn ship**; budget_after > 0 → one retry proposal, else `block_ticket` |
| `pr_mutation` | pr-open → pr-open | open PR; the specific intended change (mechanical by content) | post-edit head SHA | mechanical failure: state unchanged, no burn, retry via new proposal. Semantic change detected: failed, **no burn**, explicit failure state **→ implementing**, **failure advancement = the new post-edit head** (the mutation landed a commit); next move `dispatch_code_writer` (own the delta — revert it or make it a proper candidate), then `verify_green` → `dispatch_impl_review` → `impl_gate` → `pr_resync` |
| `land_readiness` | pr-open → landing | pr_creation (or pr_resync/rebase_pr) closed; dispatch is read-only; subject = current PR head SHA **+ current staging HEAD SHA** | L1/L2/L3/**L4a**/L5 evidence artifact (records both the PR head and the staging HEAD it was checked against; L4b is a merge-act-time check, not part of readiness) | L-blocker found: failed, state stays pr-open, no burn. Base drift (staging moved past the checked HEAD) → `rebase_pr`. Undeclared/semantic change on the PR → as `pr_mutation`'s semantic branch (**→ implementing**, `dispatch_code_writer`, full chain, `pr_resync`). **CI red (L2 blocker): classified by local reproduction, not opinion.** The classification must ride in *this same* `land_readiness` close — so on a CI-red the land child returns L2-red evidence, the orchestrator materializes it but keeps `land_readiness` **outstanding**, runs the exact local reproduction while it is still open, and reports the L evidence **plus** the reproduction artifact together in one failed `result_close` carrying the cause/burn/state branch (a move closed merely as "CI red" cannot have its branch retroactively changed). The **reproduction artifact** minimum fields: the exact command run, the head SHA it ran on, exit code, failing-test/output tail, and a code|test|environmental verdict with the CI-log reference supporting it. Branch: reproduces as a **code** defect → **→ implementing**, `dispatch_code_writer`, full chain, `pr_resync`, **burn code**; reproduces as a **test** defect → **→ testing**, `dispatch_test_writer`, full chain, **burn test**; does **not** reproduce locally **and** CI logs show an infrastructure/transient cause (environmental, **no burn**) → `ci_recheck`; still red after `ci_recheck`, or ambiguous → `block_ticket`. Evidence gap → materialize and re-propose |
| `ci_recheck` | pr-open → pr-open | a `land_readiness` CI-red close whose reproduction evidence showed **no local failure + CI-infra cause**; actor = prepare-pr; subject = current PR head SHA (no tree change) | authorized head SHA (act-time verified still the PR head) + new CI run IDs + terminal status/conclusion | **no burn**; at most **one** `ci_recheck` per land attempt. Green → re-propose `land_readiness`. Still red → `block_ticket` (treated as irreducible) |
| `rebase_pr` | pr-open → pr-open | land_readiness failed with base-drift evidence; intent = rebase onto current staging HEAD, no semantic change | new PR head SHA + **orchestrator's own** full-suite run (green) on the new head + rebase diff showing no semantic delta | conflict touching production code: failed, **no burn**, explicit failure state **→ implementing**; `dispatch_code_writer` (conflict resolution as candidate) then `verify_green` → `dispatch_impl_review` → `impl_gate` → `pr_resync`. Conflict touching tests: **→ testing**, no burn; `dispatch_test_writer` then the full testing chain. Mechanical failure: state stays pr-open, retry via new proposal |
| `pr_resync` | reviewing → pr-open | impl_gate approved on the re-reviewed head **and** an open PR exists (no PR → `pr_creation`) | PR head SHA equals the re-reviewed SHA; CI run refs | failed: state unchanged; **burn ship**; budget_after > 0 → one retry proposal, else `block_ticket` |
| `merge` | landing → landed-staging | land_readiness succeeded; `YES` bound to the **exact PR head AND the exact staging HEAD** that passed readiness. At act time the role rechecks both (**L4b**: `gh pr view` head + `git rev-parse staging` both still equal the authorized SHAs) | **L4b revalidation evidence (both heads confirmed)** + merge commit SHA + `gh pr view` post-state | **Act-time precheck refusal (no burn):** PR head or staging HEAD drifted → failed, explicit failure state **→ pr-open**; staging drift → `rebase_pr` + fresh `land_readiness`; PR-head drift → fresh `land_readiness` (re-enter per cause if the head is an undeclared change). **Merge-command failure:** **burn ship**, explicit failure state **→ pr-open**; budget_after > 0 → fresh `land_readiness` + merge, else `block_ticket`. **Ambiguous forge outcome** (merge may have half-landed) → `reconciled-unknown` → `block_ticket` |
| `deploy` | landed-staging **or deploy-failed** → landed-staging | merge closed; operator config exists and names environment. **Never authorized by the merge YES** | deploy output + health-check result | failed: explicit failure state **→ deploy-failed** (overrides stay-in-from-state); **burn ship**. If budget_after > 0: next move is a new `deploy` proposal (retry) or `dispatch_closeout`. If budget_after = 0: the only legal next move is `block_ticket` — deploy-failed stays recorded as delivery evidence for the retro, and closeout proceeds from `blocked` |
| `dispatch_closeout` | terminal-ish state → same | ticket in landed-staging / deploy-failed / blocked / canceled | retro handoff received | per handoff status |
| `closeout` | → closed | accepted retro handoff (C1–C5) | retro artifact ref | failed: state unchanged; repair retro (no burn) |
| `cleanup` | closed → closed | C4 verified from ledger/evidence: merged, evidence materialized, deploy outcome recorded, **no outstanding action**. Blocked/failed tickets: refuse | deletion confirmation (worktree path gone) | failed: state unchanged; reconcile filesystem reality, retry once, else leave worktree and note |
| `block_ticket` | any → blocked | the triggering evidence (exhaustion, cannot_judge, BLOCKED handoff, reconciled-unknown close) | escalation message reference | n/a — always succeeds |
| `cancel_ticket` | any → canceled | recorded user decision (user_override or user message ref) | none | n/a |

Repair-round authorization is folded into the failing close: a burn whose `budget_after` is
**greater than zero** simultaneously authorizes exactly one repair dispatch. A burn that lands
on **zero authorizes nothing** — the only legal next move is `block_ticket`. There are no free
retries and no third attempt on a budget of 2: initial attempt + at most (budget − 1) repairs.

**Handoff acceptance vs forge moves.** `accept_handoff:<role>` gates the *producer/reviewer/
closeout* handoffs (issue-planner, test-writer, code-writer, adversarial-reviewer,
closeout-retro): the orchestrator proposes it after the child replies and before consuming the
handoff, and the scorekeeper validates required sections + subject before the next move. The
**forge moves** (`pr_creation`, `pr_mutation`, `pr_resync`, `rebase_pr`, `ci_recheck`, `merge`,
`deploy`) are *not* re-accepted — each is its own gated move closed directly by its
`result_close`; the shipping role's own act-time subject check is the enforcement.

**Bootstrap (the `enter_conveyor` exception).** The per-ticket snapshot does not exist until
`enter_conveyor` succeeds, so the first scorekeeper's route card and the `enter_conveyor`
authorization are evaluated against the **immutable home assets** at
`/Users/matthewflebbe/.traycer/bandit/` (protocol.md, scorekeeper.md, ledger template).
`enter_conveyor`'s authorization is read-only (pin = current staging HEAD, observed by
`git rev-parse`). Creating the worktree/branch **and** materializing the ticket snapshot are
post-`YES` result work, closed as `enter_conveyor`'s result evidence. Every turn after that uses
the snapshot.

## Subject refs by move

What `subject_ref` binds to at authorization, and what the close advances it to:

| Move | Authorization subject | Close advances subject to |
|---|---|---|
| `enter_conveyor` | staging HEAD at proposal time | pinned SHA (recorded canonical) |
| `dispatch_issue_planner`, `dispatch_plan_review`, `plan_gate` | pinned SHA (planner) / the **attempt-specific immutable** plan artifact path (review, gate) — numbered per attempt, never a reused/overwritten canonical path | — |
| `accept_handoff:<role>` | the immutable handoff artifact ref + its attempt ID (validated against the open dispatch) | — |
| `dispatch_test_writer` | initial: pinned SHA + test-surface paths. Repair: exact current worktree tree SHA (or checkpoint) + the immutable failure/verdict artifact authorizing that attempt | — |
| `verify_red`, `dispatch_test_review` | worktree tree at handoff / test files + RED artifact | — |
| `test_gate` | test files + RED artifact | approved-test checkpoint SHA |
| `dispatch_code_writer` | checkpoint SHA (base) | candidate head SHA (from handoff) |
| `verify_green`, `dispatch_impl_review`, `impl_gate` | exact candidate head SHA | — |
| `pr_creation` | reviewed SHA | post-edit PR head SHA |
| `pr_mutation` | current PR head SHA | new post-edit head SHA |
| `land_readiness` | current PR head SHA + current staging HEAD SHA | — (evidence binds to both) |
| `ci_recheck` | current PR head SHA (no tree change) | — (same head; new CI refs) |
| `rebase_pr` | current PR head SHA + target staging HEAD SHA | post-rebase PR head SHA |
| `pr_resync` | re-reviewed head SHA | PR head SHA (same commit, now the PR head) |
| `merge` | exact PR head SHA + exact staging HEAD SHA (both from readiness) | merge commit SHA on staging |
| `deploy` | merge commit SHA + config path | deployed environment + SHA |
| `dispatch_closeout`, `closeout` | ticket artifact path + final lifecycle state | retro artifact path |
| `cleanup` | worktree path | — |
| `block_ticket`, `cancel_ticket` | ticket artifact path | — |

A `result_close` carries two subject fields: `authorized_subject_ref` (must **always** equal the
decision's `subject_ref`) and `result_subject_ref`, whose required value is **outcome-aware**:

- **`succeeded`** → the row's "Close advances subject to" (or the authorized subject when the row
  defines no advancement).
- **`failed`, no subject change** (precheck refusal, not-meaningful red, changes_requested, a
  command that produced no new artifact) → `result_subject_ref == authorized_subject_ref`. A
  failed close never has to invent the success artifact (there is no merge commit, no deployed
  SHA, no checkpoint, no candidate head).
- **`failed` that did mutate the subject** (e.g. a detected semantic `pr_mutation` left a new
  head on the PR) → the explicit **failure advancement** named in that row (here: the new
  post-edit head). Only rows that declare a failure advancement may carry one.
- **`reconciled-unknown`** → retain the authorized subject; any uncertain observed reality goes in
  the reconciliation evidence, never in `result_subject_ref`.

The scorekeeper refuses a result whose `authorized_subject_ref` doesn't match the open decision,
or whose `result_subject_ref` doesn't match the rule above for its outcome. Receiving roles
verify their route card's `subject_ref` against the authorizing entry.

## Budget rules

- Buckets: **plan 2 · test 2 · code 3 · ship 2** (or overrides recorded at `plan_gate`).
- **Burn points** (and only these): `plan_gate` changes_requested → plan; `verify_red` failed
  or `test_gate` changes_requested → test; `verify_green` red or `impl_gate` changes_requested
  (code defect) → code **or** a `land_readiness` CI-red that *reproduces locally* as a code
  defect → code / as a test defect → test; `pr_creation`, `pr_resync`, or `merge`-command
  failure, or `deploy` failure → ship.
- **Never burns:** environmental failure (evidence judged by the scorekeeper), `cannot_judge`,
  BLOCKED/NEEDS_CONTEXT handoffs, test-mutation re-entry, A6 rerouting, semantic `pr_mutation`
  rejection, rebase-conflict and undeclared-PR-change re-entry routing (the re-entered chain's
  own gates burn per their rows), `ci_recheck` and non-reproducing (environmental) CI-red,
  act-time `merge` precheck refusal (PR-head/staging-base drift), a first absent-agent
  re-dispatch, `block_ticket` itself, reviewer-agent failures.
- **Exhaustion is exact:** a burn recording `budget_after: 0` authorizes no repair; the only
  legal next move for that thread of work is `block_ticket`. `budget_after` never goes below
  zero — "would go negative" is unreachable because zero already blocks.
- Burns are recorded at the failing **result_close** with `budget_bucket`, `budget_delta: -1`,
  `budget_after`.

## Handoff status mapping

| Handoff `Gate / Status` | Ledger close | Next move | Budget |
|---|---|---|---|
| `DONE` | accept_handoff succeeded | next move per table | none |
| `NEEDS_CONTEXT` | accept_handoff failed | orchestrator supplies context and re-dispatches, or escalates → `block_ticket` | none |
| `BLOCKED` | accept_handoff failed | `block_ticket`, escalate to user | none |
| `DEPLOY_FAILED` (land-and-deploy only) | deploy failed | lifecycle → deploy-failed; per the deploy row's budget branch: budget_after > 0 → deploy retry proposal or `dispatch_closeout`; budget_after = 0 → `block_ticket` | ship −1 |
| **Absent** (finished with no well-formed handoff, or stalled past the wait budget after one re-ping) | dispatch failed, reason=`absent` | **Reviewer:** fresh reviewer, no burn (as today). **Producer / closeout:** the absent dispatch closes failed; authorize one **no-burn** replacement by a **fresh proposal** of the same `dispatch_*` move — new `request_id`/attempt, new `YES`, whose evidence references the first absent close (never reuse the closed sequence). Track "second absence for this logical stage/repair" across the two request_ids; a **second** absence → `block_ticket`. **Forge role** whose real-world effect can't be established → `reconciled-unknown` → `block_ticket` | none (first re-dispatch); block on second |

`DONE_WITH_CONCERNS` is not a status in this protocol — concerns go in `Risks`, the status
stays `DONE` or `BLOCKED`.

## Result-close outcomes and event types

Close outcomes: `succeeded · failed · reconciled-unknown`. An open action is *outstanding*, not
a close outcome — outstanding actions block all new moves until closed. `reconciled-unknown`
closes only through reconciliation that could not establish the outcome; its only legal
successor move is `block_ticket`.

Canonical ledger event types: `decision · result_close · late_result ·
scorekeeper_replacement · reconciliation · correction · user_override`.

A result arriving after a reconciliation that covered its action is **recorded, never
applied**: a `late_result` event with `applied: false, superseded_by: <reconciliation
sequence>`.
