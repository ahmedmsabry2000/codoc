"""Suggest source scope dirs that may need a nested codoc.spec.yaml."""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from codoc.config import ConfigError, load_project_config
from codoc.discover import DEFAULT_SKIP, DiscoverError, git_root

_SPEC_FILE = "codoc.spec.yaml"
_PROJECT_FILE = "codoc.yaml"
_SRC = Path("src")


class RecommendError(Exception):
    """Recommendations could not be produced."""


@dataclass(frozen=True, slots=True)
class SpecRecommendation:
    """One proposed scope directory relative to the git root."""

    scope_dir: Path
    rationale: str
    py_files: int = 0


@dataclass(frozen=True, slots=True)
class RecommendResult:
    rows: tuple[SpecRecommendation, ...]


class RecommendationRanker(Protocol):
    """Order candidate recommendations (heuristic today; BYO agent later)."""

    def rank(
        self, rows: Sequence[SpecRecommendation]
    ) -> tuple[SpecRecommendation, ...]: ...


class HeuristicRanker:
    """Prefer more Python files, then stable path order."""

    def rank(
        self, rows: Sequence[SpecRecommendation]
    ) -> tuple[SpecRecommendation, ...]:
        return tuple(
            sorted(rows, key=lambda row: (-row.py_files, row.scope_dir.as_posix()))
        )


class AgentRanker:
    """
    Stub for BYO LLM / index-backed ranking.

    Falls back to HeuristicRanker until a provider is wired.
    """

    def __init__(self, inner: RecommendationRanker | None = None) -> None:
        self._inner = inner if inner is not None else HeuristicRanker()

    def rank(
        self, rows: Sequence[SpecRecommendation]
    ) -> tuple[SpecRecommendation, ...]:
        # shortcut: no LLM yet; upgrade when LlmProvider can score scopes
        return self._inner.rank(rows)


def run_recommend(
    start: Path | None = None,
    *,
    ranker: RecommendationRanker | None = None,
) -> RecommendResult:
    """List src/ packages that lack a nested codoc.spec.yaml."""
    if start is None:
        start = Path.cwd()
    try:
        root = git_root(start)
    except DiscoverError as err:
        raise RecommendError(str(err)) from err
    project = root / _PROJECT_FILE
    if not project.is_file():
        raise RecommendError(f"{_PROJECT_FILE} not found at {project}")
    try:
        config = load_project_config(project)
    except ConfigError as err:
        raise RecommendError(str(err)) from err

    skip = DEFAULT_SKIP | config.ignore_dirs
    candidates = _src_package_candidates(root, skip)
    active = ranker if ranker is not None else HeuristicRanker()
    return RecommendResult(rows=active.rank(candidates))


def _src_package_candidates(
    root: Path, skip: frozenset[str]
) -> tuple[SpecRecommendation, ...]:
    src = root / _SRC
    if not src.is_dir():
        return ()
    rows: list[SpecRecommendation] = []
    try:
        children = sorted(src.iterdir(), key=lambda path: path.name)
    except OSError as err:
        raise RecommendError(f"cannot read {src}, {err.strerror}") from err
    for child in children:
        if not child.is_dir() or child.is_symlink():
            continue
        name = child.name
        if name in skip or name.startswith("."):
            continue
        if name.endswith((".egg-info", ".dist-info")):
            continue
        if not _looks_like_python_package(child):
            continue
        if (child / _SPEC_FILE).is_file():
            continue
        scope = _SRC / name
        py_files = _count_py_files(child, skip)
        rationale = (
            f"Python package under src/ without {_SPEC_FILE} "
            f"({py_files} .py file{'s' if py_files != 1 else ''})"
        )
        rows.append(
            SpecRecommendation(scope_dir=scope, rationale=rationale, py_files=py_files)
        )
    return tuple(rows)


def _looks_like_python_package(path: Path) -> bool:
    if (path / "__init__.py").is_file():
        return True
    try:
        for entry in path.iterdir():
            if entry.is_file() and entry.suffix == ".py":
                return True
    except OSError:
        return False
    return False


def _count_py_files(path: Path, skip: frozenset[str]) -> int:
    total = 0
    try:
        for _dirpath, dirnames, filenames in os.walk(path, followlinks=False):
            dirnames[:] = [
                name
                for name in dirnames
                if name not in skip
                and not name.startswith(".")
                and not name.endswith((".egg-info", ".dist-info"))
            ]
            total += sum(1 for name in filenames if name.endswith(".py"))
    except OSError:
        return total
    return total
