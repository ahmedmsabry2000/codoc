# Codoc agent notes

This repository is the Codoc Python package. The installable command is `codoc`.

## Working in this tree

- Put CLI command names and aliases only in `COMMANDS` in `src/codoc/cli.py`.
- Unknown work stays out of the tree. Add a module when you are implementing it, not as an empty placeholder.
- Do not expand scope beyond the change you were asked to make.
- Do not add roadmap, ticket, milestone, or product-vision notes to the repo (rules, comments, README, commit messages that narrate a plan). Keep the tree about the code that exists.

## Current CLI behavior

`codoc` with no arguments, or with `--help`, prints help and exits 0.

`codoc status` prints a tab-separated table with the columns `spec_path`, `scope_dir`, and `pages`. The pages column is the number of pages in that spec. An empty spec prints `0`. The command exits 0 when the git root contains a readable `codoc.yaml` and every spec loads. An empty spec list still prints the header. The command prints `codoc status: ...` to stderr and exits 1 when the directory is not a git repository, when `codoc.yaml` is missing, when `git` is not on `PATH`, or when a project or spec file is invalid.

Every other registered command prints `codoc <name>: not implemented` to stderr and exits 2. `drift` is an alias of `validate`.
