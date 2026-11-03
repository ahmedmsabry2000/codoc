import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from codoc.commands.init import run_init
from codoc.config import load_project_config
from codoc.engine.codegen import ensure_generated
from codoc.engine.engulf import IMPORTED_DIR, seed_engine_from_legacy
from tests.support.tmpdir import temporary_directory


@contextmanager
def _git_repo() -> Iterator[Path]:
    with temporary_directory() as root:
        subprocess.run(
            ["git", "init", "-q"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        yield root


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
    def test_ensure_generated_imports_and_archives_mkdocs_yml(self) -> None:
        with _git_repo() as repo:
            (repo / "mkdocs.yml").write_text(_MKDOCS, encoding="utf-8")
            (repo / "codoc.yaml").write_text(
                "engine:\n  name: zensical\n  docs_dir: docs\n  site_dir: site\n",
                encoding="utf-8",
            )
            result = ensure_generated(repo)
            assert result.notes
            assert "imported engine settings from mkdocs.yml" in result.notes[0]
            assert "moved mkdocs.yml" in result.notes[0]
            assert not (repo / "mkdocs.yml").exists()
            assert (repo / IMPORTED_DIR / "mkdocs.yml").is_file()
            config = load_project_config(repo / "codoc.yaml")
            assert config.engine.name == "mkdocs"
            assert config.engine.docs_dir == "handbook"
            assert config.engine.site_dir == "public"
            assert config.engine.site_name == "Legacy Site"
            assert config.engine.theme == {"name": "material"}
            assert config.engine.nav == [{"Home": "index.md"}, {"Guide": "guide.md"}]
            shim = (repo / ".codoc-engine.yml").read_text(encoding="utf-8")
            assert "site_name: Legacy Site" in shim
            assert "docs_dir: handbook" in shim
            assert "name: material" in shim
            assert "Home: index.md" in shim
            assert "plugins:" not in shim

    def test_ensure_generated_does_not_clobber_custom_engine_but_archives(self) -> None:
        with _git_repo() as repo:
            (repo / "mkdocs.yml").write_text(
                "docs_dir: handbook\nsite_dir: public\n",
                encoding="utf-8",
            )
            (repo / "codoc.yaml").write_text(
                "engine:\n  name: mkdocs\n  docs_dir: guide\n  site_dir: out\n",
                encoding="utf-8",
            )
            result = ensure_generated(repo)
            assert any("moved mkdocs.yml" in note for note in result.notes)
            config = load_project_config(repo / "codoc.yaml")
            assert config.engine.docs_dir == "guide"
            assert config.engine.site_dir == "out"
            assert not (repo / "mkdocs.yml").exists()
            assert (repo / IMPORTED_DIR / "mkdocs.yml").is_file()

    def test_prefer_zensical_yml_when_both_exist(self) -> None:
        with _git_repo() as repo:
            (repo / "zensical.yml").write_text(
                "docs_dir: zdocs\nsite_dir: zsite\n",
                encoding="utf-8",
            )
            (repo / "mkdocs.yml").write_text(
                "docs_dir: mdocs\nsite_dir: msite\n",
                encoding="utf-8",
            )
            engine, source = seed_engine_from_legacy(repo)
            assert source is not None
            assert source.name == "zensical.yml"
            assert engine.name == "zensical"
            assert engine.docs_dir == "zdocs"
            assert engine.site_dir == "zsite"

    def test_second_ensure_generated_is_quiet_when_already_imported(self) -> None:
        with _git_repo() as repo:
            (repo / "mkdocs.yml").write_text(
                "docs_dir: handbook\nsite_dir: public\n",
                encoding="utf-8",
            )
            (repo / "codoc.yaml").write_text(
                "engine:\n  name: zensical\n  docs_dir: docs\n  site_dir: site\n",
                encoding="utf-8",
            )
            first = ensure_generated(repo)
            assert first.notes
            second = ensure_generated(repo)
            assert second.notes == ()
            assert not (repo / "mkdocs.yml").exists()


class InitEngulfTests:
    def test_init_with_neither_legacy_file(self) -> None:
        with _git_repo() as repo:
            result = run_init(repo)
            assert result.notes == ()
            assert not (repo / "mkdocs.yml").exists()
            assert not (repo / "zensical.yml").exists()
            assert not (repo / IMPORTED_DIR).exists()
            config = load_project_config(repo / "codoc.yaml")
            assert config.engine.name == "zensical"
            assert config.engine.docs_dir == "docs"
            assert config.engine.site_dir == "site"
            assert config.engine.site_name == "Documentation"
            assert config.engine.theme is None
            assert config.engine.nav is None

    def test_init_with_existing_mkdocs_yml(self) -> None:
        with _git_repo() as repo:
            (repo / "mkdocs.yml").write_text(_MKDOCS, encoding="utf-8")
            result = run_init(repo)
            assert any("imported engine settings from mkdocs.yml" in n for n in result.notes)
            assert any("moved mkdocs.yml" in n for n in result.notes)
            assert not (repo / "mkdocs.yml").exists()
            assert (repo / IMPORTED_DIR / "mkdocs.yml").is_file()
            config = load_project_config(repo / "codoc.yaml")
            assert config.engine.name == "mkdocs"
            assert config.engine.docs_dir == "handbook"
            assert config.engine.site_dir == "public"
            assert config.engine.site_name == "Legacy Site"
            assert config.engine.theme == {"name": "material"}
            assert config.engine.nav == [{"Home": "index.md"}, {"Guide": "guide.md"}]

    def test_init_with_existing_zensical_yml(self) -> None:
        with _git_repo() as repo:
            (repo / "zensical.yml").write_text(
                "site_name: Z Docs\ndocs_dir: zdocs\nsite_dir: zout\n"
                "theme: readthedocs\nnav:\n  - Intro: index.md\n",
                encoding="utf-8",
            )
            result = run_init(repo)
            assert any("imported engine settings from zensical.yml" in n for n in result.notes)
            assert any("moved zensical.yml" in n for n in result.notes)
            assert not (repo / "zensical.yml").exists()
            assert (repo / IMPORTED_DIR / "zensical.yml").is_file()
            config = load_project_config(repo / "codoc.yaml")
            assert config.engine.name == "zensical"
            assert config.engine.docs_dir == "zdocs"
            assert config.engine.site_dir == "zout"
            assert config.engine.site_name == "Z Docs"
            assert config.engine.theme == {"name": "readthedocs"}
            assert config.engine.nav == [{"Intro": "index.md"}]
