# Codoc

Codoc is a local Python CLI. This repository is the installable tool package.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Run

```bash
codoc
codoc --help
codoc init
codoc status
codoc build
codoc serve
codoc lint
codoc generate
codoc drift
```

With no arguments, `codoc` prints help and exits 0. `codoc init` writes project files in a git repository. `codoc status` lists each `codoc.spec.yaml` in the git repo. The pages column is the number of pages in that spec. After those rows, status prints `registry_pages` and the count of page ids in every spec. `codoc build` and `codoc serve` write a generated root `mkdocs.yml` (and Vale files under `.codoc/generated/` when enabled) then invoke the engine from `codoc.yaml` (`zensical` by default; install it on `PATH`). Serve runs in the background and records `.codoc/serve.pid` plus `.codoc/logs/serve.log`. `codoc lint` writes those generated configs only (Vale is not invoked yet). Commands that are not implemented yet print `codoc <name>: not implemented` to stderr and exit 2. `codoc drift` uses the same behavior as `validate`.

`python -m codoc` calls the same entry point.
