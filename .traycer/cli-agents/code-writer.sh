#!/bin/sh
# Traycer CLI agent: code_writer (implement-green). Edits impl paths, runs GREEN command.
# Knobs: TRAYCER_CODE_WRITER_CLI / _MODEL.
ROLE=CODE_WRITER
ROLE_FILE=code-writer
SKILL=implement-green
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
