"""Discover specs and ensure every declared page under docs/."""

from dataclasses import dataclass
from pathlib import Path

from codoc.config import ConfigError, load_project_config
from codoc.discover import DiscoverError, SpecUnit, discover, git_root
from codoc.generate.ensure import PageOutcome, ensure_page
from codoc.generate.frontmatter import FrontmatterError
from codoc.generate.scripts import ScriptError
from codoc.model.registry import build_page_registry
from codoc.model.spec import CoverageBlock, SpecDocument, SpecError, load_spec


class GenerateError(Exception):
    """Generate could not write docs."""


@dataclass(frozen=True, slots=True)
class GenerateResult:
    root: Path
    pages: tuple[PageOutcome, ...]


def run_generate(start: Path | None = None) -> GenerateResult:
    """Discover every spec, merge the page registry, and ensure each page."""
    if start is None:
        start = Path.cwd()
    try:
        root = git_root(start)
        config = load_project_config(root / "codoc.yaml")
        units = discover(root)
        loaded: list[tuple[SpecUnit, SpecDocument]] = []
        for unit in units:
            loaded.append((unit, load_spec(root / unit.spec_path)))
        registry = build_page_registry(tuple((root / unit.spec_path, doc) for unit, doc in loaded))
        outcomes: list[PageOutcome] = []
        for unit, doc in loaded:
            sources_by_page = _sources_by_page(root, unit.scope_dir, doc)
            for page in doc.pages():
                outcomes.append(
                    ensure_page(
                        root=root,
                        page=page,
                        scope_dir=unit.scope_dir,
                        registry=registry,
                        source_paths=sources_by_page.get(page.id, ()),
                        scripts_dir=config.paths.scripts_dir,
                    )
                )
    except (DiscoverError, ConfigError, SpecError, ScriptError, FrontmatterError) as err:
        raise GenerateError(str(err)) from err
    return GenerateResult(root=root, pages=tuple(outcomes))


def _sources_by_page(
    root: Path,
    scope_dir: Path,
    doc: SpecDocument,
) -> dict[str, tuple[str, ...]]:
    """Map page id → repo-relative source paths from owning coverage blocks."""
    mapping: dict[str, tuple[str, ...]] = {}
    for block in doc.coverage.source + doc.coverage.features:
        paths = _expand_coverage_paths(root, scope_dir, block)
        for page in block.docs:
            mapping[page.id] = paths
    return mapping


def _expand_coverage_paths(
    root: Path,
    scope_dir: Path,
    block: CoverageBlock,
) -> tuple[str, ...]:
    """Expand coverage globs under the scope dir into repo-relative paths."""
    base = root / scope_dir
    found: list[str] = []
    seen: set[str] = set()
    for pattern in block.paths:
        if any(char in pattern for char in "*?["):
            matches = sorted(base.glob(pattern))
            for match in matches:
                if match.is_file():
                    rel = match.relative_to(root).as_posix()
                    if rel not in seen:
                        seen.add(rel)
                        found.append(rel)
        else:
            candidate = base / pattern
            if candidate.is_file():
                rel = candidate.relative_to(root).as_posix()
                if rel not in seen:
                    seen.add(rel)
                    found.append(rel)
    return tuple(found)
