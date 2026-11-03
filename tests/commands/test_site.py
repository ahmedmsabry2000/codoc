import io
import os
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import codoc.cli as cli
from codoc.commands.init import run_init
from codoc.commands.site import SiteError, run_build, run_serve, stop_serve
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


def _patch_engine_run(completed: MagicMock):
    real_run = subprocess.run

    def run(cmd, *args, **kwargs):
        if cmd and cmd[0] in {"zensical", "mkdocs"}:
            return completed
        return real_run(cmd, *args, **kwargs)

    return patch("codoc.commands.site.subprocess.run", side_effect=run)


def _patch_engine_popen(proc: MagicMock):
    real_popen = subprocess.Popen

    def popen(cmd, *args, **kwargs):
        if cmd and cmd[0] in {"zensical", "mkdocs"}:
            return proc
        return real_popen(cmd, *args, **kwargs)

    return patch("codoc.commands.site.subprocess.Popen", side_effect=popen)


class SiteCmdTests:
    def test_build_invokes_zensical_with_generated_config(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            completed = MagicMock(returncode=0)
            with (
                patch("codoc.commands.site.shutil.which", return_value="/bin/zensical"),
                _patch_engine_run(completed) as run,
            ):
                result = run_build(repo)
            engine_calls = [
                call
                for call in run.call_args_list
                if call.args and call.args[0] and call.args[0][0] == "zensical"
            ]
            assert len(engine_calls) == 1
            assert engine_calls[0].args[0] == ["zensical", "build", "-f", "mkdocs.yml"]
            assert os.path.samefile(engine_calls[0].kwargs["cwd"], repo)
            assert result.site_dir.as_posix() == "site"
            assert (repo / "mkdocs.yml").is_file()

    def test_build_missing_binary(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            with (
                patch("codoc.commands.site.shutil.which", return_value=None),
                pytest.raises(SiteError) as caught,
            ):
                run_build(repo)
            assert "zensical not found on PATH" in str(caught.value)

    def test_build_uses_mkdocs_when_configured(self) -> None:
        with _git_repo() as repo:
            (repo / "codoc.yaml").write_text(
                "engine:\n  name: mkdocs\n",
                encoding="utf-8",
            )
            completed = MagicMock(returncode=0)
            with (
                patch("codoc.commands.site.shutil.which", return_value="/bin/mkdocs"),
                _patch_engine_run(completed) as run,
            ):
                run_build(repo)
            engine_calls = [
                call
                for call in run.call_args_list
                if call.args and call.args[0] and call.args[0][0] == "mkdocs"
            ]
            assert len(engine_calls) == 1
            assert engine_calls[0].args[0] == ["mkdocs", "build", "-f", "mkdocs.yml"]

    def test_serve_writes_pidfile_and_log(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            proc = MagicMock()
            proc.pid = 4242
            proc.poll.return_value = None
            with (
                patch("codoc.commands.site.shutil.which", return_value="/bin/zensical"),
                _patch_engine_popen(proc) as popen,
            ):
                result = run_serve(repo)
            popen.assert_called()
            engine_calls = [
                call
                for call in popen.call_args_list
                if call.args and call.args[0] and call.args[0][0] == "zensical"
            ]
            assert len(engine_calls) == 1
            assert engine_calls[0].args[0] == ["zensical", "serve", "-f", "mkdocs.yml"]
            assert os.path.samefile(engine_calls[0].kwargs["cwd"], repo)
            assert engine_calls[0].kwargs["start_new_session"]
            assert result.pid == 4242
            assert (repo / result.pid_file).read_text(encoding="utf-8") == "4242\n"
            assert (repo / result.log_file).is_file()

    def test_serve_replaces_existing_pid(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            pid_path = repo / ".codoc" / "serve.pid"
            pid_path.parent.mkdir(parents=True, exist_ok=True)
            pid_path.write_text("111\n", encoding="utf-8")
            proc = MagicMock()
            proc.pid = 222
            proc.poll.return_value = None
            with (
                patch("codoc.commands.site.shutil.which", return_value="/bin/zensical"),
                patch("codoc.commands.site._terminate", return_value=True) as terminate,
                _patch_engine_popen(proc),
            ):
                result = run_serve(repo)
            terminate.assert_called_once_with(111)
            assert result.pid == 222
            assert pid_path.read_text(encoding="utf-8") == "222\n"

    def test_cli_build_prints_site_dir(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            completed = MagicMock(returncode=0)
            with (
                patch("codoc.commands.site.shutil.which", return_value="/bin/zensical"),
                _patch_engine_run(completed),
            ):
                out, err, code = _run_in(repo, ["build"])
        assert code is None
        assert out == "site\n"
        assert err == ""

    def test_cli_build_missing_binary_exits_1(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            with patch("codoc.commands.site.shutil.which", return_value=None):
                out, err, code = _run_in(repo, ["build"])
        assert code == 1
        assert out == ""
        assert "zensical not found on PATH" in err

    def test_cli_serve_prints_pid_and_url(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            proc = MagicMock()
            proc.pid = 99
            proc.poll.return_value = None
            with (
                patch("codoc.commands.site.shutil.which", return_value="/bin/zensical"),
                _patch_engine_popen(proc),
            ):
                out, err, code = _run_in(repo, ["serve"])
        assert code is None
        assert err == ""
        assert "pid\t99\n" in out
        assert "url\thttp://localhost:8000/\n" in out
        assert "log\t.codoc/logs/serve.log\n" in out
        assert "pidfile\t.codoc/serve.pid\n" in out

    def test_stop_serve_without_pidfile(self) -> None:
        with _git_repo() as repo:
            assert not stop_serve(repo)

    @pytest.mark.skipif(not shutil.which("zensical"), reason="zensical not on PATH")
    def test_live_zensical_build(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            result = run_build(repo)
            assert (repo / result.site_dir / "index.html").is_file()
            stop_serve(repo)
