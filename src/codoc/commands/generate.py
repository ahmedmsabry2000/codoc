"""Discover specs and ensure every declared page under docs/."""

from dataclasses import dataclass
from pathlib import Path

from codoc.config import ConfigError, LlmConfig, load_project_config
from codoc.coverage import expand_coverage_paths
from codoc.discover import DiscoverError, SpecUnit, child_scopes, discover, git_root
from codoc.generate.draft import draft_stub_body, maybe_rewrite_stub
from codoc.generate.ensure import PageOutcome, ensure_page
from codoc.generate.fingerprint import (
    CachedPage,
    cache_is_warm,
    cache_path,
    draft_skip_blocks_cache,
    fingerprint_inputs,
    read_cache,
    write_cache,
)
from codoc.generate.frontmatter import FrontmatterError
from codoc.generate.scripts import ScriptError
from codoc.model.registry import PageRegistry, build_page_registry
from codoc.model.spec import CoverageBlock, Page, SpecDocument, SpecError, load_spec


class GenerateError(Exception):
    """Generate could not write docs."""


@dataclass(frozen=True, slots=True)
class GenerateResult:
    root: Path
    pages: tuple[PageOutcome, ...]
    notes: tuple[str, ...] = ()


def run_generate(
    start: Path | None = None,
    *,
    scope: str | None = None,
    no_cache: bool = False,
) -> GenerateResult:
    """Discover every spec, merge the page registry, and ensure each page."""
    if start is None:
        start = Path.cwd()
    try:
        root = git_root(start)
        config = load_project_config(root / "codoc.yaml")
        all_units = discover(root)
        units = _filter_units(all_units, scope)
        if scope is not None and not units:
            raise GenerateError(f"no spec matched scope {scope!r}")
        all_docs = [(unit, load_spec(root / unit.spec_path)) for unit in all_units]
        docs_by_scope = {unit.scope_dir: doc for unit, doc in all_docs}
        registry = build_page_registry(
            tuple((root / unit.spec_path, doc) for unit, doc in all_docs)
        )
        registry_entries = _registry_entries(registry)
        excludes = child_scopes(all_units)
        outcomes: list[PageOutcome] = []
        notes: list[str] = []
        for unit in units:
            doc = docs_by_scope[unit.scope_dir]
            sources_by_page = _sources_by_page(
                root,
                unit.scope_dir,
                doc,
                exclude_scopes=excludes.get(unit.scope_dir, ()),
            )
            all_sources = tuple(
                sorted({path for paths in sources_by_page.values() for path in paths})
            )
            digest = fingerprint_inputs(
                root,
                spec_path=unit.spec_path,
                doc=doc,
                source_paths=all_sources,
                scripts_dir=config.paths.scripts_dir,
                registry_entries=registry_entries,
                llm_provider=config.llm.provider,
                llm_model=config.llm.model,
                rewrite_stubs=config.llm.rewrite_stubs,
            )
            entry_path = cache_path(root, unit.scope_dir)
            cached = None if no_cache else read_cache(entry_path)
            if not no_cache and cache_is_warm(root, fingerprint=digest, cached=cached):
                assert cached is not None
                for page in cached[1]:
                    outcomes.append(
                        PageOutcome(page_id=page.page_id, path=Path(page.path), action="cached")
                    )
                note = f"cache hit for scope {unit.scope_dir.as_posix()}"
                if note not in notes:
                    notes.append(note)
                continue
            unit_pages: list[PageOutcome] = []
            unit_notes: list[str] = []
            for page in doc.pages():
                draft, note = _maybe_draft(root, page, config.llm, doc=doc)
                if note:
                    if note not in notes:
                        notes.append(note)
                    unit_notes.append(note)
                outcome = ensure_page(
                    root=root,
                    page=page,
                    scope_dir=unit.scope_dir,
                    registry=registry,
                    source_paths=sources_by_page.get(page.id, ()),
                    scripts_dir=config.paths.scripts_dir,
                    draft_body=draft,
                )
                unit_pages.append(outcome)
                outcomes.append(outcome)
            if no_cache:
                notes.append(f"cache bypassed for scope {unit.scope_dir.as_posix()}")
            elif draft_skip_blocks_cache(unit_notes):
                notes.append(
                    f"cache not written for scope {unit.scope_dir.as_posix()} (draft skipped)"
                )
            else:
                # Recompute digest after writes so page bodies match the warm entry.
                digest = fingerprint_inputs(
                    root,
                    spec_path=unit.spec_path,
                    doc=doc,
                    source_paths=all_sources,
                    scripts_dir=config.paths.scripts_dir,
                    registry_entries=registry_entries,
                    llm_provider=config.llm.provider,
                    llm_model=config.llm.model,
                    rewrite_stubs=config.llm.rewrite_stubs,
                )
                write_cache(
                    entry_path,
                    fingerprint=digest,
                    pages=tuple(
                        CachedPage(
                            page_id=item.page_id,
                            path=item.path.as_posix(),
                            action=item.action,
                        )
                        for item in unit_pages
                    ),
                )
    except (DiscoverError, ConfigError, SpecError, ScriptError, FrontmatterError) as err:
        raise GenerateError(str(err)) from err
    except ValueError as err:
        raise GenerateError(str(err)) from err
    return GenerateResult(root=root, pages=tuple(outcomes), notes=tuple(notes))


def _registry_entries(registry: PageRegistry) -> tuple[tuple[str, str], ...]:
    return tuple((entry.id, entry.path) for entry in registry.entries)


def _filter_units(units: tuple[SpecUnit, ...], scope: str | None) -> tuple[SpecUnit, ...]:
    if scope is None:
        return units
    needle = Path(scope.rstrip("/"))
    if needle == Path("."):
        needle = Path(".")
    matched = [
        unit
        for unit in units
        if unit.scope_dir == needle
        or unit.spec_path == needle
        or unit.spec_path.as_posix() == scope.rstrip("/")
        or unit.scope_dir.as_posix() == scope.rstrip("/")
        or (needle == Path(".") and unit.scope_dir == Path("."))
    ]
    return tuple(matched)


def _maybe_draft(
    root: Path,
    page: Page,
    llm: LlmConfig,
    *,
    doc: SpecDocument,
) -> tuple[str | None, str | None]:
    """Draft new manual/hybrid stubs, or rewrite eligible manual stubs when configured."""
    if page.type not in {"manual", "hybrid"}:
        return None, None
    if (root / page.path).is_file():
        return maybe_rewrite_stub(root, page, llm, doc=doc)
    return draft_stub_body(page, llm, doc=doc)


def _sources_by_page(
    root: Path,
    scope_dir: Path,
    doc: SpecDocument,
    *,
    exclude_scopes: tuple[Path, ...] = (),
) -> dict[str, tuple[str, ...]]:
    """Map page id → repo-relative source paths from owning coverage blocks."""
    mapping: dict[str, tuple[str, ...]] = {}
    for block in doc.coverage.source + doc.coverage.features:
        paths = _expand_block(root, scope_dir, block, exclude_scopes=exclude_scopes)
        for page in block.docs:
            mapping[page.id] = paths
    return mapping


def _expand_block(
    root: Path,
    scope_dir: Path,
    block: CoverageBlock,
    *,
    exclude_scopes: tuple[Path, ...] = (),
) -> tuple[str, ...]:
    return expand_coverage_paths(
        root,
        scope_dir,
        block.paths,
        exclude_scopes=exclude_scopes,
    )
