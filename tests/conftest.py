"""Shared pytest fixtures for the Codoc test suite."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.support.git import git_repository
from tests.support.tmpdir import temporary_directory


@pytest.fixture
def tmp_dir() -> Iterator[Path]:
    """Temporary directory outside the Codoc checkout."""
    with temporary_directory() as root:
        yield root


@pytest.fixture
def git_repo() -> Iterator[Path]:
    """Fresh `git init` root outside the Codoc checkout."""
    with git_repository() as root:
        yield root
