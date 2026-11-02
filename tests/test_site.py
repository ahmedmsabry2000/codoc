import io
import os
import shutil
import subprocess
import unittest
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

from tests.tmpdir import temporary_directory
from unittest.mock import MagicMock, patch

import codoc.cli as cli
from codoc.init_cmd import run_init
from codoc.site_cmd import SiteError, run_build, run_serve, stop_serve


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

    return patch("codoc.site_cmd.subprocess.run", side_effect=run)


def _patch_engine_popen(proc: MagicMock):
    real_popen = subprocess.Popen

    def popen(cmd, *args, **kwargs):
        if cmd and cmd[0] in {"zensical", "mkdocs"}:
            return proc
        return real_popen(cmd, *args, **kwargs)

    return patch("codoc.site_cmd.subprocess.Popen", side_effect=popen)


class SiteCmdTests(unittest.TestCase):
    def test_build_invokes_zensical_with_generated_config(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            completed = MagicMock(returncode=0)
            with (
                patch("codoc.site_cmd.shutil.which", return_value="/bin/zensical"),
                _patch_engine_run(completed) as run,
            ):
                result = run_build(repo)
            engine_calls = [
                call
                for call in run.call_args_list
                if call.args and call.args[0] and call.args[0][0] == "zensical"
            ]
            self.assertEqual(len(engine_calls), 1)
            self.assertEqual(
                engine_calls[0].args[0],
                ["zensical", "build", "-f", "mkdocs.yml"],
            )
            self.assertTrue(os.path.samefile(engine_calls[0].kwargs["cwd"], repo))
            self.assertEqual(result.site_dir.as_posix(), "site")
            self.assertTrue((repo / "mkdocs.yml").is_file())

    def test_build_missing_binary(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            with patch("codoc.site_cmd.shutil.which", return_value=None):
                with self.assertRaises(SiteError) as caught:
                    run_build(repo)
            self.assertIn("zensical not found on PATH", str(caught.exception))

    def test_build_uses_mkdocs_when_configured(self) -> None:
        with _git_repo() as repo:
            (repo / "codoc.yaml").write_text(
                "engine:\n  name: mkdocs\n",
                encoding="utf-8",
            )
            completed = MagicMock(returncode=0)
            with (
                patch("codoc.site_cmd.shutil.which", return_value="/bin/mkdocs"),
                _patch_engine_run(completed) as run,
            ):
                run_build(repo)
            engine_calls = [
                call
                for call in run.call_args_list
                if call.args and call.args[0] and call.args[0][0] == "mkdocs"
            ]
            self.assertEqual(len(engine_calls), 1)
            self.assertEqual(
                engine_calls[0].args[0],
                ["mkdocs", "build", "-f", "mkdocs.yml"],
            )

    def test_serve_writes_pidfile_and_log(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            proc = MagicMock()
            proc.pid = 4242
            proc.poll.return_value = None
            with (
                patch("codoc.site_cmd.shutil.which", return_value="/bin/zensical"),
                _patch_engine_popen(proc) as popen,
            ):
                result = run_serve(repo)
            popen.assert_called()
            engine_calls = [
                call
                for call in popen.call_args_list
                if call.args and call.args[0] and call.args[0][0] == "zensical"
            ]
            self.assertEqual(len(engine_calls), 1)
            self.assertEqual(
                engine_calls[0].args[0],
                ["zensical", "serve", "-f", "mkdocs.yml"],
            )
            self.assertTrue(os.path.samefile(engine_calls[0].kwargs["cwd"], repo))
            self.assertTrue(engine_calls[0].kwargs["start_new_session"])
            self.assertEqual(result.pid, 4242)
            self.assertEqual((repo / result.pid_file).read_text(encoding="utf-8"), "4242\n")
            self.assertTrue((repo / result.log_file).is_file())

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
                patch("codoc.site_cmd.shutil.which", return_value="/bin/zensical"),
                patch("codoc.site_cmd._terminate", return_value=True) as terminate,
                _patch_engine_popen(proc),
            ):
                result = run_serve(repo)
            terminate.assert_called_once_with(111)
            self.assertEqual(result.pid, 222)
            self.assertEqual(pid_path.read_text(encoding="utf-8"), "222\n")

    def test_cli_build_prints_site_dir(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            completed = MagicMock(returncode=0)
            with (
                patch("codoc.site_cmd.shutil.which", return_value="/bin/zensical"),
                _patch_engine_run(completed),
            ):
                out, err, code = _run_in(repo, ["build"])
        self.assertEqual(code, None)
        self.assertEqual(out, "site\n")
        self.assertEqual(err, "")

    def test_cli_build_missing_binary_exits_1(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            with patch("codoc.site_cmd.shutil.which", return_value=None):
                out, err, code = _run_in(repo, ["build"])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("zensical not found on PATH", err)

    def test_cli_serve_prints_pid_and_url(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            proc = MagicMock()
            proc.pid = 99
            proc.poll.return_value = None
            with (
                patch("codoc.site_cmd.shutil.which", return_value="/bin/zensical"),
                _patch_engine_popen(proc),
            ):
                out, err, code = _run_in(repo, ["serve"])
        self.assertEqual(code, None)
        self.assertEqual(err, "")
        self.assertIn("pid\t99\n", out)
        self.assertIn("url\thttp://localhost:8000/\n", out)
        self.assertIn("log\t.codoc/logs/serve.log\n", out)
        self.assertIn("pidfile\t.codoc/serve.pid\n", out)

    def test_stop_serve_without_pidfile(self) -> None:
        with _git_repo() as repo:
            self.assertFalse(stop_serve(repo))

    @unittest.skipUnless(shutil.which("zensical"), "zensical not on PATH")
    def test_live_zensical_build(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            result = run_build(repo)
            self.assertTrue((repo / result.site_dir / "index.html").is_file())
            stop_serve(repo)


if __name__ == "__main__":
    unittest.main()
