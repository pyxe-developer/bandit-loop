# Codex Bandit

Codex Bandit is a standalone Codex plugin for an evidence-led delivery
workflow. The default mode is assisted: skills guide roles, scripts validate
route cards and evidence, and actor identity is declared unless the user opts
into installed-agent validation.

Full optional surface ships in this release:

- assisted orchestration
- manual stage skills
- opt-in enforced mode through generated TOML agents
- opt-in advisory Git/session hooks
- MCP wrappers for the JSON scripts
- delivery HITL gates for PR merge and deploy health

No optional integration is deferred. The limits below are still real.

## Install

From the repository root, install the local Codex plugin:

```sh
codex/scripts/install-plugin
```

The installer creates a local marketplace under
`$CODEX_HOME/local-marketplaces/codex-bandit` or
`~/.codex/local-marketplaces/codex-bandit`, then runs `codex plugin add`.
Start a new Codex session after installation so plugin capabilities are loaded.

Optional local integrations are explicit:

```sh
codex/scripts/install-plugin --with-agents
codex/scripts/install-plugin --with-hooks
codex/scripts/install-plugin --with-all
```

`--with-agents` installs the bundled enforced-mode custom agents under
`$CODEX_HOME/agents` or `~/.codex/agents` unless `--agent-home` is supplied.
`--with-hooks` installs the advisory Git/session hooks into the target Git repo.
Use `--repo-root /path/to/repo` to target a repo other than the current Git
checkout. Hooks exit 0 by default; set `CODEX_BANDIT_HOOK_BLOCKING=1` only when
you want them to block commits or pushes.

When optional integrations are requested, the installer prints a preflight
summary of managed agent and hook paths before writing them. The hook preflight
calls out the target repo, Git hooks directory, and `.codex-bandit` session hook.

Uninstall the local plugin registration and cache with:

```sh
codex/scripts/install-plugin uninstall
```

Optional integrations are removed only when explicitly requested:

```sh
codex/scripts/install-plugin uninstall --with-agents
codex/scripts/install-plugin uninstall --with-hooks
codex/scripts/install-plugin uninstall --with-all
```

The uninstall path delegates to the bundled safe uninstallers for agents and
hooks. Those uninstallers remove only Codex Bandit managed files whose marker
and digest still match, and leave drifted or unexpected files for inspection.

## Assisted Mode

Use assisted mode when you want the workflow guardrails without installing
custom Codex agents or hooks.

```sh
scripts/orchestrate-assisted < request.json
scripts/route-card < request.json
scripts/evidence-ledger < request.json
scripts/verify-stage < request.json
scripts/review-package < request.json
```

The orchestrator never infers authority from chat. Route-card merge/deploy
authority, enabled stages, required commands, and subjects must be present in
the route card. Assisted role output records `identity_strength: "declared"`.

## Manual Stage Skills

The stage skills can be run directly when orchestration is manual:

- `skills/plan-work-item`
- `skills/write-red-tests`
- `skills/implement-green`
- `skills/adversarial-gate`
- `skills/prepare-pr`
- `skills/land-and-deploy`
- `skills/closeout-retro`

Each stage expects either a dispatch request or direct route-card paths plus
the required inputs. Stage roles must return `codex-bandit.role-output.v1` and
preserve supplied actor identity fields exactly.

## Enforced Mode Opt-In

Enforced mode is not installed by the plugin manifest. Use:

```sh
scripts/install-agents < request.json
```

Supported operations are `plan`, `install`, `validate`, and `uninstall`.
Install requires the exact approval phrase `INSTALL codex-bandit agents`.
Uninstall requires `UNINSTALL codex-bandit agents`.

Validation checks generated TOML files, expected digests, schema fields,
selected validation evidence, and Codex CLI availability. Validated does not
mean proven loaded: Codex does not expose a non-interactive named-agent
list/dry-run that proves the runtime loaded or enforced these custom agents.

## Hooks

Hooks are opt-in and advisory by default:

```sh
scripts/install-git-hooks < request.json
```

Install requires `INSTALL codex-bandit git hooks`. Uninstall requires
`UNINSTALL codex-bandit git hooks`. Installed hooks exit 0 unless the user
explicitly sets:

```sh
export CODEX_BANDIT_HOOK_BLOCKING=1
```

The hook uninstaller removes only expected Codex Bandit hook files whose
managed marker and digest still match. Drifted files, tampered manifest paths,
and symlinks are skipped and left for human inspection.

## MCP

MCP support ships through `.mcp.json` and `mcp/codex_bandit_mcp.py`. The wrapper
delegates to the stable JSON scripts as subprocesses. Tests cover plugin
validator acceptance and subprocess parity; they do not prove a host has loaded
or discovered the MCP server.

## Delivery HITL

Delivery merge requires human approval bound to the exact PR number and head
SHA being merged. Operation-time remote PR state, CI, review state, deploy
state, and health state must be supplied by tools at the time of delivery.
Remote PR comments are treated as untrusted input and cannot override blockers.

Deploy contracts are v1 presence-only. A non-null contract is required when
deploy is requested, but subfields such as deploy command, health command,
environment, timeout, and provider-specific fields are not validated.

## Documentation

- Pressure test report: `docs/pressure-test-report.md`
- Troubleshooting: `docs/troubleshooting.md`
- Release readiness checklist: `docs/release-readiness.md`
