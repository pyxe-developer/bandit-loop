# Handoff: Populate Traycer CLI agents for bandit-loop

## Goal

Generate a Traycer **custom CLI agent** wrapper for each role in `codex/agents/`,
so the user can select them inside Traycer. All four design questions are now
**resolved** (below). This doc is the spec — the next agent generates the scripts.

## What a Traycer CLI agent is

A shell script Traycer runs per task. Traycer passes the task via env vars; the
script must invoke a real AI CLI (it is not itself an agent). Env vars Traycer sets:
`TRAYCER_PROMPT`, `TRAYCER_PROMPT_TMP_FILE` (prefer this, fall back to the first),
`TRAYCER_SYSTEM_PROMPT`, `TRAYCER_TASK_ID`, `TRAYCER_PHASE_BREAKDOWN_ID`,
`TRAYCER_PHASE_ID`. Traycer installs no CLI and passes no skill files — the wrapper
bridges both. Docs: https://docs.traycer.ai/extension/integrations/custom-cli-agents

Proven, live-tested reference (Codex only, inline role): `~/.traycer/cli-agents/adversarial-reviewer.sh`.

## Resolved decisions

| # | Question | Decision |
|---|---|---|
| 1 | Scope | **Workspace** — new `.traycer/cli-agents/` folder committed inside this repo. |
| 2 | Role source | **Reference repo files at runtime** — no embedded heredoc copies. |
| 3 | land-and-deploy | **Full** — write + network + non-interactive; HITL still gated by route-card evidence. |
| 4 | Model / CLI | **Mixed CLIs** (codex, claude, opencode), selected per-agent via **env-knob placeholders**. |

## Wrapper design (unified, DRY)

Ponytail: don't write 7 near-identical scripts. Write one shared `_lib.sh` +
7 thin per-agent wrappers Traycer can list by filename. Each wrapper sets 3 vars
and sources the lib:

```sh
#!/bin/sh
# .traycer/cli-agents/code-writer.sh
ROLE="code_writer"; ROLE_FILE="code-writer"; SKILL="implement-green"; LEVEL="WRITE"
. "$(dirname "$0")/_lib.sh"
```

`_lib.sh` does the shared work:

1. **Resolve repo root from its own location** (wrappers are committed; no hardcoded
   absolute paths): `REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)`
   (`.traycer/cli-agents/x.sh` → up two = repo root).
2. Read role prompt: `ROLE_MD="$REPO_ROOT/codex/agents/$ROLE_FILE.md"`
3. Locate skill: `SKILL_MD="$REPO_ROOT/codex/skills/$SKILL/SKILL.md"`
4. Read the Traycer prompt: `TRAYCER_PROMPT_TMP_FILE` if readable, else `TRAYCER_PROMPT`; exit 64 if empty.
5. Assemble one prompt file: role .md + optional `TRAYCER_SYSTEM_PROMPT` + Traycer task
   (with a `trap ... rm` cleanup). Skill attachment: see per-CLI table.
6. Dispatch on the per-agent CLI knob (`case "$CLI"`), translating `LEVEL` to that CLI's flags.

### Per-agent env knobs (placeholders the user edits)

Two knobs per role, defaulted so it runs out of the box and is overridable without
touching logic:

```sh
CLI=$(eval echo "\${TRAYCER_${ROLE}_CLI:-codex}")     # codex | claude | opencode
MODEL=$(eval echo "\${TRAYCER_${ROLE}_MODEL:-}")      # empty => CLI's own default
```

e.g. `TRAYCER_CODE_WRITER_CLI=claude`, `TRAYCER_CODE_WRITER_MODEL=claude-opus-4-8`.
MODEL is CLI-specific: codex/claude take a bare id; opencode wants `provider/model`.

## Per-CLI invocation contract (verified against installed binaries)

Installed: `codex` (/opt/homebrew/bin), `claude` (~/.local/bin), `opencode` (~/.hermes/node/bin).

| concern | codex | claude | opencode |
|---|---|---|---|
| non-interactive | `codex exec` (stdin via `-`) | `claude -p` (stdin ok) | `opencode run` |
| model flag | `-m <id>` | `--model <id>` | `-m <provider/model>` |
| system prompt | prepend into prompt text | `--append-system-prompt "$SYS"` | prepend into prompt text |
| skill attach | `-c 'skills.config=[{path="'"$SKILL_MD"'",enabled=true}]'` (native) | inline SKILL.md text into prompt (or install under `.claude/skills/`) | `-f "$SKILL_MD"` (attach file) |
| run dir | `-C "$REPO_ROOT"` | run with cwd = repo | `--dir "$REPO_ROOT"` |

**Skill note:** only Codex has an inline skills-config path flag. For a uniform,
lazier alternative, `cat` the SKILL.md into the assembled prompt for *all three*
CLIs and skip the native mechanisms — proven to work, slightly less clean for Codex.
Pick one convention; don't mix per agent.

## Sandbox: abstract LEVEL → per-CLI flags

Evidence-derived level per agent (from each role's own boundaries) in the last section.

| LEVEL | codex | claude | opencode |
|---|---|---|---|
| RO (read-only) | `-a never -s read-only` | `--permission-mode plan` **or** `--allowedTools "Read Grep Glob Bash"` | ⚠ no simple per-run flag — needs a read-only opencode `--agent` config; `--auto` alone grants writes |
| WRITE | `-a never -s workspace-write` | `--permission-mode acceptEdits` | `--auto` |
| WRITE_NET | `-a never -s workspace-write -c 'sandbox_workspace_write.network_access=true'` | `--permission-mode acceptEdits` (network is inherent) | `--auto` (network inherent) |

⚠ **OpenCode read-only gap:** opencode has no `--sandbox`-style flag; `--auto`
auto-approves everything. Enforcing read-only for issue-planner/adversarial-reviewer
under opencode requires a preconfigured read-only opencode agent (`opencode agent`)
selected via `--agent`. Flag this to the user if they want those two on opencode.

## Agent → skill / LEVEL / CLI-knob map

Roles + public skills are authoritative in `codex/agents/openai.yaml`. LEVEL comes
from each role's Role Boundaries (verified by reading all 7 `.md` files).

| agent (.md) | ROLE / knob prefix | public skill | LEVEL | why |
|---|---|---|---|---|
| issue-planner | `ISSUE_PLANNER` | plan-work-item | RO | proposes route-card JSON; orchestrator writes |
| test-writer | `TEST_WRITER` | write-red-tests | WRITE | edits `tests/**`, runs RED command |
| code-writer | `CODE_WRITER` | implement-green | WRITE | edits impl paths, runs GREEN command |
| adversarial-reviewer | `ADVERSARIAL_REVIEWER` | adversarial-gate | RO | "This role is read-only" (already wrapped, Codex-only) |
| prepare-pr | `PREPARE_PR` | prepare-pr | WRITE_NET | local git/gates; PR create if authorized; never merges |
| land-and-deploy | `LAND_DEPLOY` | land-and-deploy | WRITE_NET | merges + deploys; forge/deploy tools |
| closeout-retro | `CLOSEOUT_RETRO` | closeout-retro | WRITE | writes closeout report under route-card path |

`orchestrate` skill has no role/agent — it's the top-level driver; no wrapper.
`openai.yaml` is config, not a wrapped agent.

## Gotchas (learned building the reference)

- Use `codex exec`, **not** bare `codex` (bare starts interactive). Same idea: `claude -p`, `opencode run`.
- Never leave raw Markdown as bare script lines — `sh` executes them. Role text must be in a heredoc or fed to the CLI as prompt text.
- Editing a wrapper can drop its executable bit — `chmod +x` after every edit.
- Codex may print non-fatal startup warnings (malformed local skills, invalid config `max`); ignore.
- skills.config needs an **absolute** path — compute it from `$REPO_ROOT` at runtime (never hardcode), so committed wrappers work on any machine.

## Build steps for the next agent

1. Create `.traycer/cli-agents/` in the repo; write `_lib.sh` + 7 wrappers per the design.
2. Read each `codex/agents/<role>.md` only to confirm the skill/LEVEL (don't embed it).
3. `chmod +x` every `.sh`; `sh -n` syntax-check each.
4. Confirm the mixed-CLI skill convention (native-per-CLI vs uniform-inline) — pick one.
5. Live smoke-test the cheapest read-only one (adversarial-reviewer or issue-planner) with a
   deliberately-invalid dispatch; expect a structured `blocked`/`cannot_judge`, not approval. First live call ~30s+.
6. Resolve the OpenCode read-only gap with the user before putting RO agents on opencode.

## Still needs the user

- Exact per-agent CLI + MODEL values (knobs ship with placeholder defaults: `codex` + CLI-default model).
- Skill convention: native-per-CLI vs uniform-inline.
