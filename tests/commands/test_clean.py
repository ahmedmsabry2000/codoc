import io
import os
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

import codoc.cli as cli
from codoc.commands.clean import CleanError, run_clean
from codoc.commands.init import run_init
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


def _touch(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class CleanCmdTests:
    def test_clean_removes_generated_keeps_scripts(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            _touch(repo / "site" / "index.html")
            _touch(repo / ".codoc-engine.yml", "# Generated\n")
            _touch(repo / "mkdocs.yml", "# legacy\n")
            _touch(repo / ".codoc" / "generated" / ".vale.ini")
            _touch(repo / ".codoc" / "cache" / "x")
            _touch(repo / ".codoc" / "logs" / "serve.log")
            _touch(repo / ".codoc" / "scripts" / "keep.py", "print(1)\n")
            with patch("codoc.commands.clean.stop_serve", return_value=False):
                result = run_clean(repo)
            assert not result.stopped_serve
            assert not (repo / "site").exists()
            assert not (repo / ".codoc-engine.yml").exists()
            assert not (repo / "mkdocs.yml").exists()
            assert not (repo / ".codoc" / "generated").exists()
            assert not (repo / ".codoc" / "cache").exists()
            assert not (repo / ".codoc" / "logs").exists()
            assert (repo / ".codoc" / "scripts" / "keep.py").is_file()
            assert (repo / ".codoc" / "scripts" / ".gitkeep").is_file()
            assert Path("site") in result.removed
            assert Path(".codoc-engine.yml") in result.removed
            assert Path("mkdocs.yml") in result.removed

    def test_clean_uses_configured_site_dir(self) -> None:
        with _git_repo() as repo:
            (repo / "codoc.yaml").write_text(
                "engine:\n  site_dir: out/html\n",
                encoding="utf-8",
            )
            _touch(repo / "out" / "html" / "index.html")
            with patch("codoc.commands.clean.stop_serve", return_value=False):
                result = run_clean(repo)
            assert not (repo / "out" / "html").exists()
            assert Path("out/html") in result.removed

    def test_clean_stops_serve(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            with patch("codoc.commands.clean.stop_serve", return_value=True) as stop:
                result = run_clean(repo)
            stop.assert_called_once()
            assert os.path.samefile(stop.call_args.args[0], repo)
            assert result.stopped_serve

    def test_clean_outside_repo_raises(self) -> None:
        with temporary_directory() as root, pytest.raises(CleanError):
            run_clean(root)

    def test_cli_clean_prints_removed_paths(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            _touch(repo / "site" / "index.html")
            _touch(repo / ".codoc-engine.yml")
            with patch("codoc.commands.clean.stop_serve", return_value=True):
                out, err, code = _run_in(repo, ["clean"])
        assert code is None
        assert err == ""
        assert "stopped\tserve\n" in out
        assert ".codoc-engine.yml\n" in out
        assert "site\n" in out
