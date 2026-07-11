# Rubric: Red Tests (R1–R6)

For the adversarial reviewer in **test mode**, judging the failing tests. Verdict:
`approve` | `changes_requested` | `cannot_judge`.

- **R1 — Contract fidelity.** Tests express the approved plan's acceptance criteria without
  redefining the contract or forcing an implementation strategy the contract doesn't require.
  Names and assertions make the expected behavior legible to the code-writer.
- **R2 — Meaningful red.** The reported failure is an assertion failure with a legible message —
  not a syntax error, import error, or collection failure. The exact command reproduces it.
- **R3 — Coverage of acceptance.** Edge and error paths that are part of acceptance have
  executable coverage. Blocker: an acceptance criterion with no test and no declared gap.
- **R4 — Gaming resistance.** A wrong implementation could not pass: no assertion satisfiable by
  hardcoding, no-op success, or incidental output. Blocker: shallow assertions a stub would pass.
- **R5 — Determinism.** No dependence on ordering, timing, or uncontrolled external state.
- **R6 — Bounded gaps.** Any untestable criterion is recorded as an explicit, bounded
  verification gap with a disposition — never silently absent.

Also verify: tests stayed within the plan's allowed surfaces; no production code was touched.
