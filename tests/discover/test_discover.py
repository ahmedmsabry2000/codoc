import os
from pathlib import Path
from unittest.mock import patch

import pytest

from codoc.config import ConfigError
from codoc.discover import (
    DEFAULT_SKIP,
    DiscoverError,
    SpecUnit,
    child_scopes,
    discover,
    git_root,
)
from tests.support.fs import write_text
from tests.support.git import git_repository


def _product_tree(repo: Path) -> None:
    write_text(repo / "codoc.yaml")
    write_text(repo / "codoc.spec.yaml")
    write_text(repo / "src" / "my_project" / "codoc.spec.yaml")
    write_text(repo / "src" / "my_project" / "api" / "codoc.spec.yaml")
    write_text(repo / "src" / "my_project" / "cli" / "codoc.spec.yaml")


class DiscoverTests:
    def test_missing_git_repo(self, tmp_dir: Path) -> None:
        with pytest.raises(DiscoverError) as caught:
            discover(tmp_dir)
        assert str(caught.value) == f"not a git repository at {tmp_dir}"

    def test_git_not_on_path(self, tmp_dir: Path) -> None:
        with (
            patch.dict(os.environ, {"PATH": str(tmp_dir)}),
            pytest.raises(DiscoverError) as caught,
        ):
            discover(tmp_dir)
        assert str(caught.value) == "git not on PATH"

    def test_missing_codoc_yaml(self) -> None:
        with git_repository() as repo:
            with pytest.raises(DiscoverError) as caught:
                discover(repo)
            root = git_root(repo)
        assert str(caught.value) == f"codoc.yaml not found at {root / 'codoc.yaml'}"

    def test_codoc_yaml_directory_is_not_a_file(self) -> None:
        with git_repository() as repo:
            (repo / "codoc.yaml").mkdir()
            with pytest.raises(DiscoverError) as caught:
                discover(repo)
            root = git_root(repo)
        assert str(caught.value) == f"codoc.yaml not found at {root / 'codoc.yaml'}"

    def test_lists_product_tree_and_nearest_children(self) -> None:
        with git_repository() as repo:
            _product_tree(repo)
            units = discover(repo)
        assert tuple((unit.spec_path.as_posix(), unit.scope_dir.as_posix()) for unit in units) == (
            ("codoc.spec.yaml", "."),
            ("src/my_project/api/codoc.spec.yaml", "src/my_project/api"),
            ("src/my_project/cli/codoc.spec.yaml", "src/my_project/cli"),
            ("src/my_project/codoc.spec.yaml", "src/my_project"),
        )
        assert child_scopes(units) == {
            Path("."): (Path("src/my_project"),),
            Path("src/my_project/api"): (),
            Path("src/my_project/cli"): (),
            Path("src/my_project"): (
                Path("src/my_project/api"),
                Path("src/my_project/cli"),
            ),
        }

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
        assert found == {
            Path("src/pkg"): (Path("src/pkg/api"),),
            Path("src/pkg/api"): (Path("src/pkg/api/handlers"),),
            Path("src/pkg/api/handlers"): (),
        }
        assert list(found) == [unit.scope_dir for unit in units]

    def test_child_scopes_ignores_prefix_siblings(self) -> None:
        units = (
            SpecUnit(Path("src/pkg/codoc.spec.yaml"), Path("src/pkg")),
            SpecUnit(Path("src/pkg2/codoc.spec.yaml"), Path("src/pkg2")),
        )
        assert child_scopes(units) == {Path("src/pkg"): (), Path("src/pkg2"): ()}

    def test_child_scopes_rejects_duplicate_scope(self) -> None:
        unit = SpecUnit(Path("src/pkg/codoc.spec.yaml"), Path("src/pkg"))
        with pytest.raises(ValueError) as caught:
            child_scopes((unit, unit))
        assert str(caught.value) == "duplicate scope_dir"

    def test_skip_dirs_hide_specs(self) -> None:
        with git_repository() as repo:
            write_text(repo / "codoc.yaml")
            write_text(repo / "keep" / "codoc.spec.yaml")
            write_text(repo / "src" / "pkg" / "codoc.spec.yaml")
            for name in DEFAULT_SKIP:
                write_text(repo / name / "codoc.spec.yaml")
            write_text(repo / "src" / "pkg" / "__pycache__" / "codoc.spec.yaml")
            write_text(repo / "nested" / "site" / "codoc.spec.yaml")
            units = discover(repo)
        assert tuple(unit.spec_path.as_posix() for unit in units) == (
            "keep/codoc.spec.yaml",
            "src/pkg/codoc.spec.yaml",
        )

    def test_ignore_unions_with_default_skip(self) -> None:
        before = set(DEFAULT_SKIP)
        with git_repository() as repo:
            write_text(repo / "codoc.yaml", "ignore:\n  - node_modules\n")
            write_text(repo / "keep" / "codoc.spec.yaml")
            write_text(repo / "node_modules" / "codoc.spec.yaml")
            write_text(repo / "src" / "pkg" / "node_modules" / "codoc.spec.yaml")
            write_text(repo / ".git" / "codoc.spec.yaml")
            write_text(repo / "src" / "distfiles" / "codoc.spec.yaml")
            units = discover(repo)
        assert set(DEFAULT_SKIP) == before
        assert "node_modules" not in DEFAULT_SKIP
        assert tuple(unit.spec_path.as_posix() for unit in units) == (
            "keep/codoc.spec.yaml",
            "src/distfiles/codoc.spec.yaml",
        )

    def test_invalid_project_file_raises_config_error(self) -> None:
        with git_repository() as repo:
            write_text(repo / "codoc.yaml", "serve: true\n")
            write_text(repo / "keep" / "codoc.spec.yaml")
            with pytest.raises(ConfigError) as caught:
                discover(repo)
            root = git_root(repo)
        assert str(caught.value) == f"{root / 'codoc.yaml'}: document: unknown field 'serve'"

    def test_exact_spec_filename(self) -> None:
        with git_repository() as repo:
            write_text(repo / "codoc.yaml")
            write_text(repo / "real" / "codoc.spec.yaml")
            write_text(repo / "real" / "codoc.spec.yml")
            write_text(repo / "other" / "Codoc.spec.yaml")
            units = discover(repo)
        assert tuple(unit.spec_path.as_posix() for unit in units) == ("real/codoc.spec.yaml",)

    def test_discover_from_subdirectory_lists_the_repo(self) -> None:
        with git_repository() as repo:
            _product_tree(repo)
            from_root = discover(repo)
            from_sub = discover(repo / "src")
        assert from_sub == from_root
        assert len(from_sub) == 4

    def test_second_discover_matches_the_first(self) -> None:
        with git_repository() as repo:
            _product_tree(repo)
            assert discover(repo) == discover(repo)

    def test_unreadable_directory(self) -> None:
        if os.geteuid() == 0:
            pytest.skip("root can read a mode 0 directory")
        with git_repository() as repo:
            write_text(repo / "codoc.yaml")
            secret = repo / "secret"
            secret.mkdir()
            secret.chmod(0)
            try:
                with pytest.raises(DiscoverError) as caught:
                    discover(repo)
                root = git_root(repo)
            finally:
                secret.chmod(0o755)
        assert f"cannot read {root}, " in str(caught.value)

    def test_spec_unit_rejects_illegal_paths(self) -> None:
        root = SpecUnit(Path("codoc.spec.yaml"), Path("."))
        assert root.scope_dir.as_posix() == "."
        SpecUnit(Path("src/pkg/codoc.spec.yaml"), Path("src/pkg"))
        with pytest.raises(ValueError):
            SpecUnit(Path("/tmp/codoc.spec.yaml"), Path("."))
        with pytest.raises(ValueError):
            SpecUnit(Path("codoc.spec.yaml"), Path("/tmp"))
        with pytest.raises(ValueError):
            SpecUnit(Path("src/../codoc.spec.yaml"), Path("."))
        with pytest.raises(ValueError):
            SpecUnit(Path("src/codoc.spec.yml"), Path("src"))
        with pytest.raises(ValueError):
            SpecUnit(Path("src/pkg/codoc.spec.yaml"), Path("src"))

    def test_empty_repo_returns_no_units(self) -> None:
        with git_repository() as repo:
            write_text(repo / "codoc.yaml")
            assert discover(repo) == ()
