#!/bin/sh
# Traycer CLI agent: adversarial_reviewer (adversarial-gate). Read-only; security-critical.
# Knobs: TRAYCER_ADVERSARIAL_REVIEWER_CLI / _MODEL / _OPENCODE_AGENT (RO on opencode).
ROLE=ADVERSARIAL_REVIEWER
ROLE_FILE=adversarial-reviewer
SKILL=adversarial-gate
LEVEL=RO
SELF=$0
while [ -L "$SELF" ]; do
  LINK=$(readlink "$SELF")
  case "$LINK" in
    /*) SELF=$LINK ;;
    *) SELF=$(cd "$(dirname "$SELF")" && pwd)/$LINK ;;
  esac
done
TRAYCER_AGENT_DIR=$(cd "$(dirname "$SELF")" && pwd)
export TRAYCER_AGENT_DIR
. "$TRAYCER_AGENT_DIR/_lib.sh"
