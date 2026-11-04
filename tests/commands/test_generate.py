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
        assert "draft skipped" in stderr
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

    def test_offline_draft_skip_note_on_new_manual(self, git_repo: Path) -> None:
        write_text(git_repo / "codoc.yaml", _project_yaml())
        write_text(
            git_repo / "src" / "demo" / "codoc.spec.yaml",
            "docs:\n  - id: guide\n    type: manual\n    path: docs/guide.md\n",
        )
        stdout, stderr, code = run_cli(git_repo, ["generate"])
        assert code is None
        assert "draft skipped" in stderr
        assert "guide\tdocs/guide.md\tcreated\n" in stdout
        assert (git_repo / "docs" / "guide.md").is_file()

    def test_llm_draft_used_for_new_manual(self, git_repo: Path, monkeypatch) -> None:
        write_text(
            git_repo / "codoc.yaml",
            "engine:\n  name: zensical\nllm:\n  provider: openai\n  model: gpt-test\n",
        )
        write_text(
            git_repo / "src" / "demo" / "codoc.spec.yaml",
            "docs:\n  - id: guide\n    type: manual\n    path: docs/guide.md\n",
        )
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        def fake_chat(**_kwargs: object) -> str:
            return "# Drafted\n\nFrom the model.\n"

        monkeypatch.setattr("codoc.generate.draft.chat_completion", fake_chat)
        result = run_generate(git_repo)
        assert result.pages[0].action == "created"
        text = (git_repo / "docs" / "guide.md").read_text(encoding="utf-8")
        assert "From the model." in text
        assert not any("draft skipped" in note for note in result.notes)

    def test_existing_page_with_llm_does_not_call_model(self, git_repo: Path, monkeypatch) -> None:
        write_text(
            git_repo / "codoc.yaml",
            "\n".join(
                (
                    "engine:",
                    "  name: zensical",
                    "llm:",
                    "  provider: openai",
                    "  model: gpt-test",
                    "  rewrite_stubs: true",
                )
            ),
        )
        write_text(
            git_repo / "src" / "demo" / "codoc.spec.yaml",
            "docs:\n  - id: guide\n    type: manual\n    path: docs/guide.md\n",
        )
        write_text(
            git_repo / "docs" / "guide.md",
            "---\ncodoc:\n  id: guide\n  type: manual\n---\n\n# Guide\n\nUser prose stays.\n",
        )
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        calls: list[object] = []

        def fake_chat(**kwargs: object) -> str:
            calls.append(kwargs)
            return "# Nope\n"

        monkeypatch.setattr("codoc.generate.draft.chat_completion", fake_chat)
        result = run_generate(git_repo)
        assert calls == []
        assert any("existing page preserved" in note for note in result.notes)
        text = (git_repo / "docs" / "guide.md").read_text(encoding="utf-8")
        assert "User prose stays." in text
        assert result.pages[0].action == "frontmatter"

    def test_rewrite_stubs_rewrites_default_manual_stub(self, git_repo: Path, monkeypatch) -> None:
        write_text(
            git_repo / "codoc.yaml",
            "\n".join(
                (
                    "engine:",
                    "  name: zensical",
                    "llm:",
                    "  provider: openai",
                    "  model: gpt-test",
                    "  rewrite_stubs: true",
                )
            ),
        )
        write_text(
            git_repo / "src" / "demo" / "codoc.spec.yaml",
            "docs:\n  - id: guide\n    type: manual\n    path: docs/guide.md\n",
        )
        write_text(
            git_repo / "docs" / "guide.md",
            "---\ncodoc:\n  id: guide\n  type: manual\n---\n\n# guide\n",
        )
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        def fake_chat(**_kwargs: object) -> str:
            return "# Guide\n\nRewritten stub.\n"

        monkeypatch.setattr("codoc.generate.draft.chat_completion", fake_chat)
        result = run_generate(git_repo)
        assert result.pages[0].action == "rewritten"
        assert "Rewritten stub." in (git_repo / "docs" / "guide.md").read_text(encoding="utf-8")

    def test_second_generate_reuses_warm_cache(self, git_repo: Path) -> None:
        script = _write_script(git_repo, "gen.py", 'print("# API")\nprint("body")\n')
        write_text(git_repo / "codoc.yaml", _project_yaml())
        write_text(git_repo / "src" / "demo" / "__init__.py", "X = 1\n")
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
                )
            ),
        )
        first = run_generate(git_repo)
        assert {page.action for page in first.pages} == {"created", "generated"}
        before = (git_repo / "docs" / "api.md").read_text(encoding="utf-8")
        second = run_generate(git_repo)
        assert all(page.action == "cached" for page in second.pages)
        assert any("cache hit" in note for note in second.notes)
        assert (git_repo / "docs" / "api.md").read_text(encoding="utf-8") == before
        cache_dir = git_repo / ".codoc" / "cache" / "generate"
        assert cache_dir.is_dir()
        assert any(cache_dir.iterdir())

    def test_cache_invalidates_when_script_helper_changes(self, git_repo: Path) -> None:
        write_text(git_repo / ".codoc" / "scripts" / "helper.txt", "v1\n")
        script = _write_script(
            git_repo,
            "gen.py",
            "from pathlib import Path\n"
            "print('# API')\n"
            "print(Path('.codoc/scripts/helper.txt').read_text().strip())\n",
        )
        write_text(git_repo / "codoc.yaml", _project_yaml())
        write_text(git_repo / "src" / "demo" / "__init__.py", "X = 1\n")
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
                )
            ),
        )
        run_generate(git_repo)
        assert "v1" in (git_repo / "docs" / "api.md").read_text(encoding="utf-8")
        write_text(git_repo / ".codoc" / "scripts" / "helper.txt", "v2\n")
        result = run_generate(git_repo)
        assert any(page.action == "generated" for page in result.pages)
        assert "v2" in (git_repo / "docs" / "api.md").read_text(encoding="utf-8")

    def test_cache_invalidates_when_sibling_page_moves(self, git_repo: Path) -> None:
        script = _write_script(git_repo, "gen.py", 'print("# API")\n')
        write_text(git_repo / "codoc.yaml", _project_yaml())
        write_text(git_repo / "src" / "a" / "__init__.py", "")
        write_text(
            git_repo / "src" / "a" / "codoc.spec.yaml",
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
                    "          links:",
                    "            - id: other",
                    "              label: Other",
                )
            ),
        )
        write_text(
            git_repo / "src" / "b" / "codoc.spec.yaml",
            "docs:\n  - id: other\n    type: manual\n    path: docs/other.md\n",
        )
        run_generate(git_repo)
        assert "](other.md)" in (git_repo / "docs" / "api.md").read_text(encoding="utf-8")
        write_text(
            git_repo / "src" / "b" / "codoc.spec.yaml",
            "docs:\n  - id: other\n    type: manual\n    path: docs/moved/other.md\n",
        )
        (git_repo / "docs" / "other.md").unlink()
        result = run_generate(git_repo)
        assert any(
            page.page_id == "api.ref" and page.action == "generated" for page in result.pages
        )
        assert "](moved/other.md)" in (git_repo / "docs" / "api.md").read_text(encoding="utf-8")

    def test_hand_edit_auto_page_is_restored(self, git_repo: Path) -> None:
        script = _write_script(git_repo, "gen.py", 'print("# API")\nprint("canonical")\n')
        write_text(git_repo / "codoc.yaml", _project_yaml())
        write_text(git_repo / "src" / "demo" / "__init__.py", "X = 1\n")
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
                )
            ),
        )
        run_generate(git_repo)
        write_text(git_repo / "docs" / "api.md", "hand edit\n")
        result = run_generate(git_repo)
        assert any(
            page.page_id == "api.ref" and page.action == "generated" for page in result.pages
        )
        assert "canonical" in (git_repo / "docs" / "api.md").read_text(encoding="utf-8")

    def test_no_cache_flag_bypasses_warm_cache(self, git_repo: Path) -> None:
        write_text(git_repo / "codoc.yaml", _project_yaml())
        write_text(
            git_repo / "src" / "demo" / "codoc.spec.yaml",
            "docs:\n  - id: guide\n    type: manual\n    path: docs/guide.md\n",
        )
        run_generate(git_repo)
        result = run_generate(git_repo, no_cache=True)
        assert all(page.action != "cached" for page in result.pages)
        assert any("cache bypassed" in note for note in result.notes)

    def test_draft_skip_does_not_write_warm_cache(self, git_repo: Path, monkeypatch) -> None:
        write_text(
            git_repo / "codoc.yaml",
            "engine:\n  name: zensical\nllm:\n  provider: openai\n  model: gpt-test\n",
        )
        write_text(
            git_repo / "src" / "demo" / "codoc.spec.yaml",
            "docs:\n  - id: guide\n    type: manual\n    path: docs/guide.md\n",
        )
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        first = run_generate(git_repo)
        assert any("draft skipped" in note for note in first.notes)
        assert any("cache not written" in note for note in first.notes)
        cache_dir = git_repo / ".codoc" / "cache" / "generate"
        assert not cache_dir.exists() or not any(cache_dir.iterdir())

    def test_scoped_generate_only_touches_matching_spec(self, git_repo: Path) -> None:
        write_text(git_repo / "codoc.yaml", _project_yaml())
        write_text(
            git_repo / "src" / "a" / "codoc.spec.yaml",
            "docs:\n  - id: a\n    type: manual\n    path: docs/a.md\n",
        )
        write_text(
            git_repo / "src" / "b" / "codoc.spec.yaml",
            "docs:\n  - id: b\n    type: manual\n    path: docs/b.md\n",
        )
        result = run_generate(git_repo, scope="src/a")
        assert [page.page_id for page in result.pages] == ["a"]
        assert (git_repo / "docs" / "a.md").is_file()
        assert not (git_repo / "docs" / "b.md").is_file()
        stdout, stderr, code = run_cli(git_repo, ["generate", "--scope", "src/b"])
        assert code is None
        assert "b\tdocs/b.md\tcreated\n" in stdout
        assert "a\t" not in stdout.split("page_id\tpath\taction\n", 1)[1]

    def test_parent_coverage_excludes_child_scope_sources(self, git_repo: Path) -> None:
        script = _write_script(git_repo, "gen_parent.py", 'print("# Parent")\n')
        write_text(git_repo / "codoc.yaml", _project_yaml())
        write_text(git_repo / "src" / "pkg" / "__init__.py", "P = 1\n")
        write_text(git_repo / "src" / "pkg" / "child" / "__init__.py", "C = 1\n")
        write_text(
            git_repo / "src" / "pkg" / "codoc.spec.yaml",
            "\n".join(
                (
                    "docs:",
                    "  - id: parent",
                    "    type: manual",
                    "    path: docs/parent.md",
                    "coverage:",
                    "  source:",
                    "    - id: pkg",
                    "      type: auto-generated",
                    "      paths:",
                    '        - "**/*.py"',
                    "      docs:",
                    "        - id: parent.ref",
                    "          path: docs/parent-ref.md",
                    f"          script: {script}",
                )
            ),
        )
        write_text(
            git_repo / "src" / "pkg" / "child" / "codoc.spec.yaml",
            "docs:\n  - id: child\n    type: manual\n    path: docs/child.md\n",
        )
        result = run_generate(git_repo)
        text = (git_repo / "docs" / "parent-ref.md").read_text(encoding="utf-8")
        assert "## Sources" in text
        assert "`__init__.py`" in text
        assert "src/pkg/__init__.py" in text or "](../src/pkg/__init__.py)" in text
        assert "child/__init__.py" not in text
        assert "parent.ref" in {page.page_id for page in result.pages}

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
