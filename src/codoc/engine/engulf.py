"""Import root mkdocs.yml / zensical.yml into codoc.yaml; one project config only."""

import os
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from codoc.config import EngineConfig, ProjectConfig

# Prefer Zensical when both legacy files exist and engine.name does not decide.
_LEGACY_FILES: tuple[tuple[str, str], ...] = (
    ("zensical.yml", "zensical"),
    ("mkdocs.yml", "mkdocs"),
)
# Archive for engulfed root engine configs (under gitignored .codoc/).
IMPORTED_DIR = Path(".codoc") / "imported"


class EngulfError(Exception):
    """Legacy engine config could not be imported."""


@dataclass(frozen=True, slots=True)
class EngulfOutcome:
    config: ProjectConfig
    source: Path | None
    wrote_project: bool
    note: str | None


def pick_legacy_engine_file(
    root: Path, *, preferred_name: str | None = None
) -> tuple[Path, str] | None:
    """Return (path, engine_name) for an existing root legacy config, if any."""
    by_name = {name: root / filename for filename, name in _LEGACY_FILES}
    if preferred_name in by_name and by_name[preferred_name].is_file():
        return by_name[preferred_name], preferred_name
    for filename, name in _LEGACY_FILES:
        path = root / filename
        if path.is_file():
            return path, name
    return None


def read_legacy_engine(path: Path, engine_name: str) -> EngineConfig:
    """Parse MkDocs-shaped keys Codoc can carry into engine: / the shim."""
    data = _load_mapping(path)
    docs_dir = "docs"
    site_dir = "site"
    site_name = "Documentation"
    theme = None
    nav = None
    if "docs_dir" in data:
        docs_dir = _legacy_relative(data["docs_dir"], path, "docs_dir")
    if "site_dir" in data:
        site_dir = _legacy_relative(data["site_dir"], path, "site_dir")
    if "site_name" in data:
        raw_name = data["site_name"]
        if not isinstance(raw_name, str) or raw_name == "":
            raise EngulfError(f"{path.name}: site_name: expected a non-empty string")
        site_name = raw_name
    if "theme" in data:
        theme_raw = data["theme"]
        if isinstance(theme_raw, str):
            theme = {"name": theme_raw}
        elif isinstance(theme_raw, dict):
            theme = theme_raw
        else:
            raise EngulfError(f"{path.name}: theme: expected a mapping or theme name")
    if "nav" in data:
        if not isinstance(data["nav"], list):
            raise EngulfError(f"{path.name}: nav: expected a list")
        nav = data["nav"]
    return EngineConfig(engine_name, docs_dir, site_dir, site_name, theme, nav)


def relocate_legacy_engine_files(root: Path) -> tuple[str, ...]:
    """
    Move any root mkdocs.yml / zensical.yml under .codoc/imported/.

    Codoc is all-in-one: after adopt, those must not remain as live configs.
    """
    notes: list[str] = []
    dest_dir = root / IMPORTED_DIR
    for filename, _name in _LEGACY_FILES:
        source = root / filename
        if not source.is_file():
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        os.replace(source, dest)
        notes.append(
            f"moved {filename} to {IMPORTED_DIR.as_posix()}/{filename} "
            f"(codoc.yaml is the only project config)"
        )
    return tuple(notes)


def engulf_project(
    root: Path,
    config: ProjectConfig,
    *,
    fill_defaults_only: bool,
    project_path: Path | None = None,
) -> EngulfOutcome:
    """
    Merge a root legacy engine file into config.engine, then archive root legacy files.

    When fill_defaults_only is True, only replace engine fields that still equal
    EngineConfig defaults (so a later user edit to codoc.yaml is not clobbered).
    Writes codoc.yaml when the merged engine differs. Relocates root legacy configs
    so Codoc remains the single live project config.
    """
    picked = pick_legacy_engine_file(root, preferred_name=config.engine.name.lower())
    parts: list[str] = []
    updated = config
    wrote = False
    source: Path | None = None

    if picked is not None:
        source, engine_name = picked
        legacy = read_legacy_engine(source, engine_name)
        merged = _merge_engine(config.engine, legacy, fill_defaults_only=fill_defaults_only)
        if merged != config.engine:
            updated = replace(config, engine=merged)
            target = project_path if project_path is not None else root / "codoc.yaml"
            _write_project(target, updated)
            wrote = True
            parts.append(f"imported engine settings from {source.name} into codoc.yaml")

    parts.extend(relocate_legacy_engine_files(root))
    note = "; ".join(parts) if parts else None
    return EngulfOutcome(updated, source, wrote, note)


def seed_engine_from_legacy(root: Path) -> tuple[EngineConfig, Path | None]:
    """For init: read engine settings from a legacy file when present (before relocate)."""
    picked = pick_legacy_engine_file(root)
    if picked is None:
        return EngineConfig(), None
    source, engine_name = picked
    return read_legacy_engine(source, engine_name), source


def render_project_yaml(config: ProjectConfig) -> str:
    """Serialize ProjectConfig to YAML text for codoc.yaml."""
    engine: dict = {
        "name": config.engine.name,
        "docs_dir": config.engine.docs_dir,
        "site_dir": config.engine.site_dir,
        "site_name": config.engine.site_name,
    }
    if config.engine.theme is not None:
        engine["theme"] = config.engine.theme
    if config.engine.nav is not None:
        engine["nav"] = config.engine.nav
    data: dict = {
        "engine": engine,
        "vale": {"enabled": config.vale.enabled},
        "paths": {"scripts_dir": config.paths.scripts_dir},
        "terms": list(config.terms),
    }
    if config.llm.provider is not None or config.llm.model is not None:
        llm: dict = {}
        if config.llm.provider is not None:
            llm["provider"] = config.llm.provider
        if config.llm.model is not None:
            llm["model"] = config.llm.model
        data["llm"] = llm
    if config.ignore_dirs:
        data["ignore"] = sorted(config.ignore_dirs)
    dumped = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
    assert isinstance(dumped, str)
    return dumped


def _merge_engine(
    current: EngineConfig, legacy: EngineConfig, *, fill_defaults_only: bool
) -> EngineConfig:
    defaults = EngineConfig()
    if not fill_defaults_only:
        return legacy
    name = legacy.name if current.name == defaults.name else current.name
    docs_dir = legacy.docs_dir if current.docs_dir == defaults.docs_dir else current.docs_dir
    site_dir = legacy.site_dir if current.site_dir == defaults.site_dir else current.site_dir
    site_name = legacy.site_name if current.site_name == defaults.site_name else current.site_name
    theme = legacy.theme if current.theme is None else current.theme
    nav = legacy.nav if current.nav is None else current.nav
    return EngineConfig(name, docs_dir, site_dir, site_name, theme, nav)


def _load_mapping(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as err:
        raise EngulfError(f"{path.name}: invalid UTF-8: {err.reason}") from err
    except OSError as err:
        raise EngulfError(f"{path.name}: {err.strerror or 'cannot read file'}") from err
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as err:
        raise EngulfError(f"{path.name}: invalid YAML: {err}") from err
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise EngulfError(f"{path.name}: document must be a mapping")
    return loaded


def _legacy_relative(value: object, path: Path, field: str) -> str:
    if not isinstance(value, str) or not _is_relative_path(value):
        raise EngulfError(f"{path.name}: {field}: expected a relative path")
    return value


def _is_relative_path(value: str) -> bool:
    if value == "" or value.startswith("/") or value.startswith("~") or "\\" in value:
        return False
    return all(part not in ("", ".", "..") for part in value.split("/"))


def _write_project(path: Path, config: ProjectConfig) -> None:
    text = render_project_yaml(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
