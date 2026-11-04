"""RAG index chunking and retrieval."""

from pathlib import Path

from codoc.rag.index import RagChunk, attach_embeddings, build_rag_index, retrieve, write_rag_index
from tests.support.fs import write_text


class RagIndexTests:
    def test_chunks_by_heading_and_retrieves(self, tmp_dir: Path) -> None:
        path = tmp_dir / "docs" / "a.md"
        body = "\n".join(
            (
                "---",
                "codoc:",
                "  id: a",
                "  type: manual",
                "---",
                "",
                "Lead sentence before headings.",
                "",
                "# Hello",
                "",
                "alpha beta",
                "",
                "# Other",
                "",
                "gamma",
                "",
            )
        )
        write_text(path, body)
        chunks = build_rag_index([("a", path, "docs/a.md")])
        assert len(chunks) == 3
        assert chunks[0].heading == ""
        assert "Lead sentence" in chunks[0].text
        assert chunks[1].heading == "Hello"
        hits = retrieve(chunks, "alpha token")
        assert hits and hits[0].heading == "Hello"
        out = write_rag_index(tmp_dir, chunks)
        assert out.is_file()

    def test_retrieve_matches_whole_tokens(self) -> None:
        # "api" is a substring of "Capital". Path order would prefer the Capital
        # chunk if retrieve still scored substrings, so this fails that regression.
        chunks = (
            RagChunk(page_id="cap", path="docs/a.md", heading="Capital", text="Capital city"),
            RagChunk(page_id="api", path="docs/z.md", heading="API", text="api surface"),
        )
        hits = retrieve(chunks, "api")
        assert [chunk.page_id for chunk in hits] == ["api"]

    def test_retrieve_prefers_embeddings_when_present(self) -> None:
        chunks = attach_embeddings(
            (
                RagChunk(page_id="a", path="docs/a.md", heading="A", text="alpha"),
                RagChunk(page_id="b", path="docs/b.md", heading="B", text="beta"),
            ),
            [[1.0, 0.0], [0.0, 1.0]],
        )
        hits = retrieve(chunks, "token that matches neither", query_embedding=[0.0, 1.0])
        assert [chunk.page_id for chunk in hits] == ["b"]

    def test_retrieve_falls_back_without_query_embedding(self) -> None:
        chunks = attach_embeddings(
            (
                RagChunk(page_id="a", path="docs/a.md", heading="A", text="uniquealpha"),
                RagChunk(page_id="b", path="docs/b.md", heading="B", text="beta"),
            ),
            [[1.0, 0.0], [0.0, 1.0]],
        )
        hits = retrieve(chunks, "uniquealpha")
        assert hits[0].page_id == "a"
