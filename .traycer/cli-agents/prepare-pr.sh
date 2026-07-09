#!/bin/sh
# Traycer CLI agent: prepare_pr (prepare-pr). Local git/gates + PR create if authorized.
# Knobs: TRAYCER_PREPARE_PR_CLI / _MODEL.
ROLE=PREPARE_PR
ROLE_FILE=prepare-pr
SKILL=prepare-pr
LEVEL=WRITE_NET
. "$(dirname "$0")/_lib.sh"
