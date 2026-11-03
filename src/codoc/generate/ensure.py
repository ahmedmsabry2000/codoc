"""Type-aware ensureDocs for one page."""

import re
from dataclasses import dataclass
from pathlib import Path

from codoc.generate.frontmatter import CodocFrontmatter, SourceRef, split_frontmatter, write_doc
from codoc.generate.links import link_blocks, sources_block
from codoc.generate.scripts import ScriptError, run_script
from codoc.model.registry import PageRegistry
from codoc.model.spec import Page

_PLACEHOLDER_PAIR = re.compile(
    r'(<!--\s*codoc:placeholder\s+id="([^"]+)"\s*-->)(.*?)(<!--\s*/codoc:placeholder\s*-->)',
    re.IGNORECASE | re.DOTALL,
)
_PLACEHOLDER_CLOSE = "<!-- /codoc:placeholder -->"


@dataclass(frozen=True, slots=True)
class PageOutcome:
    page_id: str
    path: Path
    action: str


def ensure_page(
    *,
    root: Path,
    page: Page,
    scope_dir: Path,
    registry: PageRegistry,
    source_paths: tuple[str, ...] = (),
) -> PageOutcome:
    """
    Ensure one page on disk according to its type.

    manual: create stub if missing; sync frontmatter only when present.
    hybrid: sync frontmatter; inject placeholder bodies from scripts.
    auto-generated: rewrite the whole page from script (or a stub).
    """
    abs_path = root / page.path
    meta = CodocFrontmatter(
        id=page.id,
        type=page.type,
        sources=tuple(SourceRef(path) for path in source_paths),
    )
    if page.type == "manual":
        return _ensure_manual(abs_path, page, meta)
    if page.type == "hybrid":
        return _ensure_hybrid(root, abs_path, page, scope_dir, registry, meta, source_paths)
    if page.type == "auto-generated":
        return _ensure_auto(root, abs_path, page, scope_dir, registry, meta, source_paths)
    raise ScriptError(f"unsupported page type {page.type!r}")


def _ensure_manual(path: Path, page: Page, meta: CodocFrontmatter) -> PageOutcome:
    if not path.is_file():
        write_doc(path, meta, f"# {page.id}\n")
        return PageOutcome(page.id, Path(page.path), "created")
    text = path.read_text(encoding="utf-8")
    split = split_frontmatter(text)
    write_doc(path, meta, split.body)
    return PageOutcome(page.id, Path(page.path), "frontmatter")


def _ensure_hybrid(
    root: Path,
    path: Path,
    page: Page,
    scope_dir: Path,
    registry: PageRegistry,
    meta: CodocFrontmatter,
    source_paths: tuple[str, ...],
) -> PageOutcome:
    existed = path.is_file()
    if existed:
        body = split_frontmatter(path.read_text(encoding="utf-8")).body
    else:
        body = _hybrid_stub(page)
    body = _inject_placeholders(root, body, page, scope_dir)
    body = _ensure_trailing_sections(body, page, registry, source_paths)
    write_doc(path, meta, body)
    return PageOutcome(page.id, Path(page.path), "injected" if existed else "created")


def _ensure_auto(
    root: Path,
    path: Path,
    page: Page,
    scope_dir: Path,
    registry: PageRegistry,
    meta: CodocFrontmatter,
    source_paths: tuple[str, ...],
) -> PageOutcome:
    if page.script:
        body = run_script(
            root,
            page.script,
            page_id=page.id,
            scope_dir=scope_dir,
        )
    else:
        body = f"# {page.id}\n\nAuto-generated page with no script configured.\n"
    body = body.rstrip() + "\n"
    extras = "\n".join(
        block for block in (sources_block(source_paths), link_blocks(page, registry)) if block
    )
    if extras:
        body = body.rstrip() + "\n\n" + extras
    write_doc(path, meta, body)
    return PageOutcome(page.id, Path(page.path), "generated")


def _hybrid_stub(page: Page) -> str:
    parts = [f"# {page.id}\n"]
    for placeholder in page.placeholders:
        parts.append(f'\n<!-- codoc:placeholder id="{placeholder.id}" -->\n')
        parts.append("\n")
        parts.append(f"{_PLACEHOLDER_CLOSE}\n")
    return "".join(parts)


def _inject_placeholders(
    root: Path,
    body: str,
    page: Page,
    scope_dir: Path,
) -> str:
    scripts_by_id = {item.id: item.script for item in page.placeholders}
    if not scripts_by_id:
        return body

    def replace_pair(match: re.Match[str]) -> str:
        open_tag, placeholder_id, _old, close_tag = match.groups()
        script = scripts_by_id.get(placeholder_id)
        if script is None:
            return match.group(0)
        fragment = run_script(
            root,
            script,
            page_id=page.id,
            scope_dir=scope_dir,
            placeholder_id=placeholder_id,
        ).rstrip("\n")
        return f"{open_tag}\n{fragment}\n{close_tag}"

    return _PLACEHOLDER_PAIR.sub(replace_pair, body)


def _ensure_trailing_sections(
    body: str,
    page: Page,
    registry: PageRegistry,
    source_paths: tuple[str, ...],
) -> str:
    extras: list[str] = []
    if "## Sources" not in body:
        block = sources_block(source_paths)
        if block:
            extras.append(block.rstrip())
    if "## See also" not in body and "## Original page" not in body:
        block = link_blocks(page, registry)
        if block:
            extras.append(block.rstrip())
    if not extras:
        return body
    return body.rstrip() + "\n\n" + "\n\n".join(extras) + "\n"
