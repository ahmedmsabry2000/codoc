# Codoc agent notes

This checkout is the Codoc tool. It is a Python package and a `codoc` command. It is not a user project yet.

## Slice 1 limits

T1 does not add root `codoc.yaml`, `docs/`, or `.codoc/`. Those files belong to `codoc init` (T1b) and later dogfood.

T1 does not implement generate, validate, Zensical, Vale, or the LLM. Each known command prints `codoc <behavior>: not implemented` to stderr and exits 2. Add a command by inserting one `Command` in `COMMANDS` in `src/codoc/cli.py`.

## Product limits

The POC is macOS, a Python CLI, and one Python git repo. Codoc requires git. Validate uses git as the staleness signal.

A user project has one root `codoc.yaml` and many `codoc.spec.yaml` files found by walking the repo. All specs write Markdown into top-level `docs/`. Parse and inject scripts live in `.codoc/scripts/` and stay tracked. Engine and Vale files are generated under `.codoc/generated/`.

Doc types are `manual`, `hybrid`, and `auto-generated`. The spec owns the type. The type is a pipeline role, not a record of who wrote the page.

The site engine is Zensical. Lint is Vale. Users bring their own LLM keys. The POC does not add other languages, monorepo workspace roots, multi-repo discovery, or SaaS.

## Where decisions live

Read product decisions from the Project store paths in `README.md`. Where `preferences.md` still asks for reverse "referenced from" links, follow `open-questions.md` and `product-plan.md`. The POC keeps the light link model. That model is page ids, See also, Original, and Sources.

## Later modules

T1d adds `src/codoc/discover.py`. T2 and T2e add `src/codoc/schemas.py`. The later module map in `product-plan.md` waits for those tickets. Do not add empty packages under `src/codoc`.
