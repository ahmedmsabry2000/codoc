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
from codoc.lint_cmd import LintError, run_lint


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


def _patch_vale_run(completed: MagicMock):
    real_run = subprocess.run

    def run(cmd, *args, **kwargs):
        if cmd and cmd[0] == "vale":
            return completed
        return real_run(cmd, *args, **kwargs)

    return patch("codoc.lint_cmd.subprocess.run", side_effect=run)


class LintCmdTests(unittest.TestCase):
    def test_lint_invokes_vale_with_generated_config(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            completed = MagicMock(returncode=0)
            with (
                patch("codoc.lint_cmd.shutil.which", return_value="/bin/vale"),
                _patch_vale_run(completed) as run,
            ):
                result = run_lint(repo)
            vale_calls = [
                call
                for call in run.call_args_list
                if call.args and call.args[0] and call.args[0][0] == "vale"
            ]
            self.assertEqual(len(vale_calls), 1)
            self.assertEqual(
                vale_calls[0].args[0],
                ["vale", "--config", ".codoc/generated/.vale.ini", "docs"],
            )
            self.assertTrue(os.path.samefile(vale_calls[0].kwargs["cwd"], repo))
            self.assertFalse(result.skipped)
            self.assertTrue((repo / ".codoc" / "generated" / ".vale.ini").is_file())

    def test_lint_missing_binary(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            with patch("codoc.lint_cmd.shutil.which", return_value=None):
                with self.assertRaises(LintError) as caught:
                    run_lint(repo)
            self.assertIn("vale not found on PATH", str(caught.exception))

    def test_lint_disabled_skips_vale(self) -> None:
        with _git_repo() as repo:
            (repo / "codoc.yaml").write_text(
                "vale:\n  enabled: false\n",
                encoding="utf-8",
            )
            with patch("codoc.lint_cmd.shutil.which") as which:
                result = run_lint(repo)
            which.assert_not_called()
            self.assertTrue(result.skipped)

    def test_lint_vale_failure_raises(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            completed = MagicMock(returncode=1)
            with (
                patch("codoc.lint_cmd.shutil.which", return_value="/bin/vale"),
                _patch_vale_run(completed),
            ):
                with self.assertRaises(LintError) as caught:
                    run_lint(repo)
            self.assertIn("vale failed with exit 1", str(caught.exception))

    def test_cli_lint_prints_docs_dir(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            completed = MagicMock(returncode=0)
            with (
                patch("codoc.lint_cmd.shutil.which", return_value="/bin/vale"),
                _patch_vale_run(completed),
            ):
                out, err, code = _run_in(repo, ["lint"])
        self.assertEqual(code, None)
        self.assertEqual(out, "docs\n")
        self.assertEqual(err, "")

    def test_cli_lint_disabled_message(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            (repo / "codoc.yaml").write_text(
                "vale:\n  enabled: false\n",
                encoding="utf-8",
            )
            out, err, code = _run_in(repo, ["lint"])
        self.assertEqual(code, None)
        self.assertEqual(out, "")
        self.assertIn("codoc lint: vale disabled", err)

    def test_cli_lint_missing_binary_exits_1(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            with patch("codoc.lint_cmd.shutil.which", return_value=None):
                out, err, code = _run_in(repo, ["lint"])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("vale not found on PATH", err)

    @unittest.skipUnless(shutil.which("vale"), "vale not on PATH")
    def test_live_vale_lint(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            result = run_lint(repo)
            self.assertFalse(result.skipped)


if __name__ == "__main__":
    unittest.main()
