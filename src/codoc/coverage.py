"""Expand coverage globs under a scope, excluding nested child scopes."""

from collections.abc import Sequence
from pathlib import Path


def expand_coverage_paths(
    root: Path,
    scope_dir: Path,
    patterns: Sequence[str],
    *,
    exclude_scopes: Sequence[Path] = (),
) -> tuple[str, ...]:
    """
    Expand coverage patterns relative to scope_dir into repo-relative paths.

    Files that fall under any exclude_scopes path (child specs) are omitted so a
    parent glob like `**/*.py` does not double-count a nested package that owns
    its own codoc.spec.yaml.
    """
    base = root / scope_dir
    found: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        if any(char in pattern for char in "*?["):
            matches = sorted(base.glob(pattern))
            for match in matches:
                if not match.is_file():
                    continue
                rel = match.relative_to(root).as_posix()
                if _under_excluded(rel, exclude_scopes):
                    continue
                if rel not in seen:
                    seen.add(rel)
                    found.append(rel)
        else:
            candidate = base / pattern
            if candidate.is_file():
                rel = candidate.relative_to(root).as_posix()
                if _under_excluded(rel, exclude_scopes):
                    continue
                if rel not in seen:
                    seen.add(rel)
                    found.append(rel)
    return tuple(found)


def _under_excluded(rel_posix: str, exclude_scopes: Sequence[Path]) -> bool:
    rel = Path(rel_posix)
    for scope in exclude_scopes:
        if scope == Path("."):
            continue
        if rel == scope or rel.is_relative_to(scope):
            return True
    return False
