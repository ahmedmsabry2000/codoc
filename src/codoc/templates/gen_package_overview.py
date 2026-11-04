"""Emit a short auto-generated package overview page."""

import os
from pathlib import Path

scope = Path(os.environ["CODOC_SCOPE_DIR"])
root = Path(os.environ["CODOC_ROOT"])
package = (root / scope).resolve()
py_files = sorted(path.name for path in package.glob("*.py") if path.is_file())
print(f"# {scope.name} overview")
print()
print(f"Package scope `{scope.as_posix()}`.")
print()
if py_files:
    print("Python modules:")
    print()
    for name in py_files:
        print(f"- `{name}`")
else:
    print("No top-level Python modules found under this scope.")
