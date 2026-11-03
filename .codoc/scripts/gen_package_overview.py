"""Emit an auto-generated overview of the Codoc package tree."""

import os
from pathlib import Path

root = Path(os.environ["CODOC_ROOT"])
scope = Path(os.environ["CODOC_SCOPE_DIR"])
base = root / scope
dirs = sorted(
    path.name
    for path in base.iterdir()
    if path.is_dir() and not path.name.startswith("__") and path.name != "codoc.spec.yaml"
)
print("# Codoc overview")
print()
print(f"Scope `{scope.as_posix()}`.")
print()
print("Top-level modules:")
print()
for name in dirs:
    print(f"- `{name}/`")
for path in sorted(base.glob("*.py")):
    if path.name == "codoc.spec.yaml":
        continue
    print(f"- `{path.name}`")
