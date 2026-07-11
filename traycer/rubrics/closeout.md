# Rubric: Closeout (C1–C5)

For **closeout-retro** and the orchestrator's cleanup proposal to the scorekeeper. Vocabulary
per check: `pass` | `blocker` | `not_applicable`.

- **C1 — Evidence-grounded retro.** Every statement traces to ledger entries or evidence
  artifacts. Blocker: a material blocker, waiver, degraded path, or budget burn omitted.
- **C2 — Honest delivery outcome.** Recorded precisely: `landed-staging` | `blocked` |
  `canceled` | `deploy-failed`. Landed-staging may truthfully be described as *delivered to
  staging*, but never as promoted or delivered to main — promotion is human-owned, outside the
  workflow.
- **C3 — Lessons with dispositions.** Every lesson has one: improvement proposal (to prompts,
  rubrics, or the conveyor skill), follow-up, or explicit no-action. Orchestrator improvisations
  and prompt/rubric ambiguities are mandatory lessons during the dogfood era.
- **C4 — Cleanup preconditions.** Worktree deletion only when: branch merged to staging,
  evidence materialized, deploy outcome recorded, no outstanding ledger action. Blocked/failed
  tickets keep their worktree — stated explicitly.
- **C5 — Unambiguous next action.** The ticket ends with exactly one stated next action
  (close / human promotion pending / repair ticket), and routing surfaces reflect it.
