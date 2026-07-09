# Model Review Checklist

## Product fit
- [ ] The model satisfies every in-scope requirement REQ-001..REQ-013.
- [ ] Out-of-scope behavior (subagent internals, install-agents/hooks/MCP internals, pi-bandit interop) is explicitly excluded.
- [ ] User-visible failure paths (RED-wrong-failure, forbidden edit, stale subject, missing HITL, CI/health fail, enforced-not-validated) are clear.

## Behavioral completeness
- [ ] Every state STATE-000..STATE-011 has a precise "what is / is not true" definition.
- [ ] Every allowed event is listed per state.
- [ ] Safety-relevant invalid transitions X-001..X-012 are rejected, with a default-rejection policy for the rest.
- [ ] Every guard GUARD-001..GUARD-017 is testable (GUARD-016/017 are gated on Q-002/Q-001).
- [ ] Every side effect FX-001..FX-014 is named at its transition.
- [ ] Every failure path leads to a known state (blocked/repairing overlay, ManualContinuation, Abandoned, or delivery_blocked).

## AI boundaries
- [ ] AI-assisted edges AI-001..AI-007 are named.
- [ ] Each AI edge has a deterministic fallback (predicate, exit code, digest binding, HITL).
- [ ] AI does not decide authorization (delivery authority / capability mode), persistence integrity (append-only ledger + reducer), or merge safety (HITL + head match).

## Testability
- [ ] Test matrix covers happy paths (TEST-001..005, 016, 025).
- [ ] Test matrix covers guard rejections (TEST-011, 015, 021, 033, 060, 061).
- [ ] Test matrix covers invalid transitions (TEST-013, 014, 030, 031, 032).
- [ ] Test matrix covers invariants (TEST-006, 020, 023, 034, 041, 042).
- [ ] must-write-first tests are identified.

## Handoff
- [ ] Engineering review can proceed from this model.
- [ ] Implementation spec (Ticket 04 scripts, Ticket 05 orchestrator) can cite transition and invariant IDs.

## Review questions the human must answer first
1. **Q-001** — accept the "stamp `subject.head_sha` from actual repo HEAD; first command evidence locks the attempt subject" rule? (Blocks TEST-061 and every multi-commit fixture.)
2. **Q-002** — must the HITL-approved head equal the reviewed head (re-review on drift), or is a human-approved unreviewed delta allowed? (Delivery-safety call; blocks TEST-060.)
3. **Q-009 / Q-010** — confirm budget-exhaustion holding state and what makes a post-`manual_patch` review "independent."
4. Confirm the AI boundary: is a single AI adversarial reviewer (V1) sufficient, with HITL merge as the only human gate, or is a second independent reviewer needed for high-risk work items?
