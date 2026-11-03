"""Resolve page links and canonical targets via the merged registry."""

from pathlib import PurePosixPath

from codoc.model.registry import PageRegistry
from codoc.model.spec import Page


def relative_href(from_path: str, to_path: str) -> str:
    """Return a relative Markdown href from one docs path to another."""
    start = PurePosixPath(from_path).parent
    target = PurePosixPath(to_path)
    start_parts = start.parts
    target_parts = target.parts
    common = 0
    for left, right in zip(start_parts, target_parts, strict=False):
        if left != right:
            break
        common += 1
    ups = [".."] * (len(start_parts) - common)
    downs = list(target_parts[common:])
    if not ups and not downs:
        return target.name
    return PurePosixPath(*ups, *downs).as_posix()


def link_blocks(page: Page, registry: PageRegistry) -> str:
    """Return Markdown for Original page and See also sections, if any."""
    chunks: list[str] = []
    if page.canonical and page.canonical in registry:
        target = registry.lookup(page.canonical)
        href = relative_href(page.path, target.path)
        chunks.append("## Original page\n")
        chunks.append(f"- [{_label(page.canonical, None)}]({href})\n")
    if page.links:
        lines = ["## See also\n"]
        for link in page.links:
            if link.id not in registry:
                continue
            target = registry.lookup(link.id)
            href = relative_href(page.path, target.path)
            lines.append(f"- [{_label(link.id, link.label)}]({href})\n")
        if len(lines) > 1:
            chunks.extend(lines)
    if not chunks:
        return ""
    return "\n".join(chunks).rstrip() + "\n"


def sources_block(from_path: str, sources: tuple[str, ...]) -> str:
    """Return a Sources footer with hrefs relative to the docs page."""
    if not sources:
        return ""
    lines = ["## Sources\n"]
    for path in sources:
        name = PurePosixPath(path).name
        href = relative_href(from_path, path)
        lines.append(f"- [`{name}`]({href})\n")
    return "\n".join(lines)


def _label(page_id: str, label: str | None) -> str:
    return label if label else page_id
