#!/bin/sh
# Traycer CLI agent: code_writer (implement-green). Edits impl paths, runs GREEN command.
# Knobs: TRAYCER_CODE_WRITER_CLI / _MODEL.
ROLE=CODE_WRITER
ROLE_FILE=code-writer
SKILL=implement-green
LEVEL=WRITE
. "$(dirname "$0")/_lib.sh"
