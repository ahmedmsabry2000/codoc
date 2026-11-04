"""Nested coverage exclude behavior."""

from pathlib import Path

from codoc.coverage import expand_coverage_paths
from tests.support.fs import write_text


class CoverageExcludeTests:
    def test_parent_glob_skips_child_scope_files(self, tmp_dir: Path) -> None:
        write_text(tmp_dir / "src" / "pkg" / "a.py", "a\n")
        write_text(tmp_dir / "src" / "pkg" / "child" / "b.py", "b\n")
        write_text(tmp_dir / "src" / "pkg" / "other.py", "o\n")
        paths = expand_coverage_paths(
            tmp_dir,
            Path("src/pkg"),
            ("**/*.py",),
            exclude_scopes=(Path("src/pkg/child"),),
        )
        assert paths == ("src/pkg/a.py", "src/pkg/other.py")

    def test_without_exclude_includes_nested(self, tmp_dir: Path) -> None:
        write_text(tmp_dir / "src" / "pkg" / "a.py", "a\n")
        write_text(tmp_dir / "src" / "pkg" / "child" / "b.py", "b\n")
        paths = expand_coverage_paths(tmp_dir, Path("src/pkg"), ("**/*.py",))
        assert paths == ("src/pkg/a.py", "src/pkg/child/b.py")
