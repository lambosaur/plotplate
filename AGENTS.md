# plotplate

This is a one-off project, not part of a project with its own meta repo. Conventions live directly
in this repo: this file, `.claude/skills/`, and inline config comments.

This file exists alongside `CLAUDE.md` for tools that read `AGENTS.md` specifically.
The two files should stay identical in content for this project; edit both if either
changes.

## Project-specific notes

- This package is a library for figure layouts; `docs/design-notes.md` records the agreed design and open questions.
  Read it before changing behaviour.
- The demo ships inside the package (`src/plotplate/demo/`) and is the end-to-end reference:
  run `pixi run -e dev demo` after any change to drawing, checks, preview, LaTeX or export, then look at
  `examples/demo/fig1/preview.png`. Regenerate README images with `pixi run -e dev docs-figures`.
- Branches: `main` (released), `dev` (integration), `feature/<topic>` from `dev`. See `CONTRIBUTING.md`.
- Agent skills shipped to users live in `src/plotplate/skills/` (package data), not in `.claude/skills/`.
- Journal presets must keep `sources` and an honest `verified` field; never present unverified values as official.
- Scratch work goes to `.claude/scratch/` (git-ignored).
