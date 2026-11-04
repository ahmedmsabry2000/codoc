# Codoc

Local Python CLI that turns nested `codoc.spec.yaml` files into a Zensical docs site under `docs/`.

## Install

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
uv sync
uv run pre-commit install
```

Optional tools used by commands:

- [Zensical](https://github.com/zensical/zensical) for `build` / `serve` (`uv sync` installs it in this repo’s dev group)
- [Vale](https://vale.sh/) on `PATH` for `lint` when `vale.enabled` is true

## Develop

```bash
uv run ruff format .
uv run ruff check --fix .
uv run pytest
```

## Use

```bash
uv run codoc init          # interactive wizard on a TTY
uv run codoc init --yes    # non-interactive defaults (CI)
uv run codoc recommend
uv run codoc generate
uv run codoc validate
uv run codoc build
uv run codoc serve
uv run codoc lint
uv run codoc status
uv run codoc clean
```

`codoc drift` is an alias of `validate`. Full flags, outputs, and exit codes: [CLI reference](docs/reference/cli.md).

Typical loop in a target repo:

1. `codoc init` writes `codoc.yaml`, a starter nested spec, `docs/`, and `.codoc/scripts/`. On a TTY it asks for engine (Zensical/MkDocs), Vale, seed terms, and optional BYO LLM. Use `--yes` to skip prompts, or `--force` to overwrite scaffold files.
2. Edit nested `codoc.spec.yaml` files: optional prose `intent` / `audience` plus per-page `purpose`, alongside structured `manual` / `hybrid` / `auto-generated` pages and scripts under `.codoc/scripts/`.
3. `codoc generate` writes docs by type; feeds intent/audience/purpose into optional BYO draft prompts.
4. `codoc validate` checks structure and git-changed coverage, and writes `.codoc/index/rag.json`.
5. `codoc build` / `codoc serve` refresh a transient `.codoc-engine.yml` from `codoc.yaml` and run Zensical.

This repository dogfoods the same loop (`codoc.yaml` + `src/codoc/codoc.spec.yaml`).

```bash
uv run codoc generate
uv run codoc validate
uv run codoc build
uv run codoc serve
```

Sibling demo: [codoc-example](https://github.com/ahmedmsabry2000/codoc-example) (`../codoc-example` locally).

## Optional BYO LLM

Set `llm.provider` and `llm.model` in `codoc.yaml` for draft assist, optional stub rewrite (`llm.rewrite_stubs: true`), validate Stage D, and RAG embeddings. Keys stay in the environment only:

| Provider | Env | Notes |
| --- | --- | --- |
| `openai` / `openai-compatible` | `OPENAI_API_KEY` (optional `OPENAI_BASE_URL`) | Chat + embeddings (`llm.embedding_model` or `text-embedding-3-small`) |
| `anthropic` | `ANTHROPIC_API_KEY` | Chat only; RAG stays on token overlap |
| `cursor-cli` | `CURSOR_API_KEY` | Requires `agent` on `PATH` (`agent -p`); Mac Cursor CLI install |

Offline / no key: generate and validate still succeed with a stderr skip note. Warm `codoc generate` reuses `.codoc/cache/` when inputs are unchanged. Scope one spec with `codoc generate --scope src/pkg`.

`uv run python -m codoc` calls the same entry point as `uv run codoc`.
