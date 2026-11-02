from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from codoc.spec import SpecDocument, SpecError


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    id: str
    path: str
    type: str
    spec_path: Path


@dataclass(frozen=True, slots=True)
class PageRegistry:
    entries: tuple[RegistryEntry, ...]
    _by_id: dict[str, RegistryEntry] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_by_id",
            {entry.id: entry for entry in self.entries},
        )

    def lookup(self, page_id: str) -> RegistryEntry:
        return self._by_id[page_id]

    def __contains__(self, page_id: str) -> bool:
        return page_id in self._by_id

    def __len__(self) -> int:
        return len(self._by_id)


def build_page_registry(
    items: Sequence[tuple[Path, SpecDocument]],
) -> PageRegistry:
    """Return one entry per page id, sorted by id.

    The first spec that declares an id keeps the row. A later spec with
    that id raises SpecError. The exception path is the later file, and
    the detail names the earlier file.
    """
    seen: dict[str, RegistryEntry] = {}
    for spec_path, doc in items:
        for page in doc.pages():
            earlier = seen.get(page.id)
            if earlier is not None:
                raise SpecError(
                    spec_path,
                    f"duplicate page id {page.id!r} also in {earlier.spec_path}",
                )
            seen[page.id] = RegistryEntry(
                id=page.id,
                path=page.path,
                type=page.type,
                spec_path=spec_path,
            )
    ordered = tuple(seen[page_id] for page_id in sorted(seen))
    return PageRegistry(ordered)
