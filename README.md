# Codoc

Local Python CLI that turns nested `codoc.spec.yaml` files into a Zensical docs site under `docs/`.

## Install

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
uv sync
uv run pre-commit install
```

Optional tools used by commands:

- [Zensical](https://github.com/zensical/zensical) for `build` / `serve` (`uv sync` installs it in this repo’s dev group)
- [Vale](https://vale.sh/) on `PATH` for `lint` when `vale.enabled` is true

## Develop

```bash
uv run ruff format .
uv run ruff check --fix .
uv run pytest
```

## Use

```bash
uv run codoc init
uv run codoc recommend
uv run codoc generate
uv run codoc validate
uv run codoc build
uv run codoc serve
uv run codoc lint
uv run codoc status
uv run codoc clean
```

`codoc drift` is an alias of `validate`.

Typical loop in a target repo:

1. `codoc init` writes `codoc.yaml`, a starter nested spec, `docs/`, and `.codoc/scripts/`.
2. Edit specs (`manual` / `hybrid` / `auto-generated` pages) and scripts under `.codoc/scripts/`.
3. `codoc generate` writes docs by type (manual keeps body, hybrid injects placeholders, auto runs scripts).
4. `codoc validate` checks frontmatter, links, scripts, git-changed coverage files, and writes `.codoc/index/rag.json`.
5. `codoc build` / `codoc serve` refresh a transient `.codoc-engine.yml` from `codoc.yaml` and run Zensical.

This repository dogfoods the same loop (`codoc.yaml` + `src/codoc/codoc.spec.yaml`).

```bash
uv run codoc generate
uv run codoc validate
uv run codoc build
uv run codoc serve
```

Sibling demo: [codoc-example](https://github.com/ahmedmsabry2000/codoc-example) (`../codoc-example` locally).

`uv run python -m codoc` calls the same entry point as `uv run codoc`.
