import subprocess
from pathlib import Path

import pytest

from codoc.commands.init import InitError, run_init
from codoc.config import load_project_config
from codoc.discover import git_root
from codoc.model.spec import load_spec
from tests.support.cli import run_cli
from tests.support.git import git_repository
from tests.support.tmpdir import _REPO_ROOT


class InitTests:
    def test_init_writes_loadable_project(self) -> None:
        with git_repository(name="my-app") as repo:
            result = run_init(repo, yes=True, interactive=False)
            assert result.spec_path.as_posix() == "src/my_app/codoc.spec.yaml"
            config = load_project_config(repo / "codoc.yaml")
            assert config.engine.name == "zensical"
            assert config.vale.enabled is True
            assert config.llm.provider is None
            assert config.paths.scripts_dir == ".codoc/scripts"
            spec = load_spec(repo / result.spec_path)
            assert spec.page_count == 2
            assert (repo / ".codoc" / "scripts" / ".gitkeep").is_file()
            assert not (repo / "codoc.spec.yaml").exists()
            ignore = (repo / ".gitignore").read_text(encoding="utf-8")
            assert ".codoc/*" in ignore
            assert "!.codoc/scripts/" in ignore
            assert "!.codoc/scripts/**" in ignore
            assert "site/" in ignore
            assert ".codoc-engine.yml" in ignore
            out, err, code = run_cli(repo, ["status"])
        assert code in (0, None)
        assert err == ""
        assert "src/my_app/codoc.spec.yaml\tsrc/my_app\t2" in out
        assert "registry_pages\t2" in out

    def test_second_init_refuses_without_force(self, git_repo: Path) -> None:
        first = run_init(git_repo, yes=True, interactive=False)
        before = (git_repo / "codoc.yaml").read_text(encoding="utf-8")
        with pytest.raises(InitError) as caught:
            run_init(git_repo, yes=True, interactive=False)
        assert "codoc.yaml exists" in str(caught.value)
        assert first.spec_path.as_posix() in str(caught.value)
        assert "--force" in str(caught.value)
        assert (git_repo / "codoc.yaml").read_text(encoding="utf-8") == before
        out, err, code = run_cli(git_repo, ["init", "--yes"])
        assert code == 1
        assert "codoc init: codoc.yaml exists" in err
        assert out == ""

    def test_force_overwrites_managed_files(self) -> None:
        with git_repository(name="demo") as repo:
            run_init(repo, yes=True, interactive=False)
            (repo / "codoc.yaml").write_text("terms: [stale]\n", encoding="utf-8")
            (repo / "docs" / "index.md").write_text("stale\n", encoding="utf-8")
            result = run_init(repo, force=True, yes=True, interactive=False)
            config = load_project_config(repo / "codoc.yaml")
            assert config.terms == ()
            assert config.engine.name == "zensical"
            assert (repo / "docs" / "index.md").read_text(
                encoding="utf-8"
            ) == "# Documentation site\n\nPackage overview\n"
            assert Path("codoc.yaml") in result.written

    def test_uses_single_src_package(self) -> None:
        with git_repository(name="repo") as repo:
            pkg = repo / "src" / "widgets"
            pkg.mkdir(parents=True)
            (repo / "src" / "widgets.egg-info").mkdir()
            result = run_init(repo, yes=True, interactive=False)
            assert result.spec_path.as_posix() == "src/widgets/codoc.spec.yaml"

    def test_two_packages_create_sanitized_repo_name(self) -> None:
        with git_repository(name="cool-app") as repo:
            (repo / "src" / "one").mkdir(parents=True)
            (repo / "src" / "two").mkdir(parents=True)
            result = run_init(repo, yes=True, interactive=False)
            assert result.spec_path.as_posix() == "src/cool_app/codoc.spec.yaml"
            assert (repo / "src" / "cool_app" / "codoc.spec.yaml").is_file()

    def test_not_a_git_repo(self, tmp_dir: Path) -> None:
        with pytest.raises(InitError) as caught:
            run_init(tmp_dir, yes=True, interactive=False)
        assert not (tmp_dir / ".git").exists()
        assert not (tmp_dir / "codoc.yaml").exists()
        assert "not a git repository" in str(caught.value)

    def test_init_does_not_mkdir_under_cwd(self) -> None:
        # Regression: pkg.mkdir used to be cwd-relative and leaked empty dirs into src/.
        repo_src = _REPO_ROOT / "src"
        before = {path.name for path in repo_src.iterdir()}
        with git_repository(name="leak-probe") as repo:
            run_init(repo, yes=True, interactive=False)
            assert (repo / "src" / "leak_probe" / "codoc.spec.yaml").is_file()
        after = {path.name for path in repo_src.iterdir()}
        assert after == before

    def test_gitignore_tracks_scripts_gitkeep(self, git_repo: Path) -> None:
        run_init(git_repo, yes=True, interactive=False)
        root = git_root(git_repo)
        (root / ".codoc" / "generated").mkdir(parents=True)
        (root / ".codoc" / "generated" / "x").write_text("x", encoding="utf-8")
        (root / "site").mkdir()
        (root / "site" / "index.html").write_text("x", encoding="utf-8")
        status = subprocess.run(
            ["git", "status", "--porcelain", "-uall", "--ignored"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        dry = subprocess.run(
            ["git", "add", "-n", ".codoc/scripts/.gitkeep"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        assert "!! .codoc/generated/x" in status.stdout
        assert "!! site/index.html" in status.stdout
        assert "?? .codoc/scripts/.gitkeep" in status.stdout
        assert "add '.codoc/scripts/.gitkeep'" in dry.stdout

    def test_wizard_selections_write_llm_and_engine(self) -> None:
        answers = iter(
            [
                "mkdocs",  # engine
                "Demo Docs",  # site name
                "n",  # vale
                "Codoc, Vale",  # terms
                "cursor-cli",  # provider
                "composer-2",  # model
                "y",  # rewrite_stubs
            ]
        )

        def prompt(_message: str) -> str:
            return next(answers)

        with git_repository(name="wiz") as repo:
            result = run_init(repo, interactive=True, prompt=prompt)
            config = load_project_config(repo / "codoc.yaml")
            assert config.engine.name == "mkdocs"
            assert config.engine.site_name == "Demo Docs"
            assert config.vale.enabled is False
            assert config.terms == ("Codoc", "Vale")
            assert config.llm.provider == "cursor-cli"
            assert config.llm.model == "composer-2"
            assert config.llm.rewrite_stubs is True
            assert any("interactive wizard" in note for note in result.notes)
            text = (repo / "codoc.yaml").read_text(encoding="utf-8")
            assert "provider: cursor-cli" in text
            assert "rewrite_stubs: true" in text

    def test_existing_project_update_merges_config(self) -> None:
        answers = iter(
            [
                "y",  # confirm update
                "",  # engine default
                "",  # site default
                "",  # vale default
                "Extra",  # terms
                "openai",  # provider
                "gpt-4.1-mini",  # model
                "n",  # rewrite
            ]
        )

        def prompt(_message: str) -> str:
            return next(answers)

        with git_repository(name="again") as repo:
            run_init(repo, yes=True, interactive=False)
            before_spec = (repo / "src" / "again" / "codoc.spec.yaml").read_text(encoding="utf-8")
            result = run_init(repo, interactive=True, prompt=prompt)
            assert result.written == (Path("codoc.yaml"),)
            assert (repo / "src" / "again" / "codoc.spec.yaml").read_text(
                encoding="utf-8"
            ) == before_spec
            config = load_project_config(repo / "codoc.yaml")
            assert config.terms == ("Extra",)
            assert config.llm.provider == "openai"
            assert config.llm.model == "gpt-4.1-mini"
            assert any("updated existing" in note for note in result.notes)

    def test_cli_yes_flag_is_non_interactive(self) -> None:
        with git_repository(name="ci") as repo:
            out, err, code = run_cli(repo, ["init", "--yes"])
            assert code is None
            assert "codoc.yaml" in out
            assert "non-interactive defaults" in err or err == "" or "codoc init:" in err
            config = load_project_config(repo / "codoc.yaml")
            assert config.engine.name == "zensical"
            assert config.llm.provider is None
