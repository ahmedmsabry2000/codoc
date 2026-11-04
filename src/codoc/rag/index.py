"""Build a small JSON RAG index from docs Markdown."""

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from codoc.llm.embed import cosine_similarity

_HEADING = re.compile(r"(?m)^(#{1,6})\s+(.+)$")


@dataclass(frozen=True, slots=True)
class RagChunk:
    page_id: str
    path: str
    heading: str
    text: str
    embedding: tuple[float, ...] | None = None


def build_rag_index(pages: list[tuple[str, Path, str]]) -> tuple[RagChunk, ...]:
    """
    Chunk docs for retrieval.

    pages is a list of (page_id, absolute_path, repo-relative path).
    Missing files are skipped.
    """
    chunks: list[RagChunk] = []
    for page_id, abs_path, rel in pages:
        if not abs_path.is_file():
            continue
        text = abs_path.read_text(encoding="utf-8")
        body = _strip_frontmatter(text)
        chunks.extend(_chunk_page(page_id, rel, body))
    return tuple(chunks)


def attach_embeddings(
    chunks: tuple[RagChunk, ...],
    vectors: list[list[float]],
) -> tuple[RagChunk, ...]:
    """Return chunks with embedding vectors attached (same order/length)."""
    if len(vectors) != len(chunks):
        raise ValueError("embedding count must match chunk count")
    return tuple(
        RagChunk(
            page_id=chunk.page_id,
            path=chunk.path,
            heading=chunk.heading,
            text=chunk.text,
            embedding=tuple(vector),
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    )


def write_rag_index(root: Path, chunks: tuple[RagChunk, ...]) -> Path:
    """Write `.codoc/index/rag.json` and return its path."""
    out_dir = root / ".codoc" / "index"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "rag.json"
    payload = {
        "version": 2,
        "chunks": [asdict(chunk) for chunk in chunks],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def retrieve(
    chunks: tuple[RagChunk, ...],
    query: str,
    *,
    limit: int = 5,
    query_embedding: list[float] | None = None,
) -> tuple[RagChunk, ...]:
    """
    Return the best-matching chunks for query.

    When query_embedding is set and chunks carry embeddings, rank by cosine
    similarity. Otherwise fall back to case-insensitive token overlap.
    """
    if query_embedding is not None and any(chunk.embedding for chunk in chunks):
        scored_emb: list[tuple[float, RagChunk]] = []
        for chunk in chunks:
            if not chunk.embedding:
                continue
            score = cosine_similarity(query_embedding, list(chunk.embedding))
            if score > 0:
                scored_emb.append((score, chunk))
        scored_emb.sort(key=lambda item: (-item[0], item[1].path, item[1].heading))
        if scored_emb:
            return tuple(chunk for _score, chunk in scored_emb[:limit])

    tokens = {token.lower() for token in re.findall(r"[a-zA-Z0-9_]+", query) if len(token) > 2}
    if not tokens:
        return chunks[:limit]

    scored: list[tuple[int, RagChunk]] = []
    for chunk in chunks:
        hay_tokens = {
            token.lower()
            for token in re.findall(r"[a-zA-Z0-9_]+", f"{chunk.heading}\n{chunk.text}")
        }
        score = sum(1 for token in tokens if token in hay_tokens)
        if score:
            scored.append((score, chunk))
    scored.sort(key=lambda item: (-item[0], item[1].path, item[1].heading))
    return tuple(chunk for _score, chunk in scored[:limit])


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "".join(lines[index + 1 :])
    return text


def _chunk_page(page_id: str, rel: str, body: str) -> list[RagChunk]:
    matches = list(_HEADING.finditer(body))
    if not matches:
        stripped = body.strip()
        if not stripped:
            return []
        return [RagChunk(page_id=page_id, path=rel, heading="", text=stripped[:2000])]
    chunks: list[RagChunk] = []
    preamble = body[: matches[0].start()].strip()
    if preamble:
        chunks.append(RagChunk(page_id=page_id, path=rel, heading="", text=preamble[:2000]))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        section = body[start:end].strip()
        heading = match.group(2).strip()
        text = f"{heading}\n{section}".strip()[:2000]
        chunks.append(RagChunk(page_id=page_id, path=rel, heading=heading, text=text))
    return chunks
