"""Behavior tests for codoc generate / ensureDocs."""

from pathlib import Path

import pytest

from codoc.commands.generate import GenerateError, run_generate
from codoc.generate.frontmatter import split_frontmatter
from codoc.generate.links import relative_href
from tests.support.cli import run_cli
from tests.support.fs import write_text


def _project_yaml() -> str:
    return "engine:\n  name: zensical\n"


def _write_script(repo: Path, name: str, body: str) -> str:
    rel = Path(".codoc") / "scripts" / name
    write_text(repo / rel, body)
    return rel.as_posix()


class GenerateTests:
    def test_manual_preserves_body_and_syncs_frontmatter(self, git_repo: Path) -> None:
        write_text(git_repo / "codoc.yaml", _project_yaml())
        write_text(
            git_repo / "src" / "demo" / "codoc.spec.yaml",
            "\n".join(
                (
                    "docs:",
                    "  - id: guide",
                    "    type: manual",
                    "    path: docs/guide.md",
                )
            ),
        )
        write_text(
            git_repo / "docs" / "guide.md",
            "---\ncodoc:\n  id: stale\n  type: manual\n---\n\n# Keep me\n\nBody stays.\n",
        )
        result = run_generate(git_repo)
        assert len(result.pages) == 1
        assert result.pages[0].action == "frontmatter"
        text = (git_repo / "docs" / "guide.md").read_text(encoding="utf-8")
        split = split_frontmatter(text)
        assert split.frontmatter is not None
        assert split.frontmatter.id == "guide"
        assert "# Keep me" in split.body
        assert "Body stays." in split.body

    def test_auto_runs_script_and_emits_links(self, git_repo: Path) -> None:
        script = _write_script(
            git_repo,
            "gen_ref.py",
            'print("# API")\nprint()\nprint("Generated body.")\n',
        )
        write_text(git_repo / "codoc.yaml", _project_yaml())
        write_text(git_repo / "src" / "demo" / "__init__.py", "")
        write_text(
            git_repo / "src" / "demo" / "codoc.spec.yaml",
            "\n".join(
                (
                    "docs:",
                    "  - id: guide",
                    "    type: manual",
                    "    path: docs/guide.md",
                    "coverage:",
                    "  source:",
                    "    - id: api",
                    "      type: auto-generated",
                    "      paths:",
                    '        - "*.py"',
                    "      docs:",
                    "        - id: api.ref",
                    "          path: docs/api.md",
                    f"          script: {script}",
                    "          canonical: guide",
                    "          links:",
                    "            - id: guide",
                    "              label: Guide",
                )
            ),
        )
        write_text(git_repo / "docs" / "guide.md", "# Guide\n")
        result = run_generate(git_repo)
        actions = {page.page_id: page.action for page in result.pages}
        assert actions["guide"] == "frontmatter"
        assert actions["api.ref"] == "generated"
        text = (git_repo / "docs" / "api.md").read_text(encoding="utf-8")
        split = split_frontmatter(text)
        assert split.frontmatter is not None
        assert split.frontmatter.type == "auto-generated"
        assert "Generated body." in split.body
        assert "## Original page" in split.body
        assert "## See also" in split.body
        assert "[Guide](guide.md)" in split.body
        assert "## Sources" in split.body
        assert "`__init__.py`" in split.body
        assert "](../src/demo/__init__.py)" in split.body

    def test_hybrid_injects_placeholder(self, git_repo: Path) -> None:
        script = _write_script(
            git_repo,
            "inject_table.py",
            'print("| cmd |")\nprint("| --- |")\nprint("| build |")\n',
        )
        write_text(git_repo / "codoc.yaml", _project_yaml())
        write_text(
            git_repo / "src" / "demo" / "codoc.spec.yaml",
            "\n".join(
                (
                    "docs:",
                    "  - id: loop",
                    "    type: hybrid",
                    "    path: docs/loop.md",
                    "    placeholders:",
                    "      - id: command-table",
                    f"        script: {script}",
                )
            ),
        )
        write_text(
            git_repo / "docs" / "loop.md",
            "\n".join(
                (
                    "# Loop",
                    "",
                    "Narrative stays.",
                    "",
                    '<!-- codoc:placeholder id="command-table" -->',
                    "old",
                    "<!-- /codoc:placeholder -->",
                    "",
                )
            ),
        )
        result = run_generate(git_repo)
        assert result.pages[0].action == "injected"
        text = (git_repo / "docs" / "loop.md").read_text(encoding="utf-8")
        assert "Narrative stays." in text
        assert "| build |" in text
        assert "\nold\n" not in text
        split = split_frontmatter(text)
        assert split.frontmatter is not None
        assert split.frontmatter.id == "loop"

    def test_cli_prints_tsv(self, git_repo: Path) -> None:
        write_text(git_repo / "codoc.yaml", _project_yaml())
        write_text(
            git_repo / "src" / "demo" / "codoc.spec.yaml",
            "docs:\n  - id: index\n    type: manual\n    path: docs/index.md\n",
        )
        stdout, stderr, code = run_cli(git_repo, ["generate"])
        assert code is None
        assert stderr == ""
        assert stdout.startswith("page_id\tpath\taction\n")
        assert "index\tdocs/index.md\tcreated\n" in stdout

    def test_missing_script_fails(self, git_repo: Path) -> None:
        write_text(git_repo / "codoc.yaml", _project_yaml())
        write_text(
            git_repo / "src" / "demo" / "codoc.spec.yaml",
            "\n".join(
                (
                    "docs:",
                    "  - id: api",
                    "    type: auto-generated",
                    "    path: docs/api.md",
                    "    script: .codoc/scripts/missing.py",
                )
            ),
        )
        with pytest.raises(GenerateError, match="script not found"):
            run_generate(git_repo)

    def test_manual_preserves_sibling_frontmatter_keys(self, git_repo: Path) -> None:
        write_text(git_repo / "codoc.yaml", _project_yaml())
        write_text(
            git_repo / "src" / "demo" / "codoc.spec.yaml",
            "docs:\n  - id: guide\n    type: manual\n    path: docs/guide.md\n",
        )
        write_text(
            git_repo / "docs" / "guide.md",
            "\n".join(
                (
                    "---",
                    "title: Keep",
                    "description: stays",
                    "codoc:",
                    "  id: stale",
                    "  type: manual",
                    "---",
                    "",
                    "# Keep me",
                    "",
                )
            ),
        )
        run_generate(git_repo)
        text = (git_repo / "docs" / "guide.md").read_text(encoding="utf-8")
        assert "title: Keep" in text
        assert "description: stays" in text
        split = split_frontmatter(text)
        assert split.frontmatter is not None
        assert split.frontmatter.id == "guide"

    def test_hybrid_missing_marker_fails_without_rewrite(self, git_repo: Path) -> None:
        script = _write_script(git_repo, "inject.py", 'print("new")\n')
        write_text(git_repo / "codoc.yaml", _project_yaml())
        write_text(
            git_repo / "src" / "demo" / "codoc.spec.yaml",
            "\n".join(
                (
                    "docs:",
                    "  - id: loop",
                    "    type: hybrid",
                    "    path: docs/loop.md",
                    "    placeholders:",
                    "      - id: command-table",
                    f"        script: {script}",
                )
            ),
        )
        original = "# Loop\n\nNo marker here.\n"
        write_text(git_repo / "docs" / "loop.md", original)
        with pytest.raises(GenerateError, match="placeholder marker missing"):
            run_generate(git_repo)
        assert (git_repo / "docs" / "loop.md").read_text(encoding="utf-8") == original

    def test_hybrid_does_not_append_link_footers(self, git_repo: Path) -> None:
        script = _write_script(git_repo, "inject.py", 'print("table")\n')
        write_text(git_repo / "codoc.yaml", _project_yaml())
        write_text(
            git_repo / "src" / "demo" / "codoc.spec.yaml",
            "\n".join(
                (
                    "docs:",
                    "  - id: guide",
                    "    type: manual",
                    "    path: docs/guide.md",
                    "  - id: loop",
                    "    type: hybrid",
                    "    path: docs/loop.md",
                    "    canonical: guide",
                    "    links:",
                    "      - id: guide",
                    "    placeholders:",
                    "      - id: command-table",
                    f"        script: {script}",
                )
            ),
        )
        write_text(git_repo / "docs" / "guide.md", "# Guide\n")
        write_text(
            git_repo / "docs" / "loop.md",
            "\n".join(
                (
                    "# Loop",
                    "",
                    '<!-- codoc:placeholder id="command-table" -->',
                    "",
                    "<!-- /codoc:placeholder -->",
                    "",
                )
            ),
        )
        run_generate(git_repo)
        text = (git_repo / "docs" / "loop.md").read_text(encoding="utf-8")
        assert "table" in text
        assert "## See also" not in text
        assert "## Original page" not in text
        assert "## Sources" not in text

    def test_script_outside_scripts_dir_fails(self, git_repo: Path) -> None:
        write_text(git_repo / "codoc.yaml", _project_yaml())
        write_text(git_repo / "evil.py", 'print("nope")\n')
        write_text(
            git_repo / "src" / "demo" / "codoc.spec.yaml",
            "\n".join(
                (
                    "docs:",
                    "  - id: api",
                    "    type: auto-generated",
                    "    path: docs/api.md",
                    "    script: evil.py",
                )
            ),
        )
        with pytest.raises(GenerateError, match="script outside scripts_dir"):
            run_generate(git_repo)


@pytest.mark.parametrize(
    ("from_path", "to_path", "expected"),
    [
        ("docs/a.md", "docs/b.md", "b.md"),
        ("docs/guides/a.md", "docs/api.md", "../api.md"),
        ("docs/a.md", "docs/guides/b.md", "guides/b.md"),
    ],
)
def test_relative_href(from_path: str, to_path: str, expected: str) -> None:
    assert relative_href(from_path, to_path) == expected
