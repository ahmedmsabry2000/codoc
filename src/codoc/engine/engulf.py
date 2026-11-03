"""Import root mkdocs.yml / zensical.yml into codoc.yaml engine settings."""

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
    """Parse docs_dir/site_dir from a MkDocs-shaped config; name comes from the file."""
    data = _load_mapping(path)
    docs_dir = "docs"
    site_dir = "site"
    # Only fields Codoc's engine: section understands; other keys stay in the legacy file.
    if "docs_dir" in data:
        docs_dir = _legacy_relative(data["docs_dir"], path, "docs_dir")
    if "site_dir" in data:
        site_dir = _legacy_relative(data["site_dir"], path, "site_dir")
    return EngineConfig(engine_name, docs_dir, site_dir)


def engulf_project(
    root: Path,
    config: ProjectConfig,
    *,
    fill_defaults_only: bool,
    project_path: Path | None = None,
) -> EngulfOutcome:
    """
    Merge a root legacy engine file into config.engine.

    When fill_defaults_only is True, only replace engine fields that still equal
    EngineConfig defaults (so a later user edit to codoc.yaml is not clobbered).
    Writes codoc.yaml when the merged engine differs. Never deletes the legacy file.
    """
    picked = pick_legacy_engine_file(root, preferred_name=config.engine.name.lower())
    if picked is None:
        return EngulfOutcome(config, None, False, None)

    source, engine_name = picked
    legacy = read_legacy_engine(source, engine_name)
    merged = _merge_engine(config.engine, legacy, fill_defaults_only=fill_defaults_only)
    if merged == config.engine:
        return EngulfOutcome(config, source, False, None)

    updated = replace(config, engine=merged)
    target = project_path if project_path is not None else root / "codoc.yaml"
    _write_project(target, updated)
    note = (
        f"imported engine settings from {source.name} into codoc.yaml; "
        f"left {source.name} in place (codoc.yaml is SoT)"
    )
    return EngulfOutcome(updated, source, True, note)


def seed_engine_from_legacy(root: Path) -> tuple[EngineConfig, str | None]:
    """For init: build engine settings from a legacy file when present."""
    picked = pick_legacy_engine_file(root)
    if picked is None:
        return EngineConfig(), None
    source, engine_name = picked
    engine = read_legacy_engine(source, engine_name)
    note = (
        f"imported engine settings from {source.name} into codoc.yaml; "
        f"left {source.name} in place (codoc.yaml is SoT)"
    )
    return engine, note


def render_project_yaml(config: ProjectConfig) -> str:
    """Serialize ProjectConfig to YAML text for codoc.yaml."""
    data: dict = {
        "engine": {
            "name": config.engine.name,
            "docs_dir": config.engine.docs_dir,
            "site_dir": config.engine.site_dir,
        },
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
    docs_dir = (
        legacy.docs_dir if current.docs_dir == defaults.docs_dir else current.docs_dir
    )
    site_dir = (
        legacy.site_dir if current.site_dir == defaults.site_dir else current.site_dir
    )
    return EngineConfig(name, docs_dir, site_dir)


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
