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
from codoc.commands.lint import LintError, run_lint
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


def _patch_vale_run(completed: MagicMock):
    real_run = subprocess.run

    def run(cmd, *args, **kwargs):
        if cmd and cmd[0] == "vale":
            return completed
        return real_run(cmd, *args, **kwargs)

    return patch("codoc.commands.lint.subprocess.run", side_effect=run)


class LintCmdTests:
    def test_lint_invokes_vale_with_generated_config(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            completed = MagicMock(returncode=0)
            with (
                patch("codoc.commands.lint.shutil.which", return_value="/bin/vale"),
                _patch_vale_run(completed) as run,
            ):
                result = run_lint(repo)
            vale_calls = [
                call
                for call in run.call_args_list
                if call.args and call.args[0] and call.args[0][0] == "vale"
            ]
            assert len(vale_calls) == 1
            assert vale_calls[0].args[0] == [
                "vale",
                "--config",
                ".codoc/generated/.vale.ini",
                "docs",
            ]
            assert os.path.samefile(vale_calls[0].kwargs["cwd"], repo)
            assert not result.skipped
            assert (repo / ".codoc" / "generated" / ".vale.ini").is_file()

    def test_lint_missing_binary(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            with (
                patch("codoc.commands.lint.shutil.which", return_value=None),
                pytest.raises(LintError) as caught,
            ):
                run_lint(repo)
            assert "vale not found on PATH" in str(caught.value)

    def test_lint_disabled_skips_vale(self) -> None:
        with _git_repo() as repo:
            (repo / "codoc.yaml").write_text(
                "vale:\n  enabled: false\n",
                encoding="utf-8",
            )
            with patch("codoc.commands.lint.shutil.which") as which:
                result = run_lint(repo)
            which.assert_not_called()
            assert result.skipped

    def test_lint_vale_failure_raises(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            completed = MagicMock(returncode=1)
            with (
                patch("codoc.commands.lint.shutil.which", return_value="/bin/vale"),
                _patch_vale_run(completed),
                pytest.raises(LintError) as caught,
            ):
                run_lint(repo)
            assert "vale failed with exit 1" in str(caught.value)

    def test_cli_lint_prints_docs_dir(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            completed = MagicMock(returncode=0)
            with (
                patch("codoc.commands.lint.shutil.which", return_value="/bin/vale"),
                _patch_vale_run(completed),
            ):
                out, err, code = _run_in(repo, ["lint"])
        assert code is None
        assert out == "docs\n"
        assert err == ""

    def test_cli_lint_disabled_message(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            (repo / "codoc.yaml").write_text(
                "vale:\n  enabled: false\n",
                encoding="utf-8",
            )
            out, err, code = _run_in(repo, ["lint"])
        assert code is None
        assert out == ""
        assert "codoc lint: vale disabled" in err

    def test_cli_lint_missing_binary_exits_1(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            with patch("codoc.commands.lint.shutil.which", return_value=None):
                out, err, code = _run_in(repo, ["lint"])
        assert code == 1
        assert out == ""
        assert "vale not found on PATH" in err

    @pytest.mark.skipif(not shutil.which("vale"), reason="vale not on PATH")
    def test_live_vale_lint(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            result = run_lint(repo)
            assert not result.skipped
