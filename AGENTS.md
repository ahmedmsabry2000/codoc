# Codoc agent notes

This repository is the Codoc Python package. The installable command is `codoc`.

## Working in this tree

- Put CLI command names and aliases only in `COMMANDS` in `src/codoc/cli.py`.
- Unknown work stays out of the tree. Add a module when you are implementing it, not as an empty placeholder.
- Do not expand scope beyond the change you were asked to make.
- Do not add roadmap, ticket, milestone, or product-vision notes to the repo (rules, comments, README, commit messages that narrate a plan). Keep the tree about the code that exists.

## Current CLI behavior

`codoc` with no arguments, or with `--help`, prints help and exits 0.

`codoc init` scaffolds `codoc.yaml`, one starter `src/<pkg>/codoc.spec.yaml`, `docs/index.md`, `.codoc/scripts/.gitkeep`, and the `.codoc` / `site/` gitignore lines. It requires an existing git repository. Without `--force`, it refuses when `codoc.yaml` or that starter spec already exists. With `--force`, it overwrites `codoc.yaml`, the starter spec, and `docs/index.md`. Success prints the written paths and exits 0.

`codoc status` prints a tab-separated table with the columns `spec_path`, `scope_dir`, and `pages`. The pages column is the number of pages in that spec. An empty spec prints `0`. After the spec rows, status prints `registry_pages` and the number of page ids across every spec. An empty spec list still prints the header and `registry_pages` with `0`. The command exits 0 when the git root contains a readable `codoc.yaml` and every spec loads. The command prints `codoc status: ...` to stderr and exits 1 when the directory is not a git repository, when `codoc.yaml` is missing, when `git` is not on `PATH`, when a project or spec file is invalid, or when the same page id appears in two specs.

`codoc build`, `codoc serve`, and `codoc lint` refresh generated configs under `.codoc/generated/` from `codoc.yaml` (engine `mkdocs.yml`, and when Vale is enabled `.vale.ini` plus Vocab accept/reject). They print the written paths, print `codoc <name>: site tool not invoked` to stderr, and exit 0. They print `codoc <name>: ...` to stderr and exit 1 when the git root or `codoc.yaml` is missing or invalid, or when the engine name is not `zensical` or `mkdocs`. The site tool and Vale binary are not run yet.

Every other registered command prints `codoc <name>: not implemented` to stderr and exits 2. `drift` is an alias of `validate`.
