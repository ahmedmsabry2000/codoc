"""Small filesystem helpers for tests."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from tests.support.tmpdir import temporary_directory


def write_text(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def touch(path: Path, text: str = "x") -> None:
    write_text(path, text)


@contextmanager
def yaml_file(text: str, name: str = "codoc.yaml") -> Iterator[Path]:
    """Yield a path to a YAML file written in a temp directory outside the repo."""
    with temporary_directory() as raw:
        path = Path(raw) / name
        path.write_text(text, encoding="utf-8")
        yield path
