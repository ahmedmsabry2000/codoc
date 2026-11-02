import os
import subprocess
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from codoc.config import ConfigError
from codoc.discover import (
    DEFAULT_SKIP,
    DiscoverError,
    SpecUnit,
    child_scopes,
    discover,
    git_root,
)
from tests.support.tmpdir import temporary_directory


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


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


def _product_tree(repo: Path) -> None:
    _write(repo / "codoc.yaml")
    _write(repo / "codoc.spec.yaml")
    _write(repo / "src" / "my_project" / "codoc.spec.yaml")
    _write(repo / "src" / "my_project" / "api" / "codoc.spec.yaml")
    _write(repo / "src" / "my_project" / "cli" / "codoc.spec.yaml")


class DiscoverTests(unittest.TestCase):
    def test_missing_git_repo(self) -> None:
        with temporary_directory() as raw:
            start = Path(raw)
            with self.assertRaises(DiscoverError) as caught:
                discover(start)
        self.assertEqual(str(caught.exception), f"not a git repository at {start}")

    def test_git_not_on_path(self) -> None:
        with temporary_directory() as raw:
            start = Path(raw)
            with (
                patch.dict(os.environ, {"PATH": str(start)}),
                self.assertRaises(DiscoverError) as caught,
            ):
                discover(start)
        self.assertEqual(str(caught.exception), "git not on PATH")

    def test_missing_codoc_yaml(self) -> None:
        with _git_repo() as repo:
            with self.assertRaises(DiscoverError) as caught:
                discover(repo)
            root = git_root(repo)
        self.assertEqual(
            str(caught.exception),
            f"codoc.yaml not found at {root / 'codoc.yaml'}",
        )

    def test_codoc_yaml_directory_is_not_a_file(self) -> None:
        with _git_repo() as repo:
            (repo / "codoc.yaml").mkdir()
            with self.assertRaises(DiscoverError) as caught:
                discover(repo)
            root = git_root(repo)
        self.assertEqual(
            str(caught.exception),
            f"codoc.yaml not found at {root / 'codoc.yaml'}",
        )

    def test_lists_product_tree_and_nearest_children(self) -> None:
        with _git_repo() as repo:
            _product_tree(repo)
            units = discover(repo)
        self.assertEqual(
            tuple((unit.spec_path.as_posix(), unit.scope_dir.as_posix()) for unit in units),
            (
                ("codoc.spec.yaml", "."),
                ("src/my_project/api/codoc.spec.yaml", "src/my_project/api"),
                ("src/my_project/cli/codoc.spec.yaml", "src/my_project/cli"),
                ("src/my_project/codoc.spec.yaml", "src/my_project"),
            ),
        )
        self.assertEqual(
            child_scopes(units),
            {
                Path("."): (Path("src/my_project"),),
                Path("src/my_project/api"): (),
                Path("src/my_project/cli"): (),
                Path("src/my_project"): (
                    Path("src/my_project/api"),
                    Path("src/my_project/cli"),
                ),
            },
        )

    def test_child_scopes_nearest_descendant_only(self) -> None:
        units = (
            SpecUnit(Path("src/pkg/codoc.spec.yaml"), Path("src/pkg")),
            SpecUnit(Path("src/pkg/api/codoc.spec.yaml"), Path("src/pkg/api")),
            SpecUnit(
                Path("src/pkg/api/handlers/codoc.spec.yaml"),
                Path("src/pkg/api/handlers"),
            ),
        )
        found = child_scopes(units)
        self.assertEqual(
            found,
            {
                Path("src/pkg"): (Path("src/pkg/api"),),
                Path("src/pkg/api"): (Path("src/pkg/api/handlers"),),
                Path("src/pkg/api/handlers"): (),
            },
        )
        self.assertEqual(list(found), [unit.scope_dir for unit in units])

    def test_child_scopes_ignores_prefix_siblings(self) -> None:
        units = (
            SpecUnit(Path("src/pkg/codoc.spec.yaml"), Path("src/pkg")),
            SpecUnit(Path("src/pkg2/codoc.spec.yaml"), Path("src/pkg2")),
        )
        self.assertEqual(
            child_scopes(units),
            {Path("src/pkg"): (), Path("src/pkg2"): ()},
        )

    def test_child_scopes_rejects_duplicate_scope(self) -> None:
        unit = SpecUnit(Path("src/pkg/codoc.spec.yaml"), Path("src/pkg"))
        with self.assertRaises(ValueError) as caught:
            child_scopes((unit, unit))
        self.assertEqual(str(caught.exception), "duplicate scope_dir")

    def test_skip_dirs_hide_specs(self) -> None:
        with _git_repo() as repo:
            _write(repo / "codoc.yaml")
            _write(repo / "keep" / "codoc.spec.yaml")
            _write(repo / "src" / "pkg" / "codoc.spec.yaml")
            for name in DEFAULT_SKIP:
                _write(repo / name / "codoc.spec.yaml")
            _write(repo / "src" / "pkg" / "__pycache__" / "codoc.spec.yaml")
            _write(repo / "nested" / "site" / "codoc.spec.yaml")
            units = discover(repo)
        self.assertEqual(
            tuple(unit.spec_path.as_posix() for unit in units),
            ("keep/codoc.spec.yaml", "src/pkg/codoc.spec.yaml"),
        )

    def test_ignore_unions_with_default_skip(self) -> None:
        before = set(DEFAULT_SKIP)
        with _git_repo() as repo:
            _write(repo / "codoc.yaml", "ignore:\n  - node_modules\n")
            _write(repo / "keep" / "codoc.spec.yaml")
            _write(repo / "node_modules" / "codoc.spec.yaml")
            _write(repo / "src" / "pkg" / "node_modules" / "codoc.spec.yaml")
            _write(repo / ".git" / "codoc.spec.yaml")
            _write(repo / "src" / "distfiles" / "codoc.spec.yaml")
            units = discover(repo)
        self.assertEqual(set(DEFAULT_SKIP), before)
        self.assertNotIn("node_modules", DEFAULT_SKIP)
        self.assertEqual(
            tuple(unit.spec_path.as_posix() for unit in units),
            ("keep/codoc.spec.yaml", "src/distfiles/codoc.spec.yaml"),
        )

    def test_invalid_project_file_raises_config_error(self) -> None:
        with _git_repo() as repo:
            _write(repo / "codoc.yaml", "serve: true\n")
            _write(repo / "keep" / "codoc.spec.yaml")
            with self.assertRaises(ConfigError) as caught:
                discover(repo)
            root = git_root(repo)
        self.assertEqual(
            str(caught.exception),
            f"{root / 'codoc.yaml'}: document: unknown field 'serve'",
        )

    def test_exact_spec_filename(self) -> None:
        with _git_repo() as repo:
            _write(repo / "codoc.yaml")
            _write(repo / "real" / "codoc.spec.yaml")
            _write(repo / "real" / "codoc.spec.yml")
            _write(repo / "other" / "Codoc.spec.yaml")
            units = discover(repo)
        self.assertEqual(
            tuple(unit.spec_path.as_posix() for unit in units),
            ("real/codoc.spec.yaml",),
        )

    def test_discover_from_subdirectory_lists_the_repo(self) -> None:
        with _git_repo() as repo:
            _product_tree(repo)
            from_root = discover(repo)
            from_sub = discover(repo / "src")
        self.assertEqual(from_sub, from_root)
        self.assertEqual(len(from_sub), 4)

    def test_second_discover_matches_the_first(self) -> None:
        with _git_repo() as repo:
            _product_tree(repo)
            self.assertEqual(discover(repo), discover(repo))

    def test_unreadable_directory(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("root can read a mode 0 directory")
        with _git_repo() as repo:
            _write(repo / "codoc.yaml")
            secret = repo / "secret"
            secret.mkdir()
            secret.chmod(0)
            try:
                with self.assertRaises(DiscoverError) as caught:
                    discover(repo)
                root = git_root(repo)
            finally:
                secret.chmod(0o755)
        self.assertIn(f"cannot read {root}, ", str(caught.exception))

    def test_spec_unit_rejects_illegal_paths(self) -> None:
        root = SpecUnit(Path("codoc.spec.yaml"), Path("."))
        self.assertEqual(root.scope_dir.as_posix(), ".")
        SpecUnit(Path("src/pkg/codoc.spec.yaml"), Path("src/pkg"))
        with self.assertRaises(ValueError):
            SpecUnit(Path("/tmp/codoc.spec.yaml"), Path("."))
        with self.assertRaises(ValueError):
            SpecUnit(Path("codoc.spec.yaml"), Path("/tmp"))
        with self.assertRaises(ValueError):
            SpecUnit(Path("src/../codoc.spec.yaml"), Path("."))
        with self.assertRaises(ValueError):
            SpecUnit(Path("src/codoc.spec.yml"), Path("src"))
        with self.assertRaises(ValueError):
            SpecUnit(Path("src/pkg/codoc.spec.yaml"), Path("src"))

    def test_empty_repo_returns_no_units(self) -> None:
        with _git_repo() as repo:
            _write(repo / "codoc.yaml")
            self.assertEqual(discover(repo), ())


if __name__ == "__main__":
    unittest.main()
