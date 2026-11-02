import io
import os
import subprocess
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import codoc.cli as cli
from codoc.clean_cmd import CleanError, run_clean
from codoc.init_cmd import run_init


@contextmanager
def _git_repo() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
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


class CleanCmdTests(unittest.TestCase):
    def test_clean_removes_generated_keeps_scripts(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            _touch(repo / "site" / "index.html")
            _touch(repo / "mkdocs.yml", "# Generated\n")
            _touch(repo / ".codoc" / "generated" / ".vale.ini")
            _touch(repo / ".codoc" / "cache" / "x")
            _touch(repo / ".codoc" / "logs" / "serve.log")
            _touch(repo / ".codoc" / "scripts" / "keep.py", "print(1)\n")
            with patch("codoc.clean_cmd.stop_serve", return_value=False):
                result = run_clean(repo)
            self.assertFalse(result.stopped_serve)
            self.assertFalse((repo / "site").exists())
            self.assertFalse((repo / "mkdocs.yml").exists())
            self.assertFalse((repo / ".codoc" / "generated").exists())
            self.assertFalse((repo / ".codoc" / "cache").exists())
            self.assertFalse((repo / ".codoc" / "logs").exists())
            self.assertTrue((repo / ".codoc" / "scripts" / "keep.py").is_file())
            self.assertTrue((repo / ".codoc" / "scripts" / ".gitkeep").is_file())
            self.assertIn(Path("site"), result.removed)
            self.assertIn(Path("mkdocs.yml"), result.removed)

    def test_clean_uses_configured_site_dir(self) -> None:
        with _git_repo() as repo:
            (repo / "codoc.yaml").write_text(
                "engine:\n  site_dir: out/html\n",
                encoding="utf-8",
            )
            _touch(repo / "out" / "html" / "index.html")
            with patch("codoc.clean_cmd.stop_serve", return_value=False):
                result = run_clean(repo)
            self.assertFalse((repo / "out" / "html").exists())
            self.assertIn(Path("out/html"), result.removed)

    def test_clean_stops_serve(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            with patch("codoc.clean_cmd.stop_serve", return_value=True) as stop:
                result = run_clean(repo)
            stop.assert_called_once()
            self.assertTrue(os.path.samefile(stop.call_args.args[0], repo))
            self.assertTrue(result.stopped_serve)

    def test_clean_outside_repo_raises(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(CleanError):
                run_clean(Path(raw))

    def test_cli_clean_prints_removed_paths(self) -> None:
        with _git_repo() as repo:
            run_init(repo)
            _touch(repo / "site" / "index.html")
            _touch(repo / "mkdocs.yml")
            with patch("codoc.clean_cmd.stop_serve", return_value=True):
                out, err, code = _run_in(repo, ["clean"])
        self.assertEqual(code, None)
        self.assertEqual(err, "")
        self.assertIn("stopped\tserve\n", out)
        self.assertIn("mkdocs.yml\n", out)
        self.assertIn("site\n", out)


if __name__ == "__main__":
    unittest.main()
