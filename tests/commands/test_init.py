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
            result = run_init(repo)
            assert result.spec_path.as_posix() == "src/my_app/codoc.spec.yaml"
            config = load_project_config(repo / "codoc.yaml")
            assert config.engine.name == "zensical"
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
        first = run_init(git_repo)
        before = (git_repo / "codoc.yaml").read_text(encoding="utf-8")
        with pytest.raises(InitError) as caught:
            run_init(git_repo)
        assert "codoc.yaml exists" in str(caught.value)
        assert first.spec_path.as_posix() in str(caught.value)
        assert (git_repo / "codoc.yaml").read_text(encoding="utf-8") == before
        out, err, code = run_cli(git_repo, ["init"])
        assert code == 1
        assert "codoc init: codoc.yaml exists" in err
        assert out == ""

    def test_force_overwrites_managed_files(self) -> None:
        with git_repository(name="demo") as repo:
            run_init(repo)
            (repo / "codoc.yaml").write_text("terms: [stale]\n", encoding="utf-8")
            (repo / "docs" / "index.md").write_text("stale\n", encoding="utf-8")
            result = run_init(repo, force=True)
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
            result = run_init(repo)
            assert result.spec_path.as_posix() == "src/widgets/codoc.spec.yaml"

    def test_two_packages_create_sanitized_repo_name(self) -> None:
        with git_repository(name="cool-app") as repo:
            (repo / "src" / "one").mkdir(parents=True)
            (repo / "src" / "two").mkdir(parents=True)
            result = run_init(repo)
            assert result.spec_path.as_posix() == "src/cool_app/codoc.spec.yaml"
            assert (repo / "src" / "cool_app" / "codoc.spec.yaml").is_file()

    def test_not_a_git_repo(self, tmp_dir: Path) -> None:
        with pytest.raises(InitError) as caught:
            run_init(tmp_dir)
        assert not (tmp_dir / ".git").exists()
        assert not (tmp_dir / "codoc.yaml").exists()
        assert "not a git repository" in str(caught.value)

    def test_init_does_not_mkdir_under_cwd(self) -> None:
        # Regression: pkg.mkdir used to be cwd-relative and leaked empty dirs into src/.
        repo_src = _REPO_ROOT / "src"
        before = {path.name for path in repo_src.iterdir()}
        with git_repository(name="leak-probe") as repo:
            run_init(repo)
            assert (repo / "src" / "leak_probe" / "codoc.spec.yaml").is_file()
        after = {path.name for path in repo_src.iterdir()}
        assert after == before

    def test_gitignore_tracks_scripts_gitkeep(self, git_repo: Path) -> None:
        run_init(git_repo)
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
