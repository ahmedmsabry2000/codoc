"""List discovered specs and page counts."""

from dataclasses import dataclass
from pathlib import Path

from codoc.config import ConfigError
from codoc.discover import DiscoverError, SpecUnit, discover, git_root
from codoc.model.registry import build_page_registry
from codoc.model.spec import SpecDocument, SpecError, load_spec


class StatusError(Exception):
    """Status could not load the project or specs."""


@dataclass(frozen=True, slots=True)
class StatusRow:
    spec_path: Path
    scope_dir: Path
    pages: int


@dataclass(frozen=True, slots=True)
class StatusResult:
    rows: tuple[StatusRow, ...]
    registry_pages: int


def run_status(start: Path | None = None) -> StatusResult:
    """Discover specs, load each one, and return page counts plus registry size."""
    if start is None:
        start = Path.cwd()
    try:
        root = git_root(start)
        units = discover(root)
        loaded: list[tuple[SpecUnit, SpecDocument]] = []
        for unit in units:
            spec_path = root / unit.spec_path
            loaded.append((unit, load_spec(spec_path)))
        registry = build_page_registry(tuple((root / unit.spec_path, doc) for unit, doc in loaded))
    except (DiscoverError, ConfigError, SpecError) as err:
        raise StatusError(str(err)) from err
    rows = tuple(StatusRow(unit.spec_path, unit.scope_dir, doc.page_count) for unit, doc in loaded)
    return StatusResult(rows=rows, registry_pages=len(registry))
