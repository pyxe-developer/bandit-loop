#!/bin/sh
# Shared runner for Traycer workspace CLI agents (bandit-loop).
# Sourced by the per-agent wrappers in this dir, which set BEFORE sourcing:
#   ROLE       upper-snake knob prefix       e.g. CODE_WRITER
#   ROLE_FILE  basename in codex/agents/      e.g. code-writer      (-> code-writer.md)
#   SKILL      dir in codex/skills/           e.g. implement-green  (-> SKILL.md)
#   LEVEL      RO | WRITE | WRITE_NET
#
# Per-agent runtime knobs (env vars, placeholder-defaulted):
#   TRAYCER_<ROLE>_CLI             codex | claude | opencode      (default: codex)
#   TRAYCER_<ROLE>_MODEL           model id; empty => the CLI's own default
#                                   codex/claude: bare id (gpt-5.5, claude-opus-4-8)
#                                   opencode:     <provider>/<model>; provider must be enabled in
#                                                 opencode's config AND routed via Aperture — on this
#                                                 deployment that's aperture/<model>, e.g.
#                                                 aperture/claude-sonnet-5, aperture/z-ai/glm-5.2.
#                                                 (The opencode branch rejects any other provider.)
#   TRAYCER_<ROLE>_OPENCODE_AGENT  required only for LEVEL=RO on opencode
#
# These knobs can live in a `.env` beside this lib (auto-sourced below; values
# in .env win over the ambient environment). See .env for the full per-role list.
#
# Skill-passing convention: uniform inline (role .md + SKILL.md pasted into one prompt).
# See HANDOFF-populate-cli-agents.md for the full contract.
set -eu

LIB_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$LIB_DIR/../.." && pwd)

# Optional .env beside this lib supplies the per-role knobs. Plain KEY=value
# lines; `set -a` exports them so the eval reads below see them. Values here win
# over the ambient environment. ponytail: sourced means executed, but it sits in
# the same dir as these wrappers — same trust as the wrappers, no new boundary.
ENV_FILE="$LIB_DIR/.env"
[ -f "$ENV_FILE" ] && { set -a; . "$ENV_FILE"; set +a; }

ROLE_MD="$REPO_ROOT/codex/agents/$ROLE_FILE.md"
SKILL_MD="$REPO_ROOT/codex/skills/$SKILL/SKILL.md"

for f in "$ROLE_MD" "$SKILL_MD"; do
  [ -r "$f" ] || { echo "$ROLE_FILE: missing or unreadable: $f" >&2; exit 66; }
done

# Indirect env read. ROLE is set by the wrapper (trusted); the inner double
# quotes keep the value inert so eval assigns it verbatim.
eval "CLI=\"\${TRAYCER_${ROLE}_CLI:-codex}\""
eval "MODEL=\"\${TRAYCER_${ROLE}_MODEL:-}\""

# Traycer task prompt: prefer the temp file, fall back to the env var.
if [ -n "${TRAYCER_PROMPT_TMP_FILE:-}" ] && [ -r "$TRAYCER_PROMPT_TMP_FILE" ]; then
  TASK=$(cat "$TRAYCER_PROMPT_TMP_FILE")
else
  TASK=${TRAYCER_PROMPT:-}
fi
[ -n "$TASK" ] || { echo "$ROLE_FILE: TRAYCER_PROMPT or TRAYCER_PROMPT_TMP_FILE required" >&2; exit 64; }

# Assemble one prompt: role + skill + optional system prompt + task.
PROMPT_FILE=$(mktemp "${TMPDIR:-/tmp}/traycer-$ROLE_FILE.XXXXXX")
trap 'rm -f "$PROMPT_FILE"' EXIT HUP INT TERM
{
  cat "$ROLE_MD"
  printf '\n\n## Skill: %s\n\n' "$SKILL"
  cat "$SKILL_MD"
  if [ -n "${TRAYCER_SYSTEM_PROMPT:-}" ]; then
    printf '\n\n## Traycer System Prompt\n\n%s\n' "$TRAYCER_SYSTEM_PROMPT"
  fi
  printf '\n\n## Traycer Task\n\n%s\n' "$TASK"
} > "$PROMPT_FILE"

# Dispatch. Not exec'd, so the EXIT trap still cleans up the prompt file; the
# CLI's exit status propagates as this script's status (set -e).
case "$CLI" in
  codex)
    set -- codex -a never exec -C "$REPO_ROOT"
    case "$LEVEL" in
      RO)        set -- "$@" -s read-only ;;
      WRITE)     set -- "$@" -s workspace-write ;;
      WRITE_NET) set -- "$@" -s workspace-write -c 'sandbox_workspace_write.network_access=true' ;;
      *) echo "$ROLE_FILE: bad LEVEL '$LEVEL'" >&2; exit 78 ;;
    esac
    if [ -n "$MODEL" ]; then set -- "$@" -m "$MODEL"; fi
    "$@" - < "$PROMPT_FILE"
    ;;
  claude)
    set -- claude -p
    if [ -n "$MODEL" ]; then set -- "$@" --model "$MODEL"; fi
    case "$LEVEL" in
      RO)              set -- "$@" --permission-mode plan ;;        # no edits
      WRITE|WRITE_NET) set -- "$@" --permission-mode acceptEdits ;; # network is inherent
      *) echo "$ROLE_FILE: bad LEVEL '$LEVEL'" >&2; exit 78 ;;
    esac
    "$@" < "$PROMPT_FILE"
    ;;
  opencode)
    # Aperture preflight. opencode is the only lane whose model calls route
    # through the Aperture gateway, and that routing lives entirely in opencode's
    # own config (enabled_providers + provider.<name>.options.baseURL) — nothing
    # here sets it. Verify it before dispatch so a run can't (a) fail cryptically
    # on a provider the config doesn't enable, or (b) silently bypass Aperture's
    # policy/allowlist/budget enforcement by resolving to a non-Aperture provider.
    # ponytail: Aperture is identified by baseURL host; add hosts if the gateway moves.
    APERTURE_HOST=bandit.dunker-capella.ts.net
    OC_CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/opencode/opencode.json"
    command -v jq >/dev/null 2>&1 || { echo "$ROLE_FILE: opencode lane needs 'jq' to verify Aperture routing" >&2; exit 69; }
    [ -r "$OC_CONFIG" ] || { echo "$ROLE_FILE: opencode config not readable ($OC_CONFIG); cannot confirm Aperture routing" >&2; exit 78; }
    jq empty "$OC_CONFIG" 2>/dev/null || { echo "$ROLE_FILE: opencode config is not valid JSON ($OC_CONFIG); cannot confirm Aperture routing" >&2; exit 78; }
    # Effective model = the knob if set, else opencode's configured default.
    OC_MODEL=$MODEL
    [ -n "$OC_MODEL" ] || OC_MODEL=$(jq -r '.model // empty' "$OC_CONFIG")
    [ -n "$OC_MODEL" ] || { echo "$ROLE_FILE: no opencode model — set TRAYCER_${ROLE}_MODEL=aperture/<model> or a default 'model' in $OC_CONFIG" >&2; exit 64; }
    OC_PROVIDER=${OC_MODEL%%/*}   # provider segment = text before the first '/'
    OC_BASEURL=$(jq -r --arg p "$OC_PROVIDER" \
      'if (.enabled_providers // [] | index($p)) == null then "NOT_ENABLED" else (.provider[$p].options.baseURL // "") end' \
      "$OC_CONFIG")
    if [ "$OC_BASEURL" = NOT_ENABLED ]; then
      echo "$ROLE_FILE: opencode model '$OC_MODEL' uses provider '$OC_PROVIDER', not in enabled_providers of $OC_CONFIG; use aperture/<model>" >&2; exit 78
    fi
    # Exact host match — substring-contains would accept lookalikes that merely
    # embed the gateway FQDN (bandit.dunker-capella.ts.net.evil.example.com, or
    # the host in a query string), so pull the host out of the URL and compare.
    OC_HOST=${OC_BASEURL#*://}; OC_HOST=${OC_HOST%%/*}; OC_HOST=${OC_HOST%%:*}
    [ "$OC_HOST" = "$APERTURE_HOST" ] || { echo "$ROLE_FILE: opencode provider '$OC_PROVIDER' baseURL '$OC_BASEURL' host is not the Aperture gateway ($APERTURE_HOST); refusing to run a lane that bypasses Aperture policy enforcement" >&2; exit 78; }
    set -- opencode run --dir "$REPO_ROOT"
    case "$LEVEL" in
      RO)
        # opencode has no per-run read-only flag; require a preconfigured RO agent.
        eval "OC_AGENT=\"\${TRAYCER_${ROLE}_OPENCODE_AGENT:-}\""
        [ -n "$OC_AGENT" ] || { echo "$ROLE_FILE: LEVEL=RO on opencode needs a read-only agent; set TRAYCER_${ROLE}_OPENCODE_AGENT, or run this role on codex/claude" >&2; exit 77; }
        set -- "$@" --agent "$OC_AGENT"
        ;;
      WRITE|WRITE_NET) set -- "$@" --auto ;;
      *) echo "$ROLE_FILE: bad LEVEL '$LEVEL'" >&2; exit 78 ;;
    esac
    if [ -n "$MODEL" ]; then set -- "$@" -m "$MODEL"; fi
    "$@" "$(cat "$PROMPT_FILE")"
    ;;
  *)
    echo "$ROLE_FILE: unknown CLI '$CLI' (want codex|claude|opencode)" >&2
    exit 78
    ;;
esac
