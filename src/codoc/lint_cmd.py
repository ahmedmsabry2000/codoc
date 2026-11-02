"""Run Vale against docs after refreshing generated config."""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from codoc.codegen import CodegenError, GeneratedPaths, ensure_generated
from codoc.config import ConfigError, ProjectConfig, load_project_config


class LintError(Exception):
    """Vale could not be started or completed."""


@dataclass(frozen=True, slots=True)
class LintResult:
    root: Path
    docs_dir: Path
    config_file: Path | None
    skipped: bool
    exit_code: int


def run_lint(start: Path | None = None) -> LintResult:
    """Refresh generated config and run `vale --config … <docs_dir>` when enabled."""
    paths, config = _prepare(start)
    docs = Path(config.engine.docs_dir)
    if not config.vale.enabled:
        return LintResult(
            root=paths.root,
            docs_dir=docs,
            config_file=None,
            skipped=True,
            exit_code=0,
        )
    if paths.vale_ini is None:
        raise LintError("vale enabled but generated .vale.ini is missing")
    binary = shutil.which("vale")
    if binary is None:
        raise LintError("vale not found on PATH")
    config_rel = paths.vale_ini.as_posix()
    try:
        completed = subprocess.run(
            ["vale", "--config", config_rel, docs.as_posix()],
            cwd=paths.root,
            check=False,
        )
    except FileNotFoundError as err:
        raise LintError("vale not found on PATH") from err
    if completed.returncode != 0:
        raise LintError(f"vale failed with exit {completed.returncode}")
    return LintResult(
        root=paths.root,
        docs_dir=docs,
        config_file=paths.vale_ini,
        skipped=False,
        exit_code=0,
    )


def _prepare(start: Path | None) -> tuple[GeneratedPaths, ProjectConfig]:
    if start is None:
        start = Path.cwd()
    try:
        paths = ensure_generated(start)
    except CodegenError as err:
        raise LintError(str(err)) from err
    try:
        config = load_project_config(paths.root / "codoc.yaml")
    except ConfigError as err:
        raise LintError(str(err)) from err
    return paths, config
