# Hooks

Opt-in advisory hook assets.

The plugin manifest does not include a `hooks` field. Install hooks with
`scripts/install-git-hooks`; the installer writes only explicit, manifest-owned
files and refuses to overwrite user hooks.

Hooks exit 0 by default, even when the underlying reducer reports a blocker.
They block commits or pushes only when the user explicitly sets
`CODEX_BANDIT_HOOK_BLOCKING=1`.

Uninstall removes only expected Codex Bandit hook files whose managed marker
and digest still match. Drifted hooks, tampered manifest paths, and symlinked
managed paths are skipped and preserved.
