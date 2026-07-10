#!/bin/sh
# Traycer CLI agent: closeout_retro (closeout-retro). Writes closeout report.
# Knobs: TRAYCER_CLOSEOUT_RETRO_CLI / _MODEL.
ROLE=CLOSEOUT_RETRO
ROLE_FILE=closeout-retro
SKILL=closeout-retro
LEVEL=WRITE
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
