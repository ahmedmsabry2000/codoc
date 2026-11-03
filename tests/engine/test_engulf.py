import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from codoc.config import load_project_config
from codoc.engine.codegen import ensure_generated
from codoc.engine.engulf import seed_engine_from_legacy
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


class EngulfTests:
    def test_ensure_generated_imports_mkdocs_yml_keeps_file(self) -> None:
        with _git_repo() as repo:
            (repo / "mkdocs.yml").write_text(
                "site_name: Legacy\ndocs_dir: handbook\nsite_dir: public\n",
                encoding="utf-8",
            )
            (repo / "codoc.yaml").write_text(
                "engine:\n  name: zensical\n  docs_dir: docs\n  site_dir: site\n",
                encoding="utf-8",
            )
            result = ensure_generated(repo)
            assert result.notes
            assert "mkdocs.yml" in result.notes[0]
            assert "left mkdocs.yml in place" in result.notes[0]
            assert (repo / "mkdocs.yml").is_file()
            config = load_project_config(repo / "codoc.yaml")
            assert config.engine.name == "mkdocs"
            assert config.engine.docs_dir == "handbook"
            assert config.engine.site_dir == "public"
            shim = (repo / ".codoc-engine.yml").read_text(encoding="utf-8")
            assert "docs_dir: handbook" in shim
            assert "site_dir: public" in shim

    def test_ensure_generated_does_not_clobber_custom_engine(self) -> None:
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
            assert result.notes == ()
            config = load_project_config(repo / "codoc.yaml")
            assert config.engine.docs_dir == "guide"
            assert config.engine.site_dir == "out"
            assert (repo / "mkdocs.yml").is_file()

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
            engine, note = seed_engine_from_legacy(repo)
            assert note is not None
            assert "zensical.yml" in note
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
            assert (repo / "mkdocs.yml").is_file()
