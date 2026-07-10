#!/bin/sh
# Traycer CLI agent: test_writer (write-red-tests). Edits tests/**, runs RED command.
# Knobs: TRAYCER_TEST_WRITER_CLI / _MODEL.
ROLE=TEST_WRITER
ROLE_FILE=test-writer
SKILL=write-red-tests
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
