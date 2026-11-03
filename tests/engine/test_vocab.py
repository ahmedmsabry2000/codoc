from pathlib import Path

from codoc.engine.codegen import ensure_generated
from codoc.engine.vocab import (
    LEARNED_REL,
    grow_learned,
    harvest_docs,
    merge_accept_terms,
    read_learned,
)
from tests.support.git import git_repository


def _write_project(repo: Path, *, terms: list[str] | None = None) -> None:
    lines = [
        "engine:",
        "  name: zensical",
        "  docs_dir: docs",
        "  site_dir: site",
        "vale:",
        "  enabled: true",
    ]
    if terms is not None:
        lines.append("terms:")
        lines.extend(f"  - {term}" for term in terms)
    lines.append("")
    (repo / "codoc.yaml").write_text("\n".join(lines), encoding="utf-8")


class VocabHarvestTests:
    def test_harvest_finds_camel_snake_quoted_and_repeated_proper(self, tmp_dir: Path) -> None:
        docs = tmp_dir / "docs"
        docs.mkdir()
        (docs / "guide.md").write_text(
            "\n".join(
                [
                    "# Guide",
                    "",
                    'Install FooBar with `snake_case` and "AcmeKit".',
                    "Zensical Zensical is mentioned twice.",
                    "The The word The is common.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        harvested = set(harvest_docs(docs))
        assert "FooBar" in harvested
        assert "snake_case" in harvested
        assert "AcmeKit" in harvested
        assert "Zensical" in harvested
        assert "The" not in harvested

    def test_grow_learned_and_merge_into_accept(self) -> None:
        with git_repository() as repo:
            _write_project(repo, terms=["Codoc", "SeedTerm"])
            docs = repo / "docs"
            docs.mkdir()
            (docs / "index.md").write_text(
                "Codoc uses FooBar and `parse_spec`.\nFooBar again.\n",
                encoding="utf-8",
            )
            first = ensure_generated(repo)
            assert first.learned_added
            learned = read_learned(repo)
            assert "FooBar" in learned
            assert "parse_spec" in learned
            assert "Codoc" not in learned
            assert "SeedTerm" not in learned
            accept = (repo / first.vocab_accept).read_text(encoding="utf-8")
            assert accept.splitlines()[0:2] == ["Codoc", "SeedTerm"]
            assert "FooBar" in accept
            assert "parse_spec" in accept
            yaml_text = (repo / "codoc.yaml").read_text(encoding="utf-8")
            assert "FooBar" not in yaml_text
            assert (repo / LEARNED_REL).is_file()

            second = ensure_generated(repo)
            assert second.learned_added == ()
            assert read_learned(repo) == learned
            assert (repo / second.vocab_accept).read_text(encoding="utf-8") == accept

    def test_no_learn_skips_harvest_but_keeps_seed(self) -> None:
        with git_repository() as repo:
            _write_project(repo, terms=["Codoc"])
            docs = repo / "docs"
            docs.mkdir()
            (docs / "index.md").write_text(
                "Mentions BrandNewTool BrandNewTool.\n",
                encoding="utf-8",
            )
            result = ensure_generated(repo, learn=False)
            assert result.learned_added == ()
            assert not (repo / LEARNED_REL).exists()
            accept = (repo / result.vocab_accept).read_text(encoding="utf-8")
            assert accept == "Codoc\n"

    def test_merge_accept_keeps_seed_order(self) -> None:
        merged = merge_accept_terms(("Codoc", "Zensical"), ("Alpha", "Codoc", "Beta"))
        assert merged == ("Codoc", "Zensical", "Alpha", "Beta")

    def test_grow_learned_idempotent_for_same_docs(self, tmp_dir: Path) -> None:
        docs = tmp_dir / "docs"
        docs.mkdir()
        (docs / "a.md").write_text("CamelTerm and snake_token.\n", encoding="utf-8")
        first = grow_learned(tmp_dir, Path("docs"), seed=("Seed",))
        second = grow_learned(tmp_dir, Path("docs"), seed=("Seed",))
        assert first.added
        assert second.added == ()
        assert second.learned == first.learned
