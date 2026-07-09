# bandit-loop

An evidence-led, stage-gated delivery workflow for Pi. The repository root is
the installable Pi package; `pi/` contains its package resources and remains
installable directly for local development.

## Install for Pi

Install the published repository into the current user's Pi configuration:

```sh
pi install git:github.com/pyxe-developer/bandit-loop
```

To install the current development branch before it is merged:

```sh
pi install git:github.com/pyxe-developer/bandit-loop@codex/bandit-loop-pi-plugin
```

For a local checkout:

```sh
pi install /path/to/bandit-loop
```

Pi writes the package source to its user package directory and adds it to the
user settings file. Start a new Pi session after installation.

The package provides the native stage skills, the `bandit-loop` executable,
and the in-session `codex_bandit_*` bridge tools.
