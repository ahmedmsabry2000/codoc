from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

PAGE_TYPES: tuple[str, ...] = ("manual", "hybrid", "auto-generated")


class SpecError(Exception):
    def __init__(self, path: Path, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"{path}: {detail}")


@dataclass(frozen=True, slots=True)
class Link:
    id: str
    label: str | None = None


@dataclass(frozen=True, slots=True)
class Placeholder:
    id: str
    script: str


@dataclass(frozen=True, slots=True)
class Page:
    id: str
    type: str
    path: str
    canonical: str | None = None
    links: tuple[Link, ...] = ()
    placeholders: tuple[Placeholder, ...] = ()
    script: str | None = None


@dataclass(frozen=True, slots=True)
class CoverageBlock:
    id: str
    type: str
    paths: tuple[str, ...]
    docs: tuple[Page, ...] = ()


@dataclass(frozen=True, slots=True)
class Coverage:
    source: tuple[CoverageBlock, ...] = ()
    features: tuple[CoverageBlock, ...] = ()


@dataclass(frozen=True, slots=True)
class SpecDocument:
    docs: tuple[Page, ...] = ()
    coverage: Coverage = Coverage()

    def pages(self) -> tuple[Page, ...]:
        blocks = self.coverage.source + self.coverage.features
        nested = tuple(page for block in blocks for page in block.docs)
        return self.docs + nested

    @property
    def page_count(self) -> int:
        return len(self.pages())


class _UniqueSafeLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found merge key",
                key_node.start_mark,
            )
        key = loader.construct_object(key_node, deep=deep)
        try:
            seen = key in mapping
        except TypeError as err:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"unhashable key {key!r}",
                key_node.start_mark,
            ) from err
        if seen:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _read_mapping(path: Path, fail: Callable[[str], Exception]) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as err:
        raise fail(f"invalid UTF-8: {err.reason}") from err
    except OSError as err:
        raise fail(err.strerror or "cannot read file") from err
    try:
        loaded = yaml.load(text, Loader=_UniqueSafeLoader)
    except yaml.YAMLError as err:
        raise fail(f"invalid YAML: {err}") from err
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise fail("document must be a mapping")
    return loaded


_ROOT_KEYS = frozenset({"docs", "coverage"})
_COVERAGE_KEYS = frozenset({"source", "features"})
_BLOCK_KEYS = frozenset({"id", "type", "paths", "docs"})
_PAGE_KEYS = frozenset({"id", "type", "path", "canonical", "links", "placeholders", "script"})
_LINK_KEYS = frozenset({"id", "label"})
_PLACEHOLDER_KEYS = frozenset({"id", "script"})
_TYPE_NAMES = ", ".join(PAGE_TYPES[:-1]) + f", or {PAGE_TYPES[-1]}"


def load_spec(path: Path) -> SpecDocument:
    """Read one spec file. Raise SpecError, including for a repeated page id."""

    def fail(detail: str) -> SpecError:
        return SpecError(path, detail)

    data = _read_mapping(path, fail)
    _reject_unknown(data, _ROOT_KEYS, "document", fail)
    top = _parse_pages(data, "docs", "docs", fail, None)
    coverage, nested = _parse_coverage(data, fail)
    _reject_duplicate_pages(top + nested, fail)
    return SpecDocument(
        docs=tuple(page for page, _where in top),
        coverage=coverage,
    )


def check_unique_page_ids(items: Sequence[tuple[Path, SpecDocument]]) -> None:
    """Raise SpecError when one page id is declared in two spec files.

    items are pairs of spec path and document, in discover order. The
    exception path is the later file. detail names the earlier file.
    """
    seen: dict[str, Path] = {}
    for path, doc in items:
        for page in doc.pages():
            earlier = seen.get(page.id)
            if earlier is not None:
                raise SpecError(
                    path,
                    f"duplicate page id {page.id!r} also in {earlier}",
                )
            seen[page.id] = path


def _reject_unknown(mapping: dict, allowed: frozenset[str], where: str, fail) -> None:
    extra = [key for key in mapping if key not in allowed]
    if not extra:
        return
    extra.sort(key=repr)
    raise fail(f"{where}: unknown field {extra[0]!r}")


def _require(mapping: dict, key: str, where: str, fail) -> None:
    if key not in mapping:
        raise fail(f"{where}: missing {key!r}")


def _identifier(value: object, where: str, fail) -> str:
    if not isinstance(value, str) or value == "" or any(char.isspace() for char in value):
        raise fail(f"{where}: expected a non-empty string with no whitespace")
    return value


def _label(value: object, where: str, fail) -> str:
    if not isinstance(value, str) or value == "":
        raise fail(f"{where}: expected a non-empty string")
    return value


def _relative_path(value: object, where: str, fail) -> str:
    if not isinstance(value, str) or not _is_relative_path(value):
        raise fail(f"{where}: expected a relative path")
    return value


def _is_relative_path(value: str) -> bool:
    if value == "" or value.startswith("/") or value.startswith("~") or "\\" in value:
        return False
    return all(part not in ("", ".", "..") for part in value.split("/"))


def _page_type(value: object, where: str, fail) -> str:
    if value not in PAGE_TYPES:
        raise fail(f"{where}: expected {_TYPE_NAMES}")
    return str(value)


def _parse_pages(
    owner: dict,
    key: str,
    where_prefix: str,
    fail,
    block_type: str | None,
) -> list[tuple[Page, str]]:
    if key not in owner:
        return []
    raw = owner[key]
    if not isinstance(raw, list):
        raise fail(f"{where_prefix}: expected a list")
    found: list[tuple[Page, str]] = []
    for index, item in enumerate(raw):
        where = f"{where_prefix}[{index}]"
        found.append(_parse_page(item, where, fail, block_type))
    return found


def _parse_page(item: object, where: str, fail, block_type: str | None) -> tuple[Page, str]:
    if not isinstance(item, dict):
        raise fail(f"{where}: expected a mapping")
    _reject_unknown(item, _PAGE_KEYS, where, fail)
    _require(item, "id", where, fail)
    if block_type is None:
        _require(item, "type", where, fail)
    _require(item, "path", where, fail)
    page_id = _identifier(item["id"], f"{where}.id", fail)
    page_type = _resolve_type(item, where, fail, block_type)
    path = _relative_path(item["path"], f"{where}.path", fail)
    canonical = None
    if "canonical" in item:
        canonical = _identifier(item["canonical"], f"{where}.canonical", fail)
    page = Page(
        id=page_id,
        type=page_type,
        path=path,
        canonical=canonical,
        links=_links(item, where, fail),
        placeholders=_placeholders(item, where, fail, page_type),
        script=_script(item, where, fail, page_type),
    )
    return page, where


def _resolve_type(item: dict, where: str, fail, block_type: str | None) -> str:
    if block_type is None:
        return _page_type(item["type"], f"{where}.type", fail)
    if "type" not in item:
        return block_type
    if item["type"] != block_type:
        raise fail(f"{where}.type: expected {block_type}")
    return block_type


def _links(item: dict, where: str, fail) -> tuple[Link, ...]:
    if "links" not in item:
        return ()
    raw = item["links"]
    if not isinstance(raw, list):
        raise fail(f"{where}.links: expected a list")
    links: list[Link] = []
    for index, entry in enumerate(raw):
        loc = f"{where}.links[{index}]"
        if not isinstance(entry, dict):
            raise fail(f"{loc}: expected a mapping")
        _reject_unknown(entry, _LINK_KEYS, loc, fail)
        _require(entry, "id", loc, fail)
        label = None
        if "label" in entry:
            label = _label(entry["label"], f"{loc}.label", fail)
        links.append(Link(_identifier(entry["id"], f"{loc}.id", fail), label))
    return tuple(links)


def _placeholders(item: dict, where: str, fail, page_type: str) -> tuple[Placeholder, ...]:
    if "placeholders" not in item:
        return ()
    raw = item["placeholders"]
    if not isinstance(raw, list):
        raise fail(f"{where}.placeholders: expected a list")
    if raw and page_type != "hybrid":
        raise fail(f"{where}.placeholders: allowed only when type is hybrid")
    found: list[Placeholder] = []
    for index, entry in enumerate(raw):
        loc = f"{where}.placeholders[{index}]"
        if not isinstance(entry, dict):
            raise fail(f"{loc}: expected a mapping")
        _reject_unknown(entry, _PLACEHOLDER_KEYS, loc, fail)
        _require(entry, "id", loc, fail)
        _require(entry, "script", loc, fail)
        found.append(
            Placeholder(
                _identifier(entry["id"], f"{loc}.id", fail),
                _relative_path(entry["script"], f"{loc}.script", fail),
            )
        )
    return tuple(found)


def _script(item: dict, where: str, fail, page_type: str) -> str | None:
    if "script" not in item:
        return None
    if page_type != "auto-generated":
        raise fail(f"{where}.script: allowed only when type is auto-generated")
    return _relative_path(item["script"], f"{where}.script", fail)


def _parse_coverage(data: dict, fail) -> tuple[Coverage, list[tuple[Page, str]]]:
    if "coverage" not in data:
        return Coverage(), []
    raw = data["coverage"]
    if not isinstance(raw, dict):
        raise fail("coverage: expected a mapping")
    _reject_unknown(raw, _COVERAGE_KEYS, "coverage", fail)
    source, source_pages = _parse_blocks(raw, "source", "coverage.source", fail)
    features, feature_pages = _parse_blocks(raw, "features", "coverage.features", fail)
    _reject_duplicate_blocks(source + features, fail)
    coverage = Coverage(
        source=tuple(block for block, _where in source),
        features=tuple(block for block, _where in features),
    )
    return coverage, source_pages + feature_pages


def _parse_blocks(owner: dict, key: str, where_prefix: str, fail):
    if key not in owner:
        return [], []
    raw = owner[key]
    if not isinstance(raw, list):
        raise fail(f"{where_prefix}: expected a list")
    blocks = []
    pages: list[tuple[Page, str]] = []
    for index, item in enumerate(raw):
        where = f"{where_prefix}[{index}]"
        block, block_pages = _parse_block(item, where, fail)
        blocks.append((block, where))
        pages.extend(block_pages)
    return blocks, pages


def _parse_block(item: object, where: str, fail):
    if not isinstance(item, dict):
        raise fail(f"{where}: expected a mapping")
    _reject_unknown(item, _BLOCK_KEYS, where, fail)
    for key in ("id", "type", "paths"):
        _require(item, key, where, fail)
    block_id = _identifier(item["id"], f"{where}.id", fail)
    block_type = _page_type(item["type"], f"{where}.type", fail)
    paths = _globs(item["paths"], f"{where}.paths", fail)
    nested = _parse_pages(item, "docs", f"{where}.docs", fail, block_type)
    block = CoverageBlock(
        id=block_id,
        type=block_type,
        paths=paths,
        docs=tuple(page for page, _page_where in nested),
    )
    return block, nested


def _globs(raw: object, where: str, fail) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise fail(f"{where}: expected a list")
    return tuple(
        _relative_path(item, f"{where}[{index}]", fail) for index, item in enumerate(raw)
    )


def _reject_duplicate_pages(pages: list[tuple[Page, str]], fail) -> None:
    seen: set[str] = set()
    for page, where in pages:
        if page.id in seen:
            raise fail(f"{where}.id: duplicate page id {page.id!r}")
        seen.add(page.id)


def _reject_duplicate_blocks(blocks: list[tuple[CoverageBlock, str]], fail) -> None:
    seen: set[str] = set()
    for block, where in blocks:
        if block.id in seen:
            raise fail(f"{where}.id: duplicate coverage id {block.id!r}")
        seen.add(block.id)
