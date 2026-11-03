import io
import os
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

import codoc.cli as cli
from codoc.commands.init import InitError, run_init
from codoc.config import load_project_config
from codoc.discover import git_root
from codoc.model.spec import load_spec
from tests.support.tmpdir import _REPO_ROOT, temporary_directory


@contextmanager
def _git_repo(name: str = "demo") -> Iterator[Path]:
    with temporary_directory() as parent:
        root = parent / name
        root.mkdir()
        subprocess.run(
            ["git", "init", "-q"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        yield root


def _run_in(path: Path, argv: list[str]) -> tuple[str, str, int | None]:
    previous = os.getcwd()
    os.chdir(path)
    stdout = io.StringIO()
    stderr = io.StringIO()
    code: int | None = None
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                cli.main(argv)
            except SystemExit as caught:
                status = caught.code
                code = status if isinstance(status, int) else None
        return stdout.getvalue(), stderr.getvalue(), code
    finally:
        os.chdir(previous)


class InitTests:
    def test_init_writes_loadable_project(self) -> None:
        with _git_repo("my-app") as repo:
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
            out, err, code = _run_in(repo, ["status"])
        assert code in (0, None)
        assert err == ""
        assert "src/my_app/codoc.spec.yaml\tsrc/my_app\t2" in out
        assert "registry_pages\t2" in out

    def test_second_init_refuses_without_force(self) -> None:
        with _git_repo() as repo:
            first = run_init(repo)
            before = (repo / "codoc.yaml").read_text(encoding="utf-8")
            with pytest.raises(InitError) as caught:
                run_init(repo)
            assert "codoc.yaml exists" in str(caught.value)
            assert first.spec_path.as_posix() in str(caught.value)
            assert (repo / "codoc.yaml").read_text(encoding="utf-8") == before
            out, err, code = _run_in(repo, ["init"])
        assert code == 1
        assert "codoc init: codoc.yaml exists" in err
        assert out == ""

    def test_force_overwrites_managed_files(self) -> None:
        with _git_repo("demo") as repo:
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
        with _git_repo("repo") as repo:
            pkg = repo / "src" / "widgets"
            pkg.mkdir(parents=True)
            (repo / "src" / "widgets.egg-info").mkdir()
            result = run_init(repo)
            assert result.spec_path.as_posix() == "src/widgets/codoc.spec.yaml"

    def test_two_packages_create_sanitized_repo_name(self) -> None:
        with _git_repo("cool-app") as repo:
            (repo / "src" / "one").mkdir(parents=True)
            (repo / "src" / "two").mkdir(parents=True)
            result = run_init(repo)
            assert result.spec_path.as_posix() == "src/cool_app/codoc.spec.yaml"
            assert (repo / "src" / "cool_app" / "codoc.spec.yaml").is_file()

    def test_not_a_git_repo(self) -> None:
        with temporary_directory() as start:
            with pytest.raises(InitError) as caught:
                run_init(start)
            assert not (start / ".git").exists()
            assert not (start / "codoc.yaml").exists()
        assert "not a git repository" in str(caught.value)

    def test_init_does_not_mkdir_under_cwd(self) -> None:
        # Regression: pkg.mkdir used to be cwd-relative and leaked empty dirs into src/.
        repo_src = _REPO_ROOT / "src"
        before = {path.name for path in repo_src.iterdir()}
        with _git_repo("leak-probe") as repo:
            run_init(repo)
            assert (repo / "src" / "leak_probe" / "codoc.spec.yaml").is_file()
        after = {path.name for path in repo_src.iterdir()}
        assert after == before

    def test_gitignore_tracks_scripts_gitkeep(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            root = git_root(repo)
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
