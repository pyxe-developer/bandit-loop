# bandit-loop

bandit-loop is the Pi package equivalent of the Codex Bandit plugin. It
ships the same assisted, evidence-led workflow, route-card and evidence
scripts, stage skills, references, and role prompt assets.

## Install

For the user-facing GitHub install:

```sh
pi install git:github.com/pyxe-developer/bandit-loop@codex/bandit-loop-pi-plugin
```

The `@codex/bandit-loop-pi-plugin` ref is required until this Pi port is merged
into `main`. Once merged, the `@...` suffix can be omitted.

From a local checkout, install the repository root:

```sh
pi install .
```

For a project-local installation from a local checkout, use:

```sh
pi install -l .
```

Installing `./pi` directly is also supported for package development, but the
repository root is the normal user install target.

Start a new Pi session after installing so the skills and extension tools are
discovered.

Role agents are exposed through `pi-subagents`, which Pi does not install
automatically as part of this package:

```sh
pi install npm:pi-subagents
```

After restarting Pi, use `/subagents-doctor` to verify discovery. The package
agents are named `bandit-loop.issue-planner`,
`bandit-loop.test-writer`, `bandit-loop.code-writer`,
`bandit-loop.adversarial-reviewer`, `bandit-loop.prepare-pr`,
`bandit-loop.land-and-deploy`, and `bandit-loop.closeout-retro`.

## Use

The stage skills are available through Pi's native skill system. The extension
also registers these tools for in-session orchestration:

- `codex_bandit_orchestrate`
- `codex_bandit_dashboard`
- `codex_bandit_route_card`
- `codex_bandit_evidence_ledger`
- `codex_bandit_verify_stage`
- `codex_bandit_review_package`
- `codex_bandit_delivery_operation`

The same script entry points are available from the installed package through
the `bandit-loop` command, for example:

```sh
bandit-loop orchestrate-assisted < request.json
```

## Epic dashboard

Bandit can maintain a static HTML view of an epic without introducing a
second source of workflow truth. Create or update an epic manifest with the
`codex_bandit_dashboard` tool (or `bandit-loop dashboard`) using this request:

```json
{
  "schema_version": "codex-bandit.dashboard-request.v1",
  "operation": "upsert",
  "repo_root": ".",
  "epic_id": "billing-reliability",
  "input": {
    "title": "Billing reliability",
    "description": "Make retries and reconciliation safe.",
    "work_item_ids": ["bill-101", "bill-102", "bill-103"]
  },
  "request_id": "dashboard_billing_reliability"
}
```

This writes the durable manifest and generated view to:

```text
.codex-bandit/epics/billing-reliability/epic.json
.codex-bandit/epics/billing-reliability/dashboard.html
```

Every `orchestrate-assisted` call for a listed work item refreshes its epic
dashboard. The HTML shows overall progress, active and blocked counts, each
item's current stage, pipeline position, blockers, and last evidence time.
Use `operation: "render"` to regenerate an epic or `operation: "status"` to
read the same projection as JSON without writing HTML.

This Pi port provides the assisted workflow. Codex-specific MCP registration,
Codex custom-agent installation, and Codex Git/session hook installation are
intentionally not exposed by the Pi package.
