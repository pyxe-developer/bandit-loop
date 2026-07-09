#!/bin/sh
# Traycer CLI agent: closeout_retro (closeout-retro). Writes closeout report.
# Knobs: TRAYCER_CLOSEOUT_RETRO_CLI / _MODEL.
ROLE=CLOSEOUT_RETRO
ROLE_FILE=closeout-retro
SKILL=closeout-retro
LEVEL=WRITE
. "$(dirname "$0")/_lib.sh"
