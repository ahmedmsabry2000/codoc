"""Parse and write the `codoc:` YAML frontmatter mirror."""

from dataclasses import dataclass
from pathlib import Path

import yaml


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
    raw_frontmatter: str | None = None


def split_frontmatter(text: str) -> SplitDoc:
    """Split a Markdown file into optional codoc frontmatter and body."""
    if not text.startswith("---"):
        return SplitDoc(frontmatter=None, body=text, raw_frontmatter=None)
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return SplitDoc(frontmatter=None, body=text, raw_frontmatter=None)
    end = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = index
            break
    if end is None:
        return SplitDoc(frontmatter=None, body=text, raw_frontmatter=None)
    raw = "".join(lines[1:end])
    body = "".join(lines[end + 1 :])
    try:
        loaded = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        return SplitDoc(frontmatter=None, body=text, raw_frontmatter=None)
    if not isinstance(loaded, dict):
        return SplitDoc(frontmatter=None, body=text, raw_frontmatter=None)
    block = loaded.get("codoc")
    if not isinstance(block, dict):
        return SplitDoc(frontmatter=None, body=body, raw_frontmatter=raw)
    page_id = block.get("id")
    page_type = block.get("type")
    if not isinstance(page_id, str) or not isinstance(page_type, str):
        return SplitDoc(frontmatter=None, body=body, raw_frontmatter=raw)
    sources: list[SourceRef] = []
    raw_sources = block.get("sources") or []
    if isinstance(raw_sources, list):
        for entry in raw_sources:
            if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                sources.append(SourceRef(entry["path"]))
    return SplitDoc(
        frontmatter=CodocFrontmatter(page_id, page_type, tuple(sources)),
        body=body,
        raw_frontmatter=raw,
    )


def render_frontmatter(meta: CodocFrontmatter) -> str:
    """Return a `---` fenced YAML block for the codoc mirror."""
    payload: dict = {
        "codoc": {
            "id": meta.id,
            "type": meta.type,
        }
    }
    if meta.sources:
        payload["codoc"]["sources"] = [{"path": source.path} for source in meta.sources]
    dumped = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True).rstrip()
    return f"---\n{dumped}\n---\n"


def write_doc(path: Path, meta: CodocFrontmatter, body: str) -> None:
    """Write frontmatter + body to path, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body_text = body.lstrip("\n")
    if body_text and not body_text.endswith("\n"):
        body_text += "\n"
    content = render_frontmatter(meta)
    if body_text:
        content += "\n" + body_text
    path.write_text(content, encoding="utf-8")
