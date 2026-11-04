from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml


class ConfigError(Exception):
    def __init__(self, path: Path, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"{path}: {detail}")


@dataclass(frozen=True, slots=True)
class EngineConfig:
    name: str = "zensical"
    docs_dir: str = "docs"
    site_dir: str = "site"
    site_name: str = "Documentation"
    # Opaque MkDocs-shaped structures carried through to the engine shim.
    theme: dict | None = None
    nav: list | None = None


@dataclass(frozen=True, slots=True)
class ValeConfig:
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class LlmConfig:
    provider: str | None = None
    model: str | None = None
    rewrite_stubs: bool = False
    embedding_model: str | None = None


@dataclass(frozen=True, slots=True)
class PathsConfig:
    scripts_dir: str = ".codoc/scripts"


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    engine: EngineConfig = EngineConfig()
    vale: ValeConfig = ValeConfig()
    llm: LlmConfig = LlmConfig()
    paths: PathsConfig = PathsConfig()
    terms: tuple[str, ...] = ()
    ignore_dirs: frozenset[str] = frozenset()


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


_ROOT_KEYS = frozenset({"engine", "vale", "llm", "paths", "terms", "ignore"})


def load_project_config(path: Path) -> ProjectConfig:
    """Read one project file. Raise ConfigError."""

    def fail(detail: str) -> ConfigError:
        return ConfigError(path, detail)

    data = _read_mapping(path, fail)
    _reject_unknown(data, _ROOT_KEYS, "document", fail)
    return ProjectConfig(
        engine=_engine(data, fail),
        vale=_vale(data, fail),
        llm=_llm(data, fail),
        paths=_paths(data, fail),
        terms=_terms(data, fail),
        ignore_dirs=_ignore(data, fail),
    )


def _reject_unknown(mapping: dict, allowed: frozenset[str], where: str, fail) -> None:
    extra = [key for key in mapping if key not in allowed]
    if not extra:
        return
    extra.sort(key=repr)
    raise fail(f"{where}: unknown field {extra[0]!r}")


def _mapping(raw: object, where: str, fail) -> dict:
    if not isinstance(raw, dict):
        raise fail(f"{where}: expected a mapping")
    return raw


def _nonempty_str(value: object, where: str, fail) -> str:
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


def _engine(data: dict, fail) -> EngineConfig:
    if "engine" not in data:
        return EngineConfig()
    raw = _mapping(data["engine"], "engine", fail)
    _reject_unknown(
        raw,
        frozenset({"name", "docs_dir", "site_dir", "site_name", "theme", "nav"}),
        "engine",
        fail,
    )
    name = "zensical"
    docs_dir = "docs"
    site_dir = "site"
    site_name = "Documentation"
    theme = None
    nav = None
    if "name" in raw:
        name = _nonempty_str(raw["name"], "engine.name", fail)
    if "docs_dir" in raw:
        docs_dir = _relative_path(raw["docs_dir"], "engine.docs_dir", fail)
    if "site_dir" in raw:
        site_dir = _relative_path(raw["site_dir"], "engine.site_dir", fail)
    if "site_name" in raw:
        site_name = _nonempty_str(raw["site_name"], "engine.site_name", fail)
    if "theme" in raw:
        theme_raw = raw["theme"]
        if isinstance(theme_raw, str):
            theme = {"name": theme_raw}
        elif isinstance(theme_raw, dict):
            theme = theme_raw
        else:
            raise fail("engine.theme: expected a mapping or theme name string")
    if "nav" in raw:
        if not isinstance(raw["nav"], list):
            raise fail("engine.nav: expected a list")
        nav = raw["nav"]
    return EngineConfig(name, docs_dir, site_dir, site_name, theme, nav)


def _vale(data: dict, fail) -> ValeConfig:
    if "vale" not in data:
        return ValeConfig()
    raw = _mapping(data["vale"], "vale", fail)
    _reject_unknown(raw, frozenset({"enabled"}), "vale", fail)
    if "enabled" not in raw:
        return ValeConfig()
    enabled = raw["enabled"]
    if not isinstance(enabled, bool):
        raise fail("vale.enabled: expected a boolean")
    return ValeConfig(enabled)


def _llm(data: dict, fail) -> LlmConfig:
    if "llm" not in data:
        return LlmConfig()
    raw = _mapping(data["llm"], "llm", fail)
    _reject_unknown(
        raw,
        frozenset({"provider", "model", "rewrite_stubs", "embedding_model"}),
        "llm",
        fail,
    )
    provider = None
    model = None
    rewrite_stubs = False
    embedding_model = None
    if "provider" in raw:
        provider = _nonempty_str(raw["provider"], "llm.provider", fail)
    if "model" in raw:
        model = _nonempty_str(raw["model"], "llm.model", fail)
    if "rewrite_stubs" in raw:
        value = raw["rewrite_stubs"]
        if not isinstance(value, bool):
            raise fail("llm.rewrite_stubs: expected a boolean")
        rewrite_stubs = value
    if "embedding_model" in raw:
        embedding_model = _nonempty_str(raw["embedding_model"], "llm.embedding_model", fail)
    return LlmConfig(provider, model, rewrite_stubs, embedding_model)


def _paths(data: dict, fail) -> PathsConfig:
    if "paths" not in data:
        return PathsConfig()
    raw = _mapping(data["paths"], "paths", fail)
    _reject_unknown(raw, frozenset({"scripts_dir"}), "paths", fail)
    if "scripts_dir" not in raw:
        return PathsConfig()
    scripts_dir = _relative_path(raw["scripts_dir"], "paths.scripts_dir", fail)
    return PathsConfig(scripts_dir)


def _terms(data: dict, fail) -> tuple[str, ...]:
    if "terms" not in data:
        return ()
    raw = data["terms"]
    if not isinstance(raw, list):
        raise fail("terms: expected a list")
    return tuple(_nonempty_str(item, f"terms[{index}]", fail) for index, item in enumerate(raw))


def _ignore(data: dict, fail) -> frozenset[str]:
    if "ignore" not in data:
        return frozenset()
    raw = data["ignore"]
    if not isinstance(raw, list):
        raise fail("ignore: expected a list")
    names: list[str] = []
    for index, item in enumerate(raw):
        where = f"ignore[{index}]"
        if (
            not isinstance(item, str)
            or item == ""
            or item in {".", ".."}
            or "/" in item
            or "\\" in item
        ):
            raise fail(f"{where}: expected a single directory name")
        names.append(item)
    return frozenset(names)
