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
codoc status
codoc generate
codoc drift
```

With no arguments, `codoc` prints help and exits 0. `codoc status` lists each `codoc.spec.yaml` in the git repo. The pages column is the number of pages in that spec. Commands that are not implemented yet print `codoc <name>: not implemented` to stderr and exit 2. `codoc drift` uses the same behavior as `validate`.

`python -m codoc` calls the same entry point.
