# Rubric: Land Readiness (L1–L3, L4a/L4b, L5)

For **land-and-deploy** (self-check before merging) and the orchestrator's land-gate proposal to
the scorekeeper. Vocabulary per check: `pass` | `blocker` | `not_applicable`.

- **L1 — Subject binding.** The implementation-approved SHA is an **ancestor** of the current
  PR head, and `diff(reviewed SHA, PR head)` contains **exactly** the mechanical edits declared
  file-by-file in the PR body — nothing else. Any undeclared change is a blocker — the ticket
  re-enters at the gates. (Merge authorization is then bound to **both** the exact current PR
  head and the exact current staging HEAD, captured at L4a.)
- **L2 — CI & protections.** CI green on the PR head; required checks and branch protections
  satisfied; CI run IDs recorded as evidence.
- **L3 — Base freshness.** If `staging` moved past the pinned SHA: branch rebased and full suite
  re-run with evidence, and any code-touching conflict resolution went back through the gates.
- **L4a — Forge reality at readiness time** (this dispatch, before any merge `YES` exists).
  `gh pr view` confirms the PR is open and mergeable; **capture and record the exact current PR
  head SHA and the exact current staging HEAD SHA** — these two become the merge authorization
  subject. No comparison against a future `YES` here.
- **L4b — Revalidation at merge act time** (the separate `merge` dispatch, immediately before the
  merge command). `gh pr view` and `git rev-parse staging` confirm the PR head and staging HEAD
  still equal the two SHAs the merge `YES` names. Either moved → refuse; PR-head drift → fresh
  readiness (re-enter per cause if it's an undeclared change); base drift → `rebase_pr` then a new
  readiness pass and merge proposal.
- **L5 — Deploy authority.** Deploy only if `deploy/<repo>.md` exists and names the target
  environment; otherwise merge-only. "Merge succeeded, deploy failed" is reported explicitly;
  health check run before the move closes.

Evidence staleness relative to the current head is itself a blocker.
