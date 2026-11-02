# Codoc agent notes

This repository is the Codoc Python package. The installable command is `codoc`.

## Working in this tree

- Put CLI command names and aliases only in `COMMANDS` in `src/codoc/cli.py`.
- Unknown work stays out of the tree. Add a module when you are implementing it, not as an empty placeholder.
- Do not expand scope beyond the change you were asked to make.
- Do not add roadmap, ticket, milestone, or product-vision notes to the repo (rules, comments, README, commit messages that narrate a plan). Keep the tree about the code that exists.

## Current CLI behavior

`codoc` with no arguments, or with `--help`, prints help and exits 0.

`codoc init` scaffolds `codoc.yaml`, one starter `src/<pkg>/codoc.spec.yaml`, `docs/index.md`, `.codoc/scripts/.gitkeep`, and the `.codoc` / `site/` / `mkdocs.yml` gitignore lines. It requires an existing git repository. Without `--force`, it refuses when `codoc.yaml` or that starter spec already exists. With `--force`, it overwrites `codoc.yaml`, the starter spec, and `docs/index.md`. Success prints the written paths and exits 0.

`codoc status` prints a tab-separated table with the columns `spec_path`, `scope_dir`, and `pages`. The pages column is the number of pages in that spec. An empty spec prints `0`. After the spec rows, status prints `registry_pages` and the number of page ids across every spec. An empty spec list still prints the header and `registry_pages` with `0`. The command exits 0 when the git root contains a readable `codoc.yaml` and every spec loads. The command prints `codoc status: ...` to stderr and exits 1 when the directory is not a git repository, when `codoc.yaml` is missing, when `git` is not on `PATH`, when a project or spec file is invalid, or when the same page id appears in two specs.

`codoc build` refreshes generated configs from `codoc.yaml` (root `mkdocs.yml` shim plus Vale under `.codoc/generated/` when enabled), then runs the configured engine binary (`zensical` or `mkdocs`) as `<engine> build -f mkdocs.yml`. On success it prints the configured `site_dir` (usually `site`) and exits 0. `codoc serve` does the same codegen, stops any process named in `.codoc/serve.pid`, starts `<engine> serve -f mkdocs.yml` in the background (log `.codoc/logs/serve.log`, pidfile `.codoc/serve.pid`), prints `pid`, `url`, `log`, and `pidfile` lines, and exits 0. Both print `codoc <name>: ...` to stderr and exit 1 when codegen fails, the engine name is unsupported, the binary is missing from `PATH`, or the engine exits non-zero. There is no silent fallback from `zensical` to `mkdocs`. Root `mkdocs.yml` is generated (gitignored); Zensical requires the config file to sit at the project root because it rejects `docs_dir`/`site_dir` paths that leave that directory.

`codoc lint` refreshes generated configs, then runs `vale --config .codoc/generated/.vale.ini <docs_dir>` when `vale.enabled` is true. On success it prints the docs dir and exits 0. When Vale reports findings or fails, lint prints `codoc lint: vale failed with exit …` to stderr and exits 1. When `vale` is missing from `PATH`, it prints `codoc lint: vale not found on PATH` and exits 1. When `vale.enabled` is false, it skips the binary, prints `codoc lint: vale disabled` to stderr, and exits 0.

`codoc clean` stops a background serve named in `.codoc/serve.pid` when present, then removes the configured `site_dir` (usually `site/`), the generated root `mkdocs.yml`, `.codoc/generated/`, and the runtime dirs `.codoc/cache`, `.codoc/index`, `.codoc/reports`, and `.codoc/logs`. It does not remove `.codoc/scripts/` or `docs/`. Success prints `stopped\tserve` when a serve was stopped, then each removed path, and exits 0. Missing targets are skipped. It prints `codoc clean: ...` to stderr and exits 1 outside a git repo or when `codoc.yaml` is present but invalid.

Every other registered command prints `codoc <name>: not implemented` to stderr and exits 2. `drift` is an alias of `validate`.
