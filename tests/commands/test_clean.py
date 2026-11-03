import os
from pathlib import Path
from unittest.mock import patch

import pytest

from codoc.commands.clean import CleanError, run_clean
from codoc.commands.init import run_init
from tests.support.cli import run_cli
from tests.support.fs import touch


class CleanCmdTests:
    def test_clean_removes_generated_keeps_scripts(self, git_repo: Path) -> None:
        run_init(git_repo)
        touch(git_repo / "site" / "index.html")
        touch(git_repo / ".codoc-engine.yml", "# Generated\n")
        touch(git_repo / "mkdocs.yml", "# legacy\n")
        touch(git_repo / ".codoc" / "generated" / ".vale.ini")
        touch(git_repo / ".codoc" / "cache" / "x")
        touch(git_repo / ".codoc" / "logs" / "serve.log")
        touch(git_repo / ".codoc" / "scripts" / "keep.py", "print(1)\n")
        with patch("codoc.commands.clean.stop_serve", return_value=False):
            result = run_clean(git_repo)
        assert not result.stopped_serve
        assert not (git_repo / "site").exists()
        assert not (git_repo / ".codoc-engine.yml").exists()
        assert (git_repo / "mkdocs.yml").is_file()
        assert not (git_repo / ".codoc" / "generated").exists()
        assert not (git_repo / ".codoc" / "cache").exists()
        assert not (git_repo / ".codoc" / "logs").exists()
        assert (git_repo / ".codoc" / "scripts" / "keep.py").is_file()
        assert (git_repo / ".codoc" / "scripts" / ".gitkeep").is_file()
        assert Path("site") in result.removed
        assert Path(".codoc-engine.yml") in result.removed
        assert Path("mkdocs.yml") not in result.removed

    def test_clean_uses_configured_site_dir(self, git_repo: Path) -> None:
        (git_repo / "codoc.yaml").write_text(
            "engine:\n  site_dir: out/html\n",
            encoding="utf-8",
        )
        touch(git_repo / "out" / "html" / "index.html")
        with patch("codoc.commands.clean.stop_serve", return_value=False):
            result = run_clean(git_repo)
        assert not (git_repo / "out" / "html").exists()
        assert Path("out/html") in result.removed

    def test_clean_stops_serve(self, git_repo: Path) -> None:
        run_init(git_repo)
        with patch("codoc.commands.clean.stop_serve", return_value=True) as stop:
            result = run_clean(git_repo)
        stop.assert_called_once()
        assert os.path.samefile(stop.call_args.args[0], git_repo)
        assert result.stopped_serve

    def test_clean_outside_repo_raises(self, tmp_dir: Path) -> None:
        with pytest.raises(CleanError):
            run_clean(tmp_dir)

    def test_cli_clean_prints_removed_paths(self, git_repo: Path) -> None:
        run_init(git_repo)
        touch(git_repo / "site" / "index.html")
        touch(git_repo / ".codoc-engine.yml")
        with patch("codoc.commands.clean.stop_serve", return_value=True):
            out, err, code = run_cli(git_repo, ["clean"])
        assert code is None
        assert err == ""
        assert "stopped\tserve\n" in out
        assert ".codoc-engine.yml\n" in out
        assert "site\n" in out
