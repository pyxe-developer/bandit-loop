# Rubric: Plan Approval (P1–P7)

For the adversarial reviewer in **plan mode**, judging an orchestration plan. Verdict:
`approve` | `changes_requested` | `cannot_judge`. Block a plan that would require a downstream
role to invent scope, approve risk, or bypass evidence.

## Standing precheck: plan artifact identity

Before judging P1–P7, compare the proposed plan artifact path and attempt ID against the ticket's
ledger and prior plan evidence. Inspect every prior `subject_ref`, `authorized_subject_ref`, and
`result_subject_ref` used by `dispatch_plan_review` or `plan_gate`:

- A repaired or later-attempt plan **must use a new immutable numbered artifact path**. A canonical
  path already bound to an earlier review/gate cannot be refreshed, superseded in place, or reused
  as the new review subject, even when the earlier handoff was separately preserved.
- The plan's declared attempt ID must match its new artifact path, the accepted planner handoff,
  and the authorizing dispatch. The file contents at an earlier ledger-bound path remain evidence
  for that earlier decision and must not change.
- If the path was previously bound, the attempt identity is inconsistent, or preservation cannot
  be established, return **`cannot_judge`** with an **evidence-integrity blocker** and stop the
  content review. Require ledger reconciliation and a newly numbered plan artifact; do not accept
  a prose claim that the predecessor was preserved elsewhere.

- **P1 — Architecture fit.** The route works *with* the existing codebase's structure and
  patterns, not around them. Blocker: the plan invents parallel structure the repo already has.
- **P2 — Dependency justification.** Every new dependency is named and justified; none is added
  for what existing code or stdlib covers. Blocker: an unjustified or unstated dependency.
- **P3 — Blast radius bounded.** Allowed/forbidden surfaces exist for the stages whose surfaces
  are **ticket-specific** — the ones that write product content: RED (test files), GREEN (source
  + any declared config), and the PR mechanical-edit policy. They actually contain the change;
  nothing outside them is needed to satisfy the criteria. Recovery/re-entry moves (`rebase_pr`,
  `ci_recheck`, `pr_resync`, absent-agent re-dispatch, test-mutation re-entry) carry their
  surfaces and routing in `protocol.md` and are satisfied **by reference to the snapshot** — the
  plan need not restate them unless the ticket changes their parameters. Blocker: a
  *ticket-specific* surface missing, or criteria that can't be met inside the allowed surfaces.
  **Not** a blocker: the plan not re-deriving a protocol.md recovery branch.
- **P4 — Reversibility.** One-way doors (migrations, deletions, published artifacts) are named
  with their handling. Blocker: an unnamed irreversible step.
- **P5 — Risk pass.** Failure modes of the change itself (error paths, partial completion) have
  a stated plan. Blocker: a risk acknowledged nowhere.
- **P6 — Proportional scope.** The plan is as small as the ticket allows — no speculative work,
  no gold-plating; budget overrides (if any) are justified. Blocker: scope beyond the ticket.
- **P7 — Executable routing.** The **happy-path** checklist is complete: every forward item
  (plan gate → RED → test gate → GREEN → impl gate → PR → land → merge → closeout → cleanup)
  names stage, entry criteria, evidence, role, surfaces, gate, and next item. Failure/recovery
  branches may be satisfied **by reference to `protocol.md`** ("on failure, route per protocol.md
  <move>") rather than re-tabulated — the protocol snapshot is authoritative for them. Blocker:
  a *forward-path* point where a specialist would have to invent what to do next, or a route step
  that **contradicts** protocol.md (wrong move name, wrong from→to, a mode/label the role prompt
  doesn't define). **Not** a blocker: a recovery branch deferred to protocol.md by reference, or
  a benign synonym for a move/mode whose intent is unambiguous.

Also verify: the plan names the pinned staging SHA; acceptance criteria are testable and each
maps to a stage; the plan's declared RED failure mode is an **assertion failure** compatible with
`rubrics/red-test.md` R2 — a plan that prescribes a missing-export `SyntaxError`, import error, or
other non-assertion RED is a **blocker** (it would wall at `verify_red`).

**Scope-of-judgment rule (applies to P3 and P7).** A plan is *ticket deltas over protocol
defaults*, not a restatement of `protocol.md`. Do not require the plan to reproduce the
legal-move table, budget rules, or recovery routing that already live in the protocol snapshot;
require only what is ticket-specific (surfaces for product-writing stages, the suite/RED
commands, acceptance criteria, scope, PR edit policy, deploy applicability). A restatement of
protocol.md that **drifts** from it is itself a finding; a faithful *reference* to it is not a
gap.
