"""Discover specs and ensure every declared page under docs/."""

from dataclasses import dataclass
from pathlib import Path

from codoc.config import ConfigError, LlmConfig, load_project_config
from codoc.discover import DiscoverError, SpecUnit, discover, git_root
from codoc.generate.draft import draft_stub_body
from codoc.generate.ensure import PageOutcome, ensure_page
from codoc.generate.frontmatter import FrontmatterError
from codoc.generate.scripts import ScriptError
from codoc.model.registry import build_page_registry
from codoc.model.spec import CoverageBlock, Page, SpecDocument, SpecError, load_spec


class GenerateError(Exception):
    """Generate could not write docs."""


@dataclass(frozen=True, slots=True)
class GenerateResult:
    root: Path
    pages: tuple[PageOutcome, ...]
    notes: tuple[str, ...] = ()


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
        notes: list[str] = []
        for unit, doc in loaded:
            sources_by_page = _sources_by_page(root, unit.scope_dir, doc)
            for page in doc.pages():
                draft, note = _maybe_draft(root, page, config.llm)
                if note and note not in notes:
                    notes.append(note)
                outcomes.append(
                    ensure_page(
                        root=root,
                        page=page,
                        scope_dir=unit.scope_dir,
                        registry=registry,
                        source_paths=sources_by_page.get(page.id, ()),
                        scripts_dir=config.paths.scripts_dir,
                        draft_body=draft,
                    )
                )
    except (DiscoverError, ConfigError, SpecError, ScriptError, FrontmatterError) as err:
        raise GenerateError(str(err)) from err
    return GenerateResult(root=root, pages=tuple(outcomes), notes=tuple(notes))


def _maybe_draft(
    root: Path,
    page: Page,
    llm: LlmConfig,
) -> tuple[str | None, str | None]:
    """Draft only when creating a new manual/hybrid page."""
    if page.type not in {"manual", "hybrid"}:
        return None, None
    if (root / page.path).is_file():
        return None, None
    return draft_stub_body(page, llm)


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
