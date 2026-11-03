import os
import shutil
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from codoc.commands.init import run_init
from codoc.commands.site import SiteError, run_build, run_serve, stop_serve
from tests.support.cli import run_cli
from tests.support.git import git_repository


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
        with git_repository() as repo:
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
            assert engine_calls[0].args[0] == [
                "zensical",
                "build",
                "-f",
                ".codoc-engine.yml",
            ]
            assert os.path.samefile(engine_calls[0].kwargs["cwd"], repo)
            assert result.site_dir.as_posix() == "site"
            assert (repo / ".codoc-engine.yml").is_file()

    def test_build_missing_binary(self) -> None:
        with git_repository() as repo:
            run_init(repo)
            with (
                patch("codoc.commands.site.shutil.which", return_value=None),
                patch("codoc.commands.site.sys.prefix", "/tmp/codoc-no-venv"),
                patch("codoc.commands.site.sys.executable", "/tmp/codoc-no-venv/bin/python"),
                pytest.raises(SiteError) as caught,
            ):
                run_build(repo)
            assert "zensical not found on PATH" in str(caught.value)

    def test_build_uses_mkdocs_when_configured(self) -> None:
        with git_repository() as repo:
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
            assert engine_calls[0].args[0] == [
                "mkdocs",
                "build",
                "-f",
                ".codoc-engine.yml",
            ]

    def test_serve_writes_pidfile_and_log(self) -> None:
        with git_repository() as repo:
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
            assert engine_calls[0].args[0] == [
                "zensical",
                "serve",
                "-f",
                ".codoc-engine.yml",
            ]
            assert os.path.samefile(engine_calls[0].kwargs["cwd"], repo)
            assert engine_calls[0].kwargs["start_new_session"]
            assert result.pid == 4242
            assert (repo / result.pid_file).read_text(encoding="utf-8") == "4242\n"
            assert (repo / result.log_file).is_file()

    def test_serve_replaces_existing_pid(self) -> None:
        with git_repository() as repo:
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
        with git_repository() as repo:
            run_init(repo)
            completed = MagicMock(returncode=0)
            with (
                patch("codoc.commands.site.shutil.which", return_value="/bin/zensical"),
                _patch_engine_run(completed),
            ):
                out, err, code = run_cli(repo, ["build"])
        assert code is None
        assert out == "site\n"
        assert err == ""

    def test_cli_build_missing_binary_exits_1(self) -> None:
        with git_repository() as repo:
            run_init(repo)
            with (
                patch("codoc.commands.site.shutil.which", return_value=None),
                patch("codoc.commands.site.sys.prefix", "/tmp/codoc-no-venv"),
                patch("codoc.commands.site.sys.executable", "/tmp/codoc-no-venv/bin/python"),
            ):
                out, err, code = run_cli(repo, ["build"])
        assert code == 1
        assert out == ""
        assert "zensical not found on PATH" in err

    def test_cli_serve_prints_pid_and_url(self) -> None:
        with git_repository() as repo:
            run_init(repo)
            proc = MagicMock()
            proc.pid = 99
            proc.poll.return_value = None
            with (
                patch("codoc.commands.site.shutil.which", return_value="/bin/zensical"),
                _patch_engine_popen(proc),
            ):
                out, err, code = run_cli(repo, ["serve"])
        assert code is None
        assert err == ""
        assert "pid\t99\n" in out
        assert "url\thttp://localhost:8000/\n" in out
        assert "log\t.codoc/logs/serve.log\n" in out
        assert "pidfile\t.codoc/serve.pid\n" in out

    def test_stop_serve_without_pidfile(self) -> None:
        with git_repository() as repo:
            assert not stop_serve(repo)

    @pytest.mark.skipif(not shutil.which("zensical"), reason="zensical not on PATH")
    def test_live_zensical_build(self) -> None:
        with git_repository() as repo:
            run_init(repo)
            result = run_build(repo)
            assert (repo / result.site_dir / "index.html").is_file()
            stop_serve(repo)
