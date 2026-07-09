#!/bin/sh
# Traycer CLI agent: test_writer (write-red-tests). Edits tests/**, runs RED command.
# Knobs: TRAYCER_TEST_WRITER_CLI / _MODEL.
ROLE=TEST_WRITER
ROLE_FILE=test-writer
SKILL=write-red-tests
LEVEL=WRITE
. "$(dirname "$0")/_lib.sh"
