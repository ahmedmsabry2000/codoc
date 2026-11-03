# Codoc agent notes

This repository is the Codoc Python package. The installable command is `codoc`.

## Working in this tree

- Put CLI command names and aliases only in `COMMANDS` in `src/codoc/cli/`.
- Keep package code under `src/codoc/{cli,commands,config,discover,engine,model}/`. Mirror that layout under `tests/` (`tests/support/` for shared fixtures).
- Unknown work stays out of the tree. Add a module when you are implementing it, not as an empty placeholder.
- Do not expand scope beyond the change you were asked to make.
- Do not add roadmap, ticket, milestone, or product-vision notes to the repo (rules, comments, README, commit messages that narrate a plan). Keep the tree about the code that exists.
- After a feature PR merges, delete the local branch and prune stale remote-tracking refs (`git branch -d <branch>`; `git fetch --prune`).

## Current CLI behavior

`codoc` with no arguments, or with `--help`, prints help and exits 0.

`codoc init` scaffolds `codoc.yaml`, one starter `src/<pkg>/codoc.spec.yaml`, `docs/index.md`, `.codoc/scripts/.gitkeep`, and the `.codoc` / `site/` / `.codoc-engine.yml` gitignore lines. It requires an existing git repository. Without `--force`, it refuses when `codoc.yaml` or that starter spec already exists. With `--force`, it overwrites `codoc.yaml`, the starter spec, and `docs/index.md`. When a root `zensical.yml` or `mkdocs.yml` is already present, init imports `docs_dir` / `site_dir` (and engine name from the filename) into `codoc.yaml` `engine:`, leaves the legacy file in place, and prints a warning on stderr. Prefer `zensical.yml` when both exist. Success prints the written paths and exits 0.

`codoc status` prints a tab-separated table with the columns `spec_path`, `scope_dir`, and `pages`. The pages column is the number of pages in that spec. An empty spec prints `0`. After the spec rows, status prints `registry_pages` and the number of page ids across every spec. An empty spec list still prints the header and `registry_pages` with `0`. The command exits 0 when the git root contains a readable `codoc.yaml` and every spec loads. The command prints `codoc status: ...` to stderr and exits 1 when the directory is not a git repository, when `codoc.yaml` is missing, when `git` is not on `PATH`, when a project or spec file is invalid, or when the same page id appears in two specs.

`codoc build` refreshes generated configs from `codoc.yaml` `engine:` (transient root `.codoc-engine.yml` shim plus Vale under `.codoc/generated/` when enabled), then runs the configured engine binary (`zensical` or `mkdocs`) as `<engine> build -f .codoc-engine.yml`. On success it prints the configured `site_dir` (usually `site`) and exits 0. `codoc serve` does the same codegen, stops any process named in `.codoc/serve.pid`, starts `<engine> serve -f .codoc-engine.yml` in the background (log `.codoc/logs/serve.log`, pidfile `.codoc/serve.pid`), prints `pid`, `url`, `log`, and `pidfile` lines, and exits 0. Both print `codoc <name>: ...` to stderr and exit 1 when codegen fails, the engine name is unsupported, the binary is missing from `PATH`, or the engine exits non-zero. There is no silent fallback from `zensical` to `mkdocs`. `.codoc-engine.yml` is generated and gitignored (not SoT); Zensical requires a config at the project root because it rejects `docs_dir`/`site_dir` paths that leave that directory. If a root `zensical.yml` or `mkdocs.yml` remains and `codoc.yaml` `engine:` fields are still at defaults, codegen imports those fields into `codoc.yaml`, warns on stderr, and leaves the legacy file in place (never deletes it).

`codoc lint` refreshes generated configs, then runs `vale --config .codoc/generated/.vale.ini <docs_dir>` when `vale.enabled` is true. On success it prints the docs dir and exits 0. When Vale reports findings or fails, lint prints `codoc lint: vale failed with exit …` to stderr and exits 1. When `vale` is missing from `PATH`, it prints `codoc lint: vale not found on PATH` and exits 1. When `vale.enabled` is false, it skips the binary, prints `codoc lint: vale disabled` to stderr, and exits 0.

`codoc clean` stops a background serve named in `.codoc/serve.pid` when present, then removes the configured `site_dir` (usually `site/`), `.codoc-engine.yml`, `.codoc/generated/`, and the runtime dirs `.codoc/cache`, `.codoc/index`, `.codoc/reports`, and `.codoc/logs`. It does not remove `.codoc/scripts/`, `docs/`, or a root `mkdocs.yml` / `zensical.yml`. Success prints `stopped\tserve` when a serve was stopped, then each removed path, and exits 0. Missing targets are skipped. It prints `codoc clean: ...` to stderr and exits 1 outside a git repo or when `codoc.yaml` is present but invalid.

Every other registered command prints `codoc <name>: not implemented` to stderr and exits 2. `drift` is an alias of `validate`.
