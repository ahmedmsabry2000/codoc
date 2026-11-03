"""Stop background serve and remove generated site/engine/Vale outputs."""

import shutil
from dataclasses import dataclass
from pathlib import Path

from codoc.commands.site import stop_serve
from codoc.config import ConfigError, load_project_config
from codoc.discover import DiscoverError, git_root
from codoc.engine.codegen import ENGINE_SHIM

_GENERATED_DIR = Path(".codoc") / "generated"
_RUNTIME_DIRS = (
    Path(".codoc") / "cache",
    Path(".codoc") / "index",
    Path(".codoc") / "reports",
    Path(".codoc") / "logs",
)
_PID_FILE = Path(".codoc") / "serve.pid"


class CleanError(Exception):
    """Clean could not remove generated outputs."""


@dataclass(frozen=True, slots=True)
class CleanResult:
    root: Path
    stopped_serve: bool
    removed: tuple[Path, ...]


def run_clean(start: Path | None = None) -> CleanResult:
    """Stop serve if needed and delete site/, generated configs, and .codoc runtime dirs."""
    if start is None:
        start = Path.cwd()
    try:
        root = git_root(start)
    except DiscoverError as err:
        raise CleanError(str(err)) from err

    site_dir = Path("site")
    project = root / "codoc.yaml"
    if project.is_file():
        try:
            config = load_project_config(project)
        except ConfigError as err:
            raise CleanError(str(err)) from err
        site_dir = Path(config.engine.site_dir)

    stopped = stop_serve(root)
    removed: list[Path] = []
    # Do not remove root mkdocs.yml / zensical.yml — those are user files (engulf keeps them).
    for rel in (
        site_dir,
        ENGINE_SHIM,
        _GENERATED_DIR,
        *_RUNTIME_DIRS,
        _PID_FILE,
    ):
        if _remove(root / rel):
            removed.append(rel)
    ordered = tuple(sorted(set(removed), key=lambda path: path.as_posix()))
    return CleanResult(root=root, stopped_serve=stopped, removed=ordered)


def _remove(path: Path) -> bool:
    if not path.exists() and not path.is_symlink():
        return False
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
        return True
    path.unlink(missing_ok=True)
    return True
