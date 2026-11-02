import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from codoc.config import load_project_config

_SPEC_FILE = "codoc.spec.yaml"
_PROJECT_FILE = "codoc.yaml"

DEFAULT_SKIP: frozenset[str] = frozenset(
    {
        ".git",
        ".codoc",
        "site",
        ".venv",
        "venv",
        "__pycache__",
    }
)


class DiscoverError(Exception):
    """The git root could not be listed."""


@dataclass(frozen=True, slots=True)
class SpecUnit:
    """One spec file and the directory that contains it.

    Both paths are relative to the git root. scope_dir is spec_path.parent.
    A spec at the git root uses `.` as its scope.
    """

    spec_path: Path
    scope_dir: Path

    def __post_init__(self) -> None:
        if self.spec_path.is_absolute() or self.scope_dir.is_absolute():
            raise ValueError("SpecUnit paths are repo-root-relative")
        if ".." in self.spec_path.parts or ".." in self.scope_dir.parts:
            raise ValueError("SpecUnit paths must not contain '..'")
        if self.spec_path.name != _SPEC_FILE:
            raise ValueError(f"spec_path must be named {_SPEC_FILE}")
        if self.spec_path.parent != self.scope_dir:
            raise ValueError("scope_dir must be the parent of spec_path")


def git_root(start: Path) -> Path:
    """Return the absolute git toplevel of start."""
    try:
        completed = subprocess.run(
            ["git", "-C", os.fspath(start), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as err:
        raise DiscoverError("git not on PATH") from err
    except subprocess.CalledProcessError as err:
        raise DiscoverError(f"not a git repository at {start}") from err
    return Path(completed.stdout.strip())


def discover(start: Path | None = None) -> tuple[SpecUnit, ...]:
    """Return spec units for the git repo that contains start.

    start defaults to the current directory. The walk covers the whole
    repository. The result is sorted by spec_path. Spec files are not opened.
    """
    if start is None:
        start = Path.cwd()
    root = git_root(start)
    project = root / _PROJECT_FILE
    if not project.is_file():
        raise DiscoverError(f"{_PROJECT_FILE} not found at {project}")
    config = load_project_config(project)
    skip = DEFAULT_SKIP | config.ignore_dirs
    try:
        return _walk(root, skip)
    except OSError as err:
        raise DiscoverError(f"cannot read {root}, {err.strerror}") from err


def child_scopes(units: Sequence[SpecUnit]) -> dict[Path, tuple[Path, ...]]:
    """Map each scope to the nearest scope directories strictly inside it.

    Keys follow the order of units. Values are sorted by path. Duplicate
    scope directories raise ValueError.
    """
    scopes = [unit.scope_dir for unit in units]
    if len(set(scopes)) != len(scopes):
        raise ValueError("duplicate scope_dir")
    scope_set = set(scopes)
    out: dict[Path, tuple[Path, ...]] = {}
    for scope in scopes:
        hits: list[Path] = []
        for other in scopes:
            if other == scope or not other.is_relative_to(scope):
                continue
            parent = other.parent
            blocked = False
            while parent != scope:
                if parent in scope_set:
                    blocked = True
                    break
                nxt = parent.parent
                if nxt == parent:
                    blocked = True
                    break
                parent = nxt
            if not blocked:
                hits.append(other)
        out[scope] = tuple(sorted(hits, key=lambda path: path.as_posix()))
    return out


def _walk(root: Path, skip: frozenset[str]) -> tuple[SpecUnit, ...]:
    units: list[SpecUnit] = []

    def raise_error(err: OSError) -> None:
        raise err

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=raise_error):
        dirnames[:] = [name for name in dirnames if name not in skip]
        if _SPEC_FILE not in filenames:
            continue
        rel = (Path(dirpath) / _SPEC_FILE).relative_to(root)
        units.append(SpecUnit(rel, rel.parent))
    units.sort(key=lambda unit: unit.spec_path.as_posix())
    return tuple(units)
