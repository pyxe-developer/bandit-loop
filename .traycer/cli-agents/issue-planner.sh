#!/bin/sh
# Traycer CLI agent: issue_planner (plan-work-item). Read-only; proposes route cards.
# Knobs: TRAYCER_ISSUE_PLANNER_CLI / _MODEL / _OPENCODE_AGENT (RO on opencode).
ROLE=ISSUE_PLANNER
ROLE_FILE=issue-planner
SKILL=plan-work-item
LEVEL=RO
. "$(dirname "$0")/_lib.sh"
