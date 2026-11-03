"""Parse and write the `codoc:` YAML frontmatter mirror."""

from dataclasses import dataclass
from pathlib import Path

import yaml


class FrontmatterError(Exception):
    """Frontmatter could not be parsed or written."""


@dataclass(frozen=True, slots=True)
class SourceRef:
    path: str


@dataclass(frozen=True, slots=True)
class CodocFrontmatter:
    id: str
    type: str
    sources: tuple[SourceRef, ...] = ()


@dataclass(frozen=True, slots=True)
class SplitDoc:
    frontmatter: CodocFrontmatter | None
    body: str
    mapping: dict | None = None


def split_frontmatter(text: str) -> SplitDoc:
    """Split a Markdown file into optional codoc frontmatter and body."""
    if not text.startswith("---"):
        return SplitDoc(frontmatter=None, body=text, mapping=None)
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return SplitDoc(frontmatter=None, body=text, mapping=None)
    end = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = index
            break
    if end is None:
        return SplitDoc(frontmatter=None, body=text, mapping=None)
    raw = "".join(lines[1:end])
    body = "".join(lines[end + 1 :])
    try:
        loaded = yaml.safe_load(raw) or {}
    except yaml.YAMLError as err:
        raise FrontmatterError(f"invalid frontmatter YAML: {err}") from err
    if not isinstance(loaded, dict):
        raise FrontmatterError("frontmatter must be a mapping")
    block = loaded.get("codoc")
    if not isinstance(block, dict):
        return SplitDoc(frontmatter=None, body=body, mapping=loaded)
    page_id = block.get("id")
    page_type = block.get("type")
    if not isinstance(page_id, str) or not isinstance(page_type, str):
        return SplitDoc(frontmatter=None, body=body, mapping=loaded)
    sources: list[SourceRef] = []
    raw_sources = block.get("sources") or []
    if isinstance(raw_sources, list):
        for entry in raw_sources:
            if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                sources.append(SourceRef(entry["path"]))
    return SplitDoc(
        frontmatter=CodocFrontmatter(page_id, page_type, tuple(sources)),
        body=body,
        mapping=loaded,
    )


def render_frontmatter(meta: CodocFrontmatter, *, existing: dict | None = None) -> str:
    """Return a `---` fenced YAML block, keeping non-codoc keys from existing."""
    payload: dict = dict(existing) if existing else {}
    block: dict = {
        "id": meta.id,
        "type": meta.type,
    }
    if meta.sources:
        block["sources"] = [{"path": source.path} for source in meta.sources]
    payload["codoc"] = block
    dumped = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True).rstrip()
    return f"---\n{dumped}\n---\n"


def write_doc(
    path: Path,
    meta: CodocFrontmatter,
    body: str,
    *,
    existing: dict | None = None,
) -> None:
    """Write frontmatter + body to path, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body_text = body.lstrip("\n")
    if body_text and not body_text.endswith("\n"):
        body_text += "\n"
    content = render_frontmatter(meta, existing=existing)
    if body_text:
        content += "\n" + body_text
    path.write_text(content, encoding="utf-8")
