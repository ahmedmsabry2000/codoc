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
uv run pytest
```

## Run

```bash
uv run codoc
uv run codoc --help
uv run codoc init
uv run codoc status
uv run codoc recommend
uv run codoc build
uv run codoc serve
uv run codoc lint
uv run codoc clean
uv run codoc generate
uv run codoc drift
```

With no arguments, `codoc` prints help and exits 0. `codoc init` writes project files in a git repository. `codoc status` lists each `codoc.spec.yaml` in the git repo. The pages column is the number of pages in that spec. After those rows, status prints `registry_pages` and the count of page ids in every spec. `codoc recommend` lists `src/` packages that lack a nested `codoc.spec.yaml` (path + short rationale; recommend-only). Engine settings live in `codoc.yaml` (`engine:` only — one user-facing project config). On `init` or adopt codegen, an existing root `zensical.yml` or `mkdocs.yml` is engulfed into that section (`docs_dir`, `site_dir`, `site_name`, `theme`, `nav`) and moved under `.codoc/imported/`. `codoc build` and `codoc serve` refresh a transient root `.codoc-engine.yml` shim from `codoc.yaml` (and Vale under `.codoc/generated/` when enabled), then run the configured binary (`zensical` by default; install it on `PATH`) as `<engine> build|serve -f .codoc-engine.yml`. Serve runs in the background and records `.codoc/serve.pid` plus `.codoc/logs/serve.log`. `codoc lint` refreshes those generated configs then runs `vale` against the docs dir (`vale` must be on `PATH`; set `vale.enabled: false` to skip). `codoc clean` stops serve if needed and removes `site/`, `.codoc-engine.yml`, `.codoc/generated/`, and other `.codoc` runtime dirs while keeping `.codoc/scripts/`. Commands that are not implemented yet print `codoc <name>: not implemented` to stderr and exit 2. `codoc drift` uses the same behavior as `validate`.

`uv run python -m codoc` calls the same entry point.
