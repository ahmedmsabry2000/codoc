"""Inject the Codoc CLI command table into the getting-started guide."""

print("| Command | What it does |")
print("| --- | --- |")
print("| `codoc init` | Scaffold `codoc.yaml`, a starter spec, and `docs/` |")
print("| `codoc recommend` | List `src/` packages missing a nested spec |")
print("| `codoc generate` | Write or update docs by page type |")
print("| `codoc validate` | Structural checks, git candidates, RAG index |")
print("| `codoc build` / `serve` | Zensical site build or local preview |")
print("| `codoc lint` | Vale against `docs/` |")
print("| `codoc clean` | Stop serve and remove generated outputs |")
