# Codoc agent notes

This repository is the Codoc Python package. The installable command is `codoc`.

## Working in this tree

- Put CLI command names and aliases only in `COMMANDS` in `src/codoc/cli.py`.
- Unknown work stays out of the tree. Add a module when you are implementing it, not as an empty placeholder.
- Do not expand scope beyond the change you were asked to make.
- Do not add roadmap, ticket, milestone, or product-vision notes to the repo (rules, comments, README, commit messages that narrate a plan). Keep the tree about the code that exists.

## Current CLI behavior

`codoc` with no arguments (or `--help`) prints help and exits 0. Every registered command that is not implemented yet prints `codoc <name>: not implemented` to stderr and exits 2. `drift` is an alias of `validate`.
