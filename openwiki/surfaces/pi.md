# Pi surface

## What Pi provides
The Pi package is the repository's Pi-native surface. It packages the bandit-loop workflow as a Pi installable package with:

- package metadata in [`pi/package.json`](../../pi/package.json)
- a CLI entrypoint in [`pi/bin/bandit-loop.mjs`](../../pi/bin/bandit-loop.mjs)
- an extension bridge in [`pi/extensions/codex-bandit.ts`](../../pi/extensions/codex-bandit.ts)
- role agents under [`pi/agents/`](../../pi/agents/)
- stage skills under [`pi/skills/`](../../pi/skills/)
- workflow/runtime helpers under [`pi/scripts/`](../../pi/scripts/)

The root README positions Pi as one of three host surfaces that share the same delivery workflow contract. See [`README.md`](../../README.md).

## Intended user path
The documented installation flows are:

```sh
pi install git:github.com/pyxe-developer/bandit-loop@codex/bandit-loop-pi-plugin
pi install .
pi install -l .
pi install npm:pi-subagents
```

After installation, users restart Pi so the skills and agents are discovered.

## Runtime surface
The Pi README describes two main runtime entry points:

- the `bandit-loop` CLI, which dispatches to package scripts
- the Pi extension tools, which expose orchestration and validation actions inside a Pi session

Documented tools include:

- `codex_bandit_orchestrate`
- `codex_bandit_dashboard`
- `codex_bandit_route_card`
- `codex_bandit_evidence_ledger`
- `codex_bandit_verify_stage`
- `codex_bandit_review_package`
- `codex_bandit_delivery_operation`

## Dashboard feature
Pi has a dashboard projection feature that renders an epic's progress into static HTML under `.codex-bandit/epics/<epic_id>/dashboard.html`.

The key design point is that the dashboard is a projection, not a second source of truth. The README says it is created from an epic manifest, route cards, and evidence ledgers, and orchestration refreshes it as work items advance.

This is the first place to look when changing dashboard behavior:

- [`pi/scripts/dashboard_runtime.py`](../../pi/scripts/dashboard_runtime.py)
- [`pi/tests/run_dashboard_checks.py`](../../pi/tests/run_dashboard_checks.py)
- [`pi/README.md`](../../pi/README.md)

## Limits and caveats

- Pi is described as an **assisted-mode** surface; Codex-specific MCP registration, custom-agent installation, and Git/session hooks are intentionally not exposed by the Pi package.
- Role agents are exposed through `pi-subagents` and are not installed automatically.
- The dashboard is derived output only.
- The root package declares Pi and Pi-subagents metadata, so changes to packaging should be checked in both the root `package.json` and `pi/package.json`.

## What to check before changing Pi

- If you change install or packaging behavior, inspect both `package.json` files and the Pi README.
- If you change the dashboard, re-run `pi/tests/run_dashboard_checks.py`.
- If you change CLI dispatch, verify the entrypoint in `pi/bin/bandit-loop.mjs` still matches the documented script surface.

## Source anchors

- Pi README: [`pi/README.md`](../../pi/README.md)
- Root package metadata: [`package.json`](../../package.json)
- Pi package metadata: [`pi/package.json`](../../pi/package.json)
- CLI entrypoint: [`pi/bin/bandit-loop.mjs`](../../pi/bin/bandit-loop.mjs)
- Extension bridge: [`pi/extensions/codex-bandit.ts`](../../pi/extensions/codex-bandit.ts)
- Dashboard tests: [`pi/tests/run_dashboard_checks.py`](../../pi/tests/run_dashboard_checks.py)
