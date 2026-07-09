# bandit-loop

bandit-loop is the Pi package equivalent of the Codex Bandit plugin. It
ships the same assisted, evidence-led workflow, route-card and evidence
scripts, stage skills, references, and role prompt assets.

## Install

For the user-facing GitHub install:

```sh
pi install git:github.com/pyxe-developer/bandit-loop
```

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

## Use

The stage skills are available through Pi's native skill system. The extension
also registers these tools for in-session orchestration:

- `codex_bandit_orchestrate`
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

This Pi port provides the assisted workflow. Codex-specific MCP registration,
Codex custom-agent installation, and Codex Git/session hook installation are
intentionally not exposed by the Pi package.
