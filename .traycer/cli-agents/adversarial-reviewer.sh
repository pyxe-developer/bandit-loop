#!/bin/sh
# Traycer CLI agent: adversarial_reviewer (adversarial-gate). Read-only; security-critical.
# Knobs: TRAYCER_ADVERSARIAL_REVIEWER_CLI / _MODEL / _OPENCODE_AGENT (RO on opencode).
ROLE=ADVERSARIAL_REVIEWER
ROLE_FILE=adversarial-reviewer
SKILL=adversarial-gate
LEVEL=RO
. "$(dirname "$0")/_lib.sh"
