# Codoc agent notes

This checkout is the Codoc *tool* package: a Python package and a `codoc` command. It is not yet a Codoc *user project* (no root `codoc.yaml`, specs, or `docs/`).

## Slice 1 limits

T1 does not add root `codoc.yaml`, `docs/`, or `.codoc/`. Those files come from `codoc init` (**T1b**) in a target repo. Dogfood of *this* checkout is **T25**, not T1b.

T1 does not implement generate, validate, Zensical, Vale, or the LLM. Each known command prints `codoc <name>: not implemented` to stderr and exits **2** (local stub convention, so scripts cannot treat NYI as success). Add a command by inserting one `Command` in `COMMANDS` in `src/codoc/cli.py`. `drift` is an alias of `validate`, not a second behavior.

## Product limits (POC)

- macOS pilot only
- Python CLI; Python target code only
- Single git repo; Codoc requires git; validate is git-first
- One root `codoc.yaml` + many walk-discovered `codoc.spec.yaml` (scope = directory containing the file)
- Shared top-level `docs/`; `.codoc/scripts/` tracked; engine/Vale generated under `.codoc/generated/`
- Doc types `manual` | `hybrid` | `auto-generated`; the spec owns the type
- Zensical site engine; Vale lint; BYO LLM keys (no Codoc-hosted model required)
- No multi-language extractors, monorepo workspace roots, multi-repo discovery, or SaaS in POC

Do not invent product decisions. Consult the Project store paths listed in `README.md`.

## Where decisions live

Read product decisions from the Project store paths in `README.md`. Where `preferences.md` still asks for reverse "referenced from" links, follow `open-questions.md` and `product-plan.md`. The POC keeps the light link model (page ids, See also, Original, Sources).

## Modules not created in slice 1

Do not pre-create empty packages. Later tickets add modules when they have code. Plan names that wait include:

- `generate`, `validate`, `lint`, `rag`, `agents`, `scripts_gen`
- `discover`, `engines`, `core` (and related) when their tickets land

T1d starts discovery. T2 / T2e start schemas. Do not lock filenames ahead of those tickets beyond what the ticket names.
