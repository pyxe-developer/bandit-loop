---
kind: spec
title: "Conveyor Ledger — <ticket title>"
---

# Conveyor Ledger

> Sole writer: the ticket's scorekeeper (current epoch below). Everyone else reads only.
> The event log is append-only and authoritative; this summary is a convenience view.

## Current state

- **Ticket:** <ticket artifact path>
- **Lifecycle state:** queued
- **Pinned staging SHA:** <sha>
- **Scorekeeper:** agent `<id>` — **epoch 1**
- **Replacement chain:** epoch 1: agent `<id>` (initial)
- **Budgets remaining:** plan 2 / test 2 / code 3 / ship 2
- **Outstanding authorized action:** none
  <!-- when open: sequence=<n>, request_id=<id>, action=<what was authorized>, awaiting=<next_required_result> -->
- **Failure state:** none  <!-- or: re-ping issued <seq> | replaced at <seq> -->

## Entry shapes by event type

Beyond `decision` (shown below), entries use these shapes — same `sequence`/`epoch` fields:

```
event: result_close          # closes the open decision's action
closes_sequence: <n>
request_id: <must match the closed decision's>
authorized_subject_ref: <must equal the closed decision's subject_ref>
result_subject_ref: <outcome-aware, per protocol.md: succeeded → the row's advancement (or authorized subject when none); failed w/ no subject change → equals authorized_subject_ref; failed w/ a declared failure advancement → that; reconciled-unknown → authorized subject>
outcome: succeeded | failed | reconciled-unknown
budget_bucket: plan | test | code | ship | none   # per protocol.md burn points
budget_delta: 0 | -1
budget_after: <n>
evidence: [<refs>]           # for reconciled-unknown: the checks that failed to establish it

event: late_result           # result arriving after a reconciliation covered its action
for_sequence: <n>
applied: false
superseded_by: <reconciliation sequence>
content: <the result, recorded verbatim, never applied>

event: scorekeeper_replacement
new_epoch: <n>               # predecessor + 1
new_agent: <id>
reason: finished-without-reply | stalled-turn | operator
outstanding_at_takeover: <sequence or "none">

event: reconciliation        # mandatory after timeout / restart / replacement / ambiguous result
checks: branch SHA, PR head/base/merge state, CI run IDs, deploy status, cleanup state
findings: <what reality shows>
supersedes_results_for: [<sequences>]   # late results for these are recorded, never applied

event: correction            # voids/supersedes a damaged or stale entry; never edits it
supersedes_sequence: <n>
reason: torn-tail | stale-epoch-append | summary-divergence
reconstructed_state: <one line>

event: user_override         # only way to reverse a NO without new evidence
overrides_sequence: <n>
recorded_decision: <what the user decided, verbatim>
```

## Event log (append-only)

<!-- Event types: decision | result_close | late_result | scorekeeper_replacement | reconciliation | correction | user_override -->
<!-- requested_move values MUST be exact move names from protocol.md (e.g. enter_conveyor, verify_red, impl_gate, pr_creation) — anything else is refused -->

```
sequence: 1
event: decision
request_id: enter_conveyor-attempt-1
epoch: 1
requested_move: enter_conveyor
from_state: queued        to_state: planning
subject_ref: <staging HEAD SHA at proposal time>
evidence: []
budget_before: n/a
decision: YES
reason: Conveyor entry; first move; no prior state.
next_required_result: pinned SHA + worktree path + snapshot path
```
