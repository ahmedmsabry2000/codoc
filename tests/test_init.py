import io
import os
import subprocess
import unittest
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

import codoc.cli as cli
from codoc.commands.init import InitError, run_init
from codoc.config import load_project_config
from codoc.discover import git_root
from codoc.model.spec import load_spec
from tests.tmpdir import temporary_directory


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


class InitTests(unittest.TestCase):
    def test_init_writes_loadable_project(self) -> None:
        with _git_repo("my-app") as repo:
            result = run_init(repo)
            self.assertEqual(result.spec_path.as_posix(), "src/my_app/codoc.spec.yaml")
            config = load_project_config(repo / "codoc.yaml")
            self.assertEqual(config.engine.name, "zensical")
            self.assertEqual(config.paths.scripts_dir, ".codoc/scripts")
            spec = load_spec(repo / result.spec_path)
            self.assertEqual(spec.page_count, 2)
            self.assertTrue((repo / ".codoc" / "scripts" / ".gitkeep").is_file())
            self.assertFalse((repo / "codoc.spec.yaml").exists())
            ignore = (repo / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".codoc/*", ignore)
            self.assertIn("!.codoc/scripts/", ignore)
            self.assertIn("!.codoc/scripts/**", ignore)
            self.assertIn("site/", ignore)
            self.assertIn("mkdocs.yml", ignore)
            out, err, code = _run_in(repo, ["status"])
        self.assertIn(code, (0, None))
        self.assertEqual(err, "")
        self.assertIn("src/my_app/codoc.spec.yaml\tsrc/my_app\t2", out)
        self.assertIn("registry_pages\t2", out)

    def test_second_init_refuses_without_force(self) -> None:
        with _git_repo() as repo:
            first = run_init(repo)
            before = (repo / "codoc.yaml").read_text(encoding="utf-8")
            with self.assertRaises(InitError) as caught:
                run_init(repo)
            self.assertIn("codoc.yaml exists", str(caught.exception))
            self.assertIn(first.spec_path.as_posix(), str(caught.exception))
            self.assertEqual((repo / "codoc.yaml").read_text(encoding="utf-8"), before)
            out, err, code = _run_in(repo, ["init"])
        self.assertEqual(code, 1)
        self.assertIn("codoc init: codoc.yaml exists", err)
        self.assertEqual(out, "")

    def test_force_overwrites_managed_files(self) -> None:
        with _git_repo("demo") as repo:
            run_init(repo)
            (repo / "codoc.yaml").write_text("terms: [stale]\n", encoding="utf-8")
            (repo / "docs" / "index.md").write_text("stale\n", encoding="utf-8")
            result = run_init(repo, force=True)
            config = load_project_config(repo / "codoc.yaml")
            self.assertEqual(config.terms, ())
            self.assertEqual(config.engine.name, "zensical")
            self.assertEqual(
                (repo / "docs" / "index.md").read_text(encoding="utf-8"),
                "# Documentation site\n\nPackage overview\n",
            )
            self.assertIn(Path("codoc.yaml"), result.written)

    def test_uses_single_src_package(self) -> None:
        with _git_repo("repo") as repo:
            pkg = repo / "src" / "widgets"
            pkg.mkdir(parents=True)
            (repo / "src" / "widgets.egg-info").mkdir()
            result = run_init(repo)
            self.assertEqual(result.spec_path.as_posix(), "src/widgets/codoc.spec.yaml")

    def test_two_packages_create_sanitized_repo_name(self) -> None:
        with _git_repo("cool-app") as repo:
            (repo / "src" / "one").mkdir(parents=True)
            (repo / "src" / "two").mkdir(parents=True)
            result = run_init(repo)
            self.assertEqual(result.spec_path.as_posix(), "src/cool_app/codoc.spec.yaml")
            self.assertTrue((repo / "src" / "cool_app" / "codoc.spec.yaml").is_file())

    def test_not_a_git_repo(self) -> None:
        with temporary_directory() as start:
            with self.assertRaises(InitError) as caught:
                run_init(start)
            self.assertFalse((start / ".git").exists())
            self.assertFalse((start / "codoc.yaml").exists())
        self.assertIn("not a git repository", str(caught.exception))

    def test_init_does_not_mkdir_under_cwd(self) -> None:
        # Regression: pkg.mkdir used to be cwd-relative and leaked empty dirs into src/.
        repo_src = Path(__file__).resolve().parents[1] / "src"
        before = {path.name for path in repo_src.iterdir()}
        with _git_repo("leak-probe") as repo:
            run_init(repo)
            self.assertTrue((repo / "src" / "leak_probe" / "codoc.spec.yaml").is_file())
        after = {path.name for path in repo_src.iterdir()}
        self.assertEqual(after, before)

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
        self.assertIn("!! .codoc/generated/x", status.stdout)
        self.assertIn("!! site/index.html", status.stdout)
        self.assertIn("?? .codoc/scripts/.gitkeep", status.stdout)
        self.assertIn("add '.codoc/scripts/.gitkeep'", dry.stdout)


if __name__ == "__main__":
    unittest.main()
