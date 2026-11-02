"""Temp directories that stay outside this checkout even if TMPDIR is mis-set."""

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def safe_temp_root() -> Path:
    """Return a directory usable for fixtures that is not inside this repo."""
    candidates = [
        Path(tempfile.gettempdir()).resolve(),
        Path("/tmp").resolve(),
        Path("/var/tmp").resolve(),
        (Path.home() / ".cache" / "codoc-tests").resolve(),
    ]
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        try:
            if path == _REPO_ROOT or path.is_relative_to(_REPO_ROOT):
                continue
        except (OSError, ValueError):
            continue
        if path.is_dir():
            return path
        if path.name == "codoc-tests":
            path.mkdir(parents=True, exist_ok=True)
            return path
    raise RuntimeError("no safe temp directory outside the Codoc checkout")


@contextmanager
def temporary_directory(prefix: str = "codoc-") -> Iterator[Path]:
    """Create a temporary directory outside the package tree."""
    with tempfile.TemporaryDirectory(prefix=prefix, dir=safe_temp_root()) as raw:
        yield Path(raw)
