"""RAG index chunking and retrieval."""

from pathlib import Path

from codoc.rag.index import RagChunk, build_rag_index, retrieve, write_rag_index
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
        chunks = (
            RagChunk(page_id="cap", path="docs/cap.md", heading="Capital", text="Capital city"),
            RagChunk(page_id="api", path="docs/api.md", heading="API", text="api surface"),
        )
        hits = retrieve(chunks, "api")
        assert hits and hits[0].page_id == "api"
