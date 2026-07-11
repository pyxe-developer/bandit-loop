# Bandit Conveyor Asset Pack

Role prompts, rubrics, and templates for the Traycer bandit conveyor — the stage-gated,
scorekeeper-authorized execution pipeline defined in the epic decision log
("Decision Log — Bandit Conveyor on Traycer").

## Layout

- `protocol.md` — the canonical state machine: lifecycle states, legal moves with prerequisites
  and evidence, budget burn rules, handoff-status mapping. The scorekeeper's transition
  authority; the orchestrator skill defers to it.
- `agents/` — one self-contained role prompt per conveyor role (8 roles).
- `rubrics/` — judging criteria per gate; referenced by the adversarial reviewer and stage roles.
- `templates/ledger.md` — the conveyor-ledger skeleton the scorekeeper instantiates per ticket.
- `deploy/` — operator-authored per-repo deploy configs (`<repo>.md`). See `deploy/README.md`.

## How these files are used

- At **conveyor entry** the orchestrator snapshots `protocol.md`, `agents/`, `rubrics/`, and
  `templates/` into the ticket's artifact directory. Every dispatch for that ticket references
  the **snapshot copy**, never this directory — a mid-ticket edit here cannot change a running
  ticket's contracts.
- A dispatch (route card) is sent inline via Traycer message; the receiving agent's **first action**
  is to read its role prompt and rubric from the snapshot paths named in the card.
- All paths in dispatches are **expanded absolute paths** (never `~`).

## Non-negotiable ground rules (all roles)

- Discipline here is **procedural, best-effort** — there is no enforcement engine. Each role holds
  its own boundary; multi-role ledger checks provide defense in depth.
- **All roles except the scorekeeper:** before starting work, read the ticket's conveyor ledger
  and confirm a scorekeeper `YES` exists for the move that dispatched you (matching
  `request_id`). No `YES` → refuse and report. (The scorekeeper itself is exempt — it *writes*
  the ledger; its first turn instantiates it.)
- Every return ends with the handoff contract defined in that role's prompt (section names vary
  slightly by role; `protocol.md` maps every `Gate / Status` value to its ledger consequence).
- Prose is not evidence: every evidence claim carries either its command + exit code + output
  tail, or an immutable reference (artifact path, commit SHA, PR number, CI run ID).
- Agents never touch `main` and never deploy except per an operator config in `deploy/`.
