#!/bin/sh
# Traycer CLI agent: issue_planner (plan-work-item). Read-only; proposes route cards.
# Knobs: TRAYCER_ISSUE_PLANNER_CLI / _MODEL / _OPENCODE_AGENT (RO on opencode).
ROLE=ISSUE_PLANNER
ROLE_FILE=issue-planner
SKILL=plan-work-item
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
