# Codoc

Codoc is a local Python CLI. This repository is the installable tool package.

## Install

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pre-commit install
```

## Format and lint

```bash
uv run ruff format .
uv run ruff check --fix .
```

Git hooks run the same checks on commit via pre-commit (`uv run pre-commit run --all-files`).

## Test

```bash
uv run python -m unittest discover -s tests -v
```

## Run

```bash
uv run codoc
uv run codoc --help
uv run codoc init
uv run codoc status
uv run codoc build
uv run codoc serve
uv run codoc lint
uv run codoc clean
uv run codoc generate
uv run codoc drift
```

With no arguments, `codoc` prints help and exits 0. `codoc init` writes project files in a git repository. `codoc status` lists each `codoc.spec.yaml` in the git repo. The pages column is the number of pages in that spec. After those rows, status prints `registry_pages` and the count of page ids in every spec. `codoc build` and `codoc serve` write a generated root `mkdocs.yml` (and Vale files under `.codoc/generated/` when enabled) then invoke the engine from `codoc.yaml` (`zensical` by default; install it on `PATH`). Serve runs in the background and records `.codoc/serve.pid` plus `.codoc/logs/serve.log`. `codoc lint` writes those generated configs then runs `vale` against the docs dir (`vale` must be on `PATH`; set `vale.enabled: false` to skip). `codoc clean` stops serve if needed and removes `site/`, generated `mkdocs.yml`, `.codoc/generated/`, and other `.codoc` runtime dirs while keeping `.codoc/scripts/`. Commands that are not implemented yet print `codoc <name>: not implemented` to stderr and exit 2. `codoc drift` uses the same behavior as `validate`.

`uv run python -m codoc` calls the same entry point.
