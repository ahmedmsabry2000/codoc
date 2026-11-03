"""Behavior tests for codoc validate."""

import json
from pathlib import Path

from codoc.commands.generate import run_generate
from codoc.commands.validate import run_validate
from tests.support.cli import run_cli
from tests.support.fs import write_text


def _seed(repo: Path) -> None:
    write_text(repo / "codoc.yaml", "engine:\n  name: zensical\n")
    write_text(
        repo / "src" / "demo" / "codoc.spec.yaml",
        "\n".join(
            (
                "docs:",
                "  - id: guide",
                "    type: manual",
                "    path: docs/guide.md",
                "  - id: api",
                "    type: auto-generated",
                "    path: docs/api.md",
                "    script: .codoc/scripts/gen_api.py",
                "    canonical: guide",
            )
        ),
    )
    write_text(
        repo / ".codoc" / "scripts" / "gen_api.py",
        'print("# API")\nprint()\nprint("See the guide.")\nprint()\nprint("[guide](guide.md)")\n',
    )
    write_text(repo / "docs" / "guide.md", "# Guide\n\nManual body.\n")


class ValidateTests:
    def test_passes_after_generate_and_writes_rag(self, git_repo: Path) -> None:
        _seed(git_repo)
        run_generate(git_repo)
        result = run_validate(git_repo)
        assert result.ok
        assert result.rag_path is not None
        assert result.rag_path.is_file()
        payload = json.loads(result.rag_path.read_text(encoding="utf-8"))
        assert payload["version"] == 1
        assert payload["chunks"]
        stdout, stderr, code = run_cli(git_repo, ["validate"])
        assert code is None
        assert "severity\tcode\tpath\tmessage" in stdout
        assert "rag\t" in stdout

    def test_broken_link_fails(self, git_repo: Path) -> None:
        _seed(git_repo)
        run_generate(git_repo)
        api = git_repo / "docs" / "api.md"
        text = api.read_text(encoding="utf-8")
        api.write_text(text + "\n[missing](nope.md)\n", encoding="utf-8")
        result = run_validate(git_repo)
        assert not result.ok
        assert any(item.code == "link.broken" for item in result.findings)

    def test_link_title_and_fenced_sample_ignored(self, git_repo: Path) -> None:
        _seed(git_repo)
        run_generate(git_repo)
        guide = git_repo / "docs" / "guide.md"
        guide.write_text(
            "\n".join(
                (
                    "---",
                    "codoc:",
                    "  id: guide",
                    "  type: manual",
                    "---",
                    "",
                    "# Guide",
                    "",
                    '[api](api.md "API page")',
                    "",
                    "```md",
                    "[also missing](not-a-file.md)",
                    "```",
                    "",
                )
            ),
            encoding="utf-8",
        )
        result = run_validate(git_repo)
        assert result.ok
        assert not any(item.code == "link.broken" for item in result.findings)

    def test_frontmatter_mismatch_fails(self, git_repo: Path) -> None:
        _seed(git_repo)
        run_generate(git_repo)
        guide = git_repo / "docs" / "guide.md"
        guide.write_text(
            "---\ncodoc:\n  id: wrong\n  type: manual\n---\n\n# Guide\n",
            encoding="utf-8",
        )
        result = run_validate(git_repo)
        assert not result.ok
        assert any(item.code == "frontmatter.id" for item in result.findings)

    def test_invalid_frontmatter_is_finding(self, git_repo: Path) -> None:
        _seed(git_repo)
        run_generate(git_repo)
        guide = git_repo / "docs" / "guide.md"
        guide.write_text("---\ncodoc: [\n---\n\n# Guide\n", encoding="utf-8")
        result = run_validate(git_repo)
        assert not result.ok
        assert any(item.code == "frontmatter.invalid" for item in result.findings)

    def test_git_candidates_for_changed_coverage(self, git_repo: Path) -> None:
        write_text(git_repo / "codoc.yaml", "engine:\n  name: zensical\n")
        write_text(git_repo / "src" / "demo" / "__init__.py", "VALUE = 1\n")
        write_text(
            git_repo / "src" / "demo" / "codoc.spec.yaml",
            "\n".join(
                (
                    "docs:",
                    "  - id: index",
                    "    type: manual",
                    "    path: docs/index.md",
                    "coverage:",
                    "  source:",
                    "    - id: pkg",
                    "      type: auto-generated",
                    "      paths:",
                    '        - "*.py"',
                    "      docs:",
                    "        - id: pkg.overview",
                    "          path: docs/package.md",
                )
            ),
        )
        run_generate(git_repo)
        write_text(git_repo / "src" / "demo" / "__init__.py", "VALUE = 2\n")
        result = run_validate(git_repo)
        assert result.ok
        assert "src/demo/__init__.py" in result.candidates
