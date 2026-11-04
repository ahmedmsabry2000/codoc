---
codoc:
  id: guide
  type: hybrid
---

# Getting started

Install Codoc in a git repository, add specs next to the code they document, then generate and serve.

```bash
uv sync
uv run codoc init
uv run codoc generate
uv run codoc serve
```

<!-- codoc:placeholder id="command-table" -->
| Command | What it does |
| --- | --- |
| `codoc init` | Scaffold `codoc.yaml`, a starter spec, and `docs/` |
| `codoc recommend` | List `src/` packages missing a nested spec |
| `codoc generate` | Write or update docs by page type |
| `codoc validate` | Structural checks, git candidates, RAG index |
| `codoc build` / `serve` | Zensical site build or local preview |
| `codoc lint` | Vale against `docs/` |
| `codoc clean` | Stop serve and remove generated outputs |
<!-- /codoc:placeholder -->

Put parse and inject scripts under `.codoc/scripts/`. Keep project settings in root `codoc.yaml` and page declarations in nested `codoc.spec.yaml` files.

## See also

- [CLI reference](../reference/cli.md)
- [Package overview](../reference/package.md)
