---
codoc:
  id: cli
  type: manual
---

# CLI reference

`codoc` with no arguments, or with `--help`, prints help and exits 0. `codoc drift` is an alias of `validate`. Every other registered command name that is not implemented yet prints `codoc <name>: not implemented` to stderr and exits 2.

## `init`

Scaffolds `codoc.yaml`, one starter `src/<pkg>/codoc.spec.yaml`, `docs/index.md`, `.codoc/scripts/.gitkeep`, and the `.codoc` / `site/` / `.codoc-engine.yml` gitignore lines. Requires an existing git repository. There is no separate `setup` command.

On a TTY it runs an interactive wizard for docs engine (Zensical default, MkDocs optional), site name, Vale enable + seed terms, and optional LLM provider (`openai` / `anthropic` / `openai-compatible` / `cursor-cli`) plus model and `rewrite_stubs`. Pass `--yes` / `-y` for non-interactive defaults (Zensical + Vale on, no LLM) with no prompts (CI/tests).

Without `--force`, a second init refuses when `codoc.yaml` or that starter spec already exists unless the session is interactive: then it confirms and updates/merges `codoc.yaml` only (does not clobber the starter spec). With `--force`, it overwrites `codoc.yaml`, the starter spec, and `docs/index.md`.

When a root `zensical.yml` or `mkdocs.yml` is already present, init engulfs it into `codoc.yaml` `engine:` (`name` from the filename, plus `docs_dir`, `site_dir`, `site_name`, `theme`, `nav` when present), moves the legacy file to `.codoc/imported/`, and prints notes on stderr. Prefer `zensical.yml` when both exist. Success prints the written paths and exits 0.

## `status`

Prints a tab-separated table with columns `spec_path`, `scope_dir`, and `pages` (page count in that spec; empty specs print `0`). After the rows, prints `registry_pages` and the number of page ids across every spec. An empty spec list still prints the header and `registry_pages` with `0`.

Exits 0 when the git root contains a readable `codoc.yaml` and every spec loads. Prints `codoc status: ...` to stderr and exits 1 when the directory is not a git repository, when `codoc.yaml` is missing, when `git` is not on `PATH`, when a project or spec file is invalid, or when the same page id appears in two specs.

## `build` / `serve`

Both refresh generated configs from `codoc.yaml` `engine:` (transient root `.codoc-engine.yml` shim plus Vale under `.codoc/generated/` when enabled), then run the configured engine binary (`zensical` or `mkdocs`).

- `build` runs `<engine> build -f .codoc-engine.yml`. On success it prints the configured `site_dir` (usually `site`) and exits 0.
- `serve` stops any process named in `.codoc/serve.pid`, starts `<engine> serve -f .codoc-engine.yml` in the background (log `.codoc/logs/serve.log`, pidfile `.codoc/serve.pid`), prints `pid`, `url`, `log`, and `pidfile` lines, and exits 0.

Both print `codoc <name>: ...` to stderr and exit 1 when codegen fails, the engine name is unsupported, the binary is missing from `PATH`, or the engine exits non-zero. There is no silent fallback from `zensical` to `mkdocs`.

`.codoc-engine.yml` is generated and gitignored (not source of truth); Zensical requires a config at the project root because it rejects `docs_dir`/`site_dir` paths that leave that directory. If a root `zensical.yml` or `mkdocs.yml` remains, codegen engulfs default `engine:` fields into `codoc.yaml` when needed, moves the legacy file to `.codoc/imported/`, and notes that on stderr so `codoc.yaml` stays the only live project config.

## `lint`

Refreshes generated configs and by default harvests candidate terms from `docs_dir` into `.codoc/vocab/learned.txt`, merging them with `codoc.yaml` `terms:` into the generated Vale accept list. Pass `--no-learn` to skip harvesting. When new terms are learned it prints `codoc lint: learned N new term(s)` to stderr.

Then runs `vale --config .codoc/generated/.vale.ini <docs_dir>` when `vale.enabled` is true. On success it prints the docs dir and exits 0. When Vale reports findings or fails, lint prints `codoc lint: vale failed with exit …` to stderr and exits 1. When `vale` is missing from `PATH`, it prints `codoc lint: vale not found on PATH` and exits 1. When `vale.enabled` is false, it skips the binary, prints `codoc lint: vale disabled` to stderr, and exits 0.

## `recommend`

Prints a tab-separated table with columns `scope_dir` and `rationale` for Python packages under `src/` that lack a nested `codoc.spec.yaml` (top-level packages and nested packages with `__init__.py`). Writes a small package index to `.codoc/index/packages.json`. Ranking uses `codoc.yaml` `llm:` + env API keys when available (BYO), otherwise `.py` file count (descending); agent failures fall back to the heuristic with a stderr note. Does not write specs. An empty list still prints the header and exits 0. Errors print `codoc recommend: ...` to stderr and exit 1 (missing git repo or `codoc.yaml`).

## `generate`

Discovers every `codoc.spec.yaml`, merges the page registry, and ensures each page under `docs/` by type. Specs may carry optional prose `intent` and `audience` at the document root and optional per-page `purpose` (natural-language jobs for agents/humans; structured id/type/path/links/placeholders/script stay required for generate/validate).

- `--scope DIR` regenerates only the spec whose `scope_dir` (or spec path) matches `DIR`.
- `--no-cache` ignores the warm cache.

Parent coverage globs exclude files under nested child scopes. When the fingerprint of the owning spec, coverage sources, scripts tree, merged registry, page bodies, and llm settings is unchanged, generate reuses `.codoc/cache/generate/` and reports `action` `cached`. A draft/rewrite skip (missing key/provider) does not write a warm entry.

Page types:

- **Manual** — sync the `codoc:` frontmatter mirror (preserving sibling YAML keys) and create a stub when missing (body preserved).
- **Hybrid** — inject script stdout into `<!-- codoc:placeholder id="…" -->` regions only; a declared placeholder without a matching marker fails.
- **Auto-generated** — rewrite the whole file from scripts under `paths.scripts_dir` (default `.codoc/scripts/`, or a stub when no script is set), and append Sources / Original page / See also when declared.

Scripts must resolve under the git root and that scripts directory. When creating a new manual or hybrid page, an optional BYO LLM draft may fill the stub if `llm.provider`/`model` and an env API key are set (`openai`, `anthropic`, `openai-compatible`, or `cursor-cli` with `agent` on PATH + `CURSOR_API_KEY`); draft/rewrite prompts include scope `intent`/`audience` and page `purpose` when present; otherwise generate prints a skip note on stderr and still succeeds offline. With `llm.rewrite_stubs: true`, generate may rewrite an existing manual page only when its body is still the default `# {id}` stub; hybrid exteriors and non-stub manuals are never rewritten.

Success prints a TSV of `page_id`, `path`, and `action`, then exits 0. Errors print `codoc generate: ...` to stderr and exit 1.

## `validate` (`drift`)

Loads every spec, checks frontmatter id/type mirrors, placeholder/script paths, registry link ids, and broken relative Markdown links. Lists git-changed coverage files as candidates, writes `.codoc/index/rag.json` (embeddings attached when a BYO embed provider/key is available; otherwise token-overlap retrieval), and optionally runs BYO Stage D when `llm.provider`/`model` and an env API key are set (otherwise notes the skip on stderr). Stage D prompts include a capped inventory of owning-scope `intent`/`audience` and related page `purpose` values when present.

Success prints `rag`, optional `candidates`, then a findings TSV (`severity`, `code`, `path`, `message`) and exits 0 when there are no `error` findings. Errors print `codoc validate: ...` to stderr and exit 1; findings with severity `error` also exit 1. Staleness uses git as the primary signal.

## `clean`

Stops a background serve named in `.codoc/serve.pid` when present, then removes the configured `site_dir` (usually `site/`), `.codoc-engine.yml`, `.codoc/generated/`, and the runtime dirs `.codoc/cache`, `.codoc/index`, `.codoc/reports`, and `.codoc/logs`. Does not remove `.codoc/scripts/`, `docs/`, or a root `mkdocs.yml` / `zensical.yml`. Success prints `stopped\tserve` when a serve was stopped, then each removed path, and exits 0. Missing targets are skipped. Prints `codoc clean: ...` to stderr and exits 1 outside a git repo or when `codoc.yaml` is present but invalid.

## See also

- [Getting started](../guides/getting-started.md)
- [Package overview](package.md)
