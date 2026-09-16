# Contributing

This file is for people who change `plotplate` itself.
To use the tool, see the [README](README.md).

## Setup

```sh
git clone https://github.com/<org>/plotplate.git
cd plotplate
make setup
```

`make setup` checks for `pixi`, runs `pixi install -e dev`, and offers (does not force) to install pre-commit hooks.
Re-running it is always safe.
The `dev` environment installs the package in editable mode, so `pixi run -e dev plotplate …` uses your working copy.

If you use `direnv`:

```sh
echo 'source_env .envrc.shared' > .envrc
direnv allow
```

## Everyday commands

```sh
make lint        # ruff, TOML, YAML, Markdown, spelling, editorconfig
make format      # ruff format, mdformat, taplo
make typecheck   # mypy
make test        # pytest on the locked environment (includes a LaTeX compile test when tectonic is available)
pixi run -e dev tox            # the same suite on every Python you have installed (3.12-3.14)
pixi run -e dev demo           # full demo build in examples/demo/ (git-ignored)
pixi run -e dev hard-case      # awkward-layout PDF and its import, in examples/hard-layout/
pixi run -e dev docs-figures   # regenerate docs/images/ from a fresh demo build
```

After any change to drawing, checks, preview, LaTeX or export, run the demo and look at `examples/demo/fig1/preview.png`.
Regenerate `docs/images/` when the pictures in the README change.

## Branches

- `main`: released state. Users install from it (or from tags on it).
- `dev`: integration branch. Feature branches merge here first.
- `feature/<topic>`: one change each, branched from `dev`, merged back with a pull request.

Merge `dev` into `main` when it is ready to release, then tag (`vX.Y.Z`).

All files are tracked on every branch, including development configuration (`pixi.toml`, lint configs, `.github/`, `CLAUDE.md`).
Keeping different files on different branches is not possible with git in a maintainable way: every merge would carry them over.
It is also not needed: an installation (`pipx`, `uv`, `pip`) only contains the package in `src/plotplate/`, never these files.

## Repository layout

| path | purpose | reaches users |
| --- | --- | --- |
| `src/plotplate/` | the package, including `presets/`, `skills/` and `demo/` | yes |
| `docs/` | documentation and generated images | as web pages |
| `tests/` | pytest suite | no |
| `scripts/` | maintenance scripts (docs images) | no |
| `examples/` | sandboxes; only the scripts and README are tracked | no |
| `tox.ini` | compatibility runs across Python versions | no |
| `pyproject.toml` | package metadata, ruff, mypy, pytest config | build only |
| `pixi.toml`, `pixi.lock`, `Makefile` | development environments and tasks | no |
| `.pre-commit-config.yaml`, `.editorconfig`, `.ecrc`, `.markdownlint.json`, `.taplo.toml`, `.yamllint.yaml`, `_typos.toml` | lint and format configuration | no |
| `.github/workflows/` | CI | no |
| `.actrc`, `.envrc.shared`, `.vscode/` | optional local tools (act, direnv, VS Code) | no |
| `.copier-answers.yml` | link to the project-meta template, for `copier update` | no |
| `CLAUDE.md`, `AGENTS.md`, `.claude/skills/` | instructions and skills for coding agents working on this repository | no |

Personal files stay out of git: `.envrc`, `.claude/settings.local.json`, `.claude/scratch/`, `.demo/`.

## Template origin

The repository skeleton was generated from the project-meta Copier template (library tier).
`.copier-answers.yml` records the template version, so `copier update` can bring later template changes.

## Enforcement policy

Config files plus CI are the real gate.
Pre-commit hooks are optional; CI enforces the same rules whatever is installed locally.
