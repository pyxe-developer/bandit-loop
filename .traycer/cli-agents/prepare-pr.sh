#!/bin/sh
# Traycer CLI agent: prepare_pr (prepare-pr). Local git/gates + PR create if authorized.
# Knobs: TRAYCER_PREPARE_PR_CLI / _MODEL.
ROLE=PREPARE_PR
ROLE_FILE=prepare-pr
SKILL=prepare-pr
LEVEL=WRITE_NET
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
