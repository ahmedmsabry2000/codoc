import os
import shutil
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from codoc.commands.init import run_init
from codoc.commands.lint import LintError, run_lint
from tests.support.cli import run_cli
from tests.support.git import git_repository


def _patch_vale_run(completed: MagicMock):
    real_run = subprocess.run

    def run(cmd, *args, **kwargs):
        if cmd and cmd[0] == "vale":
            return completed
        return real_run(cmd, *args, **kwargs)

    return patch("codoc.commands.lint.subprocess.run", side_effect=run)


class LintCmdTests:
    def test_lint_invokes_vale_with_generated_config(self) -> None:
        with git_repository() as repo:
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
        with git_repository() as repo:
            run_init(repo)
            with (
                patch("codoc.commands.lint.shutil.which", return_value=None),
                pytest.raises(LintError) as caught,
            ):
                run_lint(repo)
            assert "vale not found on PATH" in str(caught.value)

    def test_lint_disabled_skips_vale(self) -> None:
        with git_repository() as repo:
            (repo / "codoc.yaml").write_text(
                "vale:\n  enabled: false\n",
                encoding="utf-8",
            )
            with patch("codoc.commands.lint.shutil.which") as which:
                result = run_lint(repo)
            which.assert_not_called()
            assert result.skipped

    def test_lint_vale_failure_raises(self) -> None:
        with git_repository() as repo:
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
        with git_repository() as repo:
            run_init(repo)
            completed = MagicMock(returncode=0)
            with (
                patch("codoc.commands.lint.shutil.which", return_value="/bin/vale"),
                _patch_vale_run(completed),
            ):
                out, err, code = run_cli(repo, ["lint"])
        assert code is None
        assert out == "docs\n"
        # init docs may yield zero learned terms; stderr stays quiet then.
        assert "vale failed" not in err

    def test_lint_grows_learned_vocab_from_docs(self) -> None:
        with git_repository() as repo:
            run_init(repo)
            (repo / "docs" / "guide.md").write_text(
                "Use FooBar with `parse_spec`.\nFooBar is required.\n",
                encoding="utf-8",
            )
            completed = MagicMock(returncode=0)
            with (
                patch("codoc.commands.lint.shutil.which", return_value="/bin/vale"),
                _patch_vale_run(completed),
            ):
                result = run_lint(repo)
            learned = (repo / ".codoc" / "vocab" / "learned.txt").read_text(encoding="utf-8")
            assert "FooBar" in learned
            assert "parse_spec" in learned
            accept = (
                repo / ".codoc" / "generated" / "styles" / "Vocab" / "Codoc" / "accept.txt"
            ).read_text(encoding="utf-8")
            assert "FooBar" in accept
            assert "parse_spec" in accept
            assert result.learned_added
            yaml_text = (repo / "codoc.yaml").read_text(encoding="utf-8")
            assert "FooBar" not in yaml_text

    def test_cli_lint_no_learn_skips_harvest(self) -> None:
        with git_repository() as repo:
            run_init(repo)
            (repo / "docs" / "guide.md").write_text(
                "BrandNewTool BrandNewTool appears twice.\n",
                encoding="utf-8",
            )
            completed = MagicMock(returncode=0)
            with (
                patch("codoc.commands.lint.shutil.which", return_value="/bin/vale"),
                _patch_vale_run(completed),
            ):
                out, err, code = run_cli(repo, ["lint", "--no-learn"])
            assert code is None
            assert out == "docs\n"
            assert "learned" not in err
            assert not (repo / ".codoc" / "vocab" / "learned.txt").exists()
            accept = (
                repo / ".codoc" / "generated" / "styles" / "Vocab" / "Codoc" / "accept.txt"
            ).read_text(encoding="utf-8")
            assert "BrandNewTool" not in accept

    def test_cli_lint_disabled_message(self) -> None:
        with git_repository() as repo:
            run_init(repo)
            (repo / "codoc.yaml").write_text(
                "vale:\n  enabled: false\n",
                encoding="utf-8",
            )
            out, err, code = run_cli(repo, ["lint"])
        assert code is None
        assert out == ""
        assert "codoc lint: vale disabled" in err

    def test_cli_lint_missing_binary_exits_1(self) -> None:
        with git_repository() as repo:
            run_init(repo)
            with patch("codoc.commands.lint.shutil.which", return_value=None):
                out, err, code = run_cli(repo, ["lint"])
        assert code == 1
        assert out == ""
        assert "vale not found on PATH" in err

    @pytest.mark.skipif(not shutil.which("vale"), reason="vale not on PATH")
    def test_live_vale_lint(self) -> None:
        with git_repository() as repo:
            run_init(repo)
            result = run_lint(repo)
            assert not result.skipped
