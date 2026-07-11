# Rubric: Implementation Review (A1–A7)

For the adversarial reviewer in **implementation mode**, judging the green change. This rubric
**absorbs standard code review** — correctness, quality, and adversarial falsification in one
gate. Verdict: `approve` | `changes_requested` | `cannot_judge`. Findings carry severity
(`blocker` | `non_blocking`) and route by cause: test defects → test-writer; requirements
defects → re-plan; otherwise → code-writer.

- **A1 — Failure paths.** Error, partial-failure, retry, and rollback paths are inspected;
  durable state changes and one-way doors are handled. Blocker: a failure leaves state corrupt,
  ambiguous, or unrecoverable; rollback depends on unstated manual cleanup.
- **A2 — Contract correctness.** The change implements the approved plan and acceptance
  criteria — not a redefinition or a subset. Blocker: an omitted or reinterpreted criterion.
- **A3 — Quality & fit (standard review).** The change reads like the surrounding code: naming,
  idiom, altitude, comment discipline; smallest honest change; reuses what the codebase has; no
  speculative abstraction; no dead code. Blocker: complexity or duplication a maintainer would
  reject.
- **A4 — Scope containment.** Only allowed surfaces touched; no unrelated edits, no scope
  creep, no new dependency without plan justification.
- **A5 — Trust boundaries.** Input validation at boundaries, no secrets in code or logs, no
  injection-shaped string building, safe defaults.
- **A6 — Gameable tests (late check).** Challenge the passing tests themselves: could this
  implementation pass by hardcoding, special-casing test inputs, or satisfying incidental
  output? Could the tests have been weakened? An A6 blocker routes to the **test-writer** and
  the ticket re-enters at the test gate.
- **A7 — Blast radius & operations.** Migrations, config, and compatibility effects are
  accounted for; behavior outside the task is not regressed.

Also verify from the ledger: the green evidence (orchestrator's suite run) covers the exact
subject SHA you are judging, and the expected preceding ledger sequence exists.
