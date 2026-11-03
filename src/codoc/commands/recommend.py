"""Suggest source scope dirs that may need a nested codoc.spec.yaml."""

import json
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from codoc.config import ConfigError, LlmConfig, load_project_config
from codoc.discover import DEFAULT_SKIP, DiscoverError, git_root
from codoc.llm import LlmError, chat_completion, resolve_api_key

_SPEC_FILE = "codoc.spec.yaml"
_PROJECT_FILE = "codoc.yaml"
_SRC = Path("src")
_INDEX_DIR = Path(".codoc") / "index"
_INDEX_FILE = _INDEX_DIR / "packages.json"


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
    ranking: str = "heuristic"
    notes: tuple[str, ...] = ()


class RecommendationRanker(Protocol):
    """Order candidate recommendations."""

    def rank(self, rows: Sequence[SpecRecommendation]) -> tuple[SpecRecommendation, ...]: ...


class HeuristicRanker:
    """Prefer more Python files, then stable path order."""

    def rank(self, rows: Sequence[SpecRecommendation]) -> tuple[SpecRecommendation, ...]:
        return tuple(sorted(rows, key=lambda row: (-row.py_files, row.scope_dir.as_posix())))


ChatFn = Callable[..., str]


class AgentRanker:
    """BYO LLM ranking when provider/model/key are available; else heuristic."""

    def __init__(
        self,
        llm: LlmConfig,
        *,
        fallback: RecommendationRanker | None = None,
        index_path: Path | None = None,
        chat: ChatFn | None = None,
    ) -> None:
        self._llm = llm
        self._fallback = fallback if fallback is not None else HeuristicRanker()
        self._index_path = index_path
        self._chat = chat if chat is not None else chat_completion
        self.ranking = "heuristic"
        self.note: str | None = None

    def rank(self, rows: Sequence[SpecRecommendation]) -> tuple[SpecRecommendation, ...]:
        baseline = self._fallback.rank(rows)
        if not baseline:
            self.ranking = "heuristic"
            self.note = None
            return ()
        provider = self._llm.provider
        model = self._llm.model
        if provider is None or model is None:
            self.ranking = "heuristic"
            self.note = None
            return baseline
        api_key = resolve_api_key(provider)
        if api_key is None:
            self.ranking = "heuristic"
            self.note = (
                f"llm.provider {provider!r} configured but no API key "
                "in the environment; using heuristic ranking"
            )
            return baseline
        try:
            ordered = self._rank_with_llm(
                baseline,
                provider=provider,
                model=model,
                api_key=api_key,
            )
        except LlmError as err:
            self.ranking = "heuristic"
            self.note = f"agent ranking failed ({err}); using heuristic ranking"
            return baseline
        self.ranking = "agent"
        self.note = f"ranked with {provider} model {model}"
        return ordered

    def _rank_with_llm(
        self,
        rows: Sequence[SpecRecommendation],
        *,
        provider: str,
        model: str,
        api_key: str,
    ) -> tuple[SpecRecommendation, ...]:
        paths = [row.scope_dir.as_posix() for row in rows]
        index_hint = ""
        if self._index_path is not None and self._index_path.is_file():
            snippet = self._index_path.read_text(encoding="utf-8")[:4000]
            index_hint = f"Package index path: {self._index_path.as_posix()}\n{snippet}\n"
        candidates = [
            {
                "scope_dir": row.scope_dir.as_posix(),
                "py_files": row.py_files,
                "rationale": row.rationale,
            }
            for row in rows
        ]
        candidate_json = json.dumps(candidates)
        user = (
            "Rank these Codoc scope directories for adding a nested "
            "codoc.spec.yaml. Prefer substantial packages and useful "
            "nested scopes. Return ONLY a JSON array of the same "
            "scope_dir strings in best-first order. Include every "
            f"path exactly once.\nCandidates:\n{candidate_json}\n"
            f"{index_hint}"
        )
        system = "You rank documentation scope directories. Reply with JSON only."
        text = self._chat(
            provider=provider,
            model=model,
            api_key=api_key,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        order = _parse_scope_order(text, set(paths))
        by_path = {row.scope_dir.as_posix(): row for row in rows}
        return tuple(by_path[path] for path in order)


def run_recommend(
    start: Path | None = None,
    *,
    ranker: RecommendationRanker | None = None,
) -> RecommendResult:
    """List src/ packages (nested included) that lack a nested codoc.spec.yaml."""
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
    packages = _scan_src_packages(root, skip)
    write_package_index(root, packages)
    candidates = tuple(row for row in packages if not row.has_spec)
    recommendations = tuple(
        SpecRecommendation(
            scope_dir=row.scope_dir,
            rationale=_rationale(row),
            py_files=row.py_files,
        )
        for row in candidates
    )
    notes: list[str] = []
    ranking = "heuristic"
    if ranker is None:
        agent = AgentRanker(config.llm, index_path=root / _INDEX_FILE)
        ranked = agent.rank(recommendations)
        ranking = agent.ranking
        if agent.note:
            notes.append(agent.note)
    else:
        ranked = ranker.rank(recommendations)
    return RecommendResult(rows=ranked, ranking=ranking, notes=tuple(notes))


@dataclass(frozen=True, slots=True)
class _PackageRow:
    scope_dir: Path
    py_files: int
    has_spec: bool


def write_package_index(root: Path, packages: Sequence[_PackageRow]) -> Path:
    """Write `.codoc/index/packages.json` for recommend / later tooling."""
    target = root / _INDEX_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "packages": [
            {
                "scope_dir": row.scope_dir.as_posix(),
                "py_files": row.py_files,
                "has_spec": row.has_spec,
            }
            for row in packages
        ]
    }
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    target.write_text(text, encoding="utf-8")
    return target


def _scan_src_packages(root: Path, skip: frozenset[str]) -> tuple[_PackageRow, ...]:
    src = root / _SRC
    if not src.is_dir():
        return ()
    rows: list[_PackageRow] = []
    try:
        for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
            dirnames[:] = [
                name
                for name in dirnames
                if name not in skip
                and not name.startswith(".")
                and not name.endswith((".egg-info", ".dist-info"))
            ]
            abs_dir = Path(dirpath)
            rel = abs_dir.relative_to(root)
            if rel == _SRC:
                continue
            top_level = rel.parent == _SRC
            if top_level:
                if not _looks_like_python_package(abs_dir):
                    continue
            elif "__init__.py" not in filenames:
                continue
            has_spec = _SPEC_FILE in filenames
            py_files = _count_py_files(abs_dir, skip)
            rows.append(_PackageRow(scope_dir=rel, py_files=py_files, has_spec=has_spec))
    except OSError as err:
        raise RecommendError(f"cannot read {src}, {err.strerror}") from err
    rows.sort(key=lambda row: row.scope_dir.as_posix())
    return tuple(rows)


def _rationale(row: _PackageRow) -> str:
    depth = len(row.scope_dir.parts)
    kind = "Nested Python package" if depth > 2 else "Python package under src/"
    plural = "s" if row.py_files != 1 else ""
    return f"{kind} without {_SPEC_FILE} ({row.py_files} .py file{plural})"


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


def _parse_scope_order(text: str, expected: set[str]) -> list[str]:
    match = re.search(r"\[[\s\S]*\]", text)
    if match is None:
        raise LlmError("agent ranking response did not contain a JSON array")
    try:
        loaded = json.loads(match.group(0))
    except json.JSONDecodeError as err:
        raise LlmError("agent ranking response JSON was invalid") from err
    if not isinstance(loaded, list):
        raise LlmError("agent ranking response must be a JSON array")
    order: list[str] = []
    seen: set[str] = set()
    for item in loaded:
        if not isinstance(item, str):
            raise LlmError("agent ranking entries must be strings")
        if item not in expected or item in seen:
            continue
        order.append(item)
        seen.add(item)
    missing = expected - seen
    if missing:
        # Append any omitted paths in sorted order so ranking stays complete.
        order.extend(sorted(missing))
    return order
