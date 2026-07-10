#!/bin/sh
# Traycer CLI agent: land_deploy (land-and-deploy). Merges + deploys; write + network.
# HITL merge approval is still gated by route-card evidence inside the role prompt.
# Knobs: TRAYCER_LAND_DEPLOY_CLI / _MODEL.
ROLE=LAND_DEPLOY
ROLE_FILE=land-and-deploy
SKILL=land-and-deploy
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
