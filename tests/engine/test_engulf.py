from pathlib import Path

from codoc.commands.init import run_init
from codoc.config import load_project_config
from codoc.engine.codegen import ensure_generated
from codoc.engine.engulf import IMPORTED_DIR, seed_engine_from_legacy

_MKDOCS = """\
site_name: Legacy Site
docs_dir: handbook
site_dir: public
theme:
  name: material
nav:
  - Home: index.md
  - Guide: guide.md
plugins:
  - search
"""


class EngulfTests:
    def test_ensure_generated_imports_and_archives_mkdocs_yml(self, git_repo: Path) -> None:
        (git_repo / "mkdocs.yml").write_text(_MKDOCS, encoding="utf-8")
        (git_repo / "codoc.yaml").write_text(
            "engine:\n  name: zensical\n  docs_dir: docs\n  site_dir: site\n",
            encoding="utf-8",
        )
        result = ensure_generated(git_repo)
        assert result.notes
        assert "imported engine settings from mkdocs.yml" in result.notes[0]
        assert "moved mkdocs.yml" in result.notes[0]
        assert not (git_repo / "mkdocs.yml").exists()
        assert (git_repo / IMPORTED_DIR / "mkdocs.yml").is_file()
        config = load_project_config(git_repo / "codoc.yaml")
        assert config.engine.name == "mkdocs"
        assert config.engine.docs_dir == "handbook"
        assert config.engine.site_dir == "public"
        assert config.engine.site_name == "Legacy Site"
        assert config.engine.theme == {"name": "material"}
        assert config.engine.nav == [{"Home": "index.md"}, {"Guide": "guide.md"}]
        shim = (git_repo / ".codoc-engine.yml").read_text(encoding="utf-8")
        assert "site_name: Legacy Site" in shim
        assert "docs_dir: handbook" in shim
        assert "name: material" in shim
        assert "Home: index.md" in shim
        assert "plugins:" not in shim

    def test_ensure_generated_does_not_clobber_custom_engine_but_archives(
        self, git_repo: Path
    ) -> None:
        (git_repo / "mkdocs.yml").write_text(
            "docs_dir: handbook\nsite_dir: public\n",
            encoding="utf-8",
        )
        (git_repo / "codoc.yaml").write_text(
            "engine:\n  name: mkdocs\n  docs_dir: guide\n  site_dir: out\n",
            encoding="utf-8",
        )
        result = ensure_generated(git_repo)
        assert any("moved mkdocs.yml" in note for note in result.notes)
        config = load_project_config(git_repo / "codoc.yaml")
        assert config.engine.docs_dir == "guide"
        assert config.engine.site_dir == "out"
        assert not (git_repo / "mkdocs.yml").exists()
        assert (git_repo / IMPORTED_DIR / "mkdocs.yml").is_file()

    def test_prefer_zensical_yml_when_both_exist(self, git_repo: Path) -> None:
        (git_repo / "zensical.yml").write_text(
            "docs_dir: zdocs\nsite_dir: zsite\n",
            encoding="utf-8",
        )
        (git_repo / "mkdocs.yml").write_text(
            "docs_dir: mdocs\nsite_dir: msite\n",
            encoding="utf-8",
        )
        engine, source = seed_engine_from_legacy(git_repo)
        assert source is not None
        assert source.name == "zensical.yml"
        assert engine.name == "zensical"
        assert engine.docs_dir == "zdocs"
        assert engine.site_dir == "zsite"

    def test_second_ensure_generated_is_quiet_when_already_imported(
        self, git_repo: Path
    ) -> None:
        (git_repo / "mkdocs.yml").write_text(
            "docs_dir: handbook\nsite_dir: public\n",
            encoding="utf-8",
        )
        (git_repo / "codoc.yaml").write_text(
            "engine:\n  name: zensical\n  docs_dir: docs\n  site_dir: site\n",
            encoding="utf-8",
        )
        first = ensure_generated(git_repo)
        assert first.notes
        second = ensure_generated(git_repo)
        assert second.notes == ()
        assert not (git_repo / "mkdocs.yml").exists()


class InitEngulfTests:
    def test_init_with_neither_legacy_file(self, git_repo: Path) -> None:
        result = run_init(git_repo)
        assert result.notes == ()
        assert not (git_repo / "mkdocs.yml").exists()
        assert not (git_repo / "zensical.yml").exists()
        assert not (git_repo / IMPORTED_DIR).exists()
        config = load_project_config(git_repo / "codoc.yaml")
        assert config.engine.name == "zensical"
        assert config.engine.docs_dir == "docs"
        assert config.engine.site_dir == "site"
        assert config.engine.site_name == "Documentation"
        assert config.engine.theme is None
        assert config.engine.nav is None

    def test_init_with_existing_mkdocs_yml(self, git_repo: Path) -> None:
        (git_repo / "mkdocs.yml").write_text(_MKDOCS, encoding="utf-8")
        result = run_init(git_repo)
        assert any("imported engine settings from mkdocs.yml" in n for n in result.notes)
        assert any("moved mkdocs.yml" in n for n in result.notes)
        assert not (git_repo / "mkdocs.yml").exists()
        assert (git_repo / IMPORTED_DIR / "mkdocs.yml").is_file()
        config = load_project_config(git_repo / "codoc.yaml")
        assert config.engine.name == "mkdocs"
        assert config.engine.docs_dir == "handbook"
        assert config.engine.site_dir == "public"
        assert config.engine.site_name == "Legacy Site"
        assert config.engine.theme == {"name": "material"}
        assert config.engine.nav == [{"Home": "index.md"}, {"Guide": "guide.md"}]

    def test_init_with_existing_zensical_yml(self, git_repo: Path) -> None:
        (git_repo / "zensical.yml").write_text(
            "site_name: Z Docs\ndocs_dir: zdocs\nsite_dir: zout\n"
            "theme: readthedocs\nnav:\n  - Intro: index.md\n",
            encoding="utf-8",
        )
        result = run_init(git_repo)
        assert any("imported engine settings from zensical.yml" in n for n in result.notes)
        assert any("moved zensical.yml" in n for n in result.notes)
        assert not (git_repo / "zensical.yml").exists()
        assert (git_repo / IMPORTED_DIR / "zensical.yml").is_file()
        config = load_project_config(git_repo / "codoc.yaml")
        assert config.engine.name == "zensical"
        assert config.engine.docs_dir == "zdocs"
        assert config.engine.site_dir == "zout"
        assert config.engine.site_name == "Z Docs"
        assert config.engine.theme == {"name": "readthedocs"}
        assert config.engine.nav == [{"Intro": "index.md"}]
