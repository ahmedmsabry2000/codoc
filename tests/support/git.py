"""Git repo fixtures for tests (outside the Codoc checkout)."""

import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from tests.support.tmpdir import temporary_directory


def init_git_repo(root: Path) -> Path:
    """Run `git init` in root and return root."""
    subprocess.run(
        ["git", "init", "-q"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return root


@contextmanager
def git_repository(*, name: str | None = None) -> Iterator[Path]:
    """
    Yield a fresh git root outside the package tree.

    When name is set, the repo lives at <tmpdir>/<name> (for package-name tests).
    """
    with temporary_directory() as parent:
        if name is None:
            root = parent
        else:
            root = parent / name
            root.mkdir()
        yield init_git_repo(root)
