"""Invoke the configured site engine after refreshing generated config."""

import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from codoc.config import ConfigError, ProjectConfig, load_project_config
from codoc.engine.codegen import CodegenError, GeneratedPaths, ensure_generated

_PID_FILE = Path(".codoc") / "serve.pid"
_SERVE_LOG = Path(".codoc") / "logs" / "serve.log"
_DEFAULT_DEV_ADDR = "localhost:8000"


class SiteError(Exception):
    """Site engine could not be started or completed."""


@dataclass(frozen=True, slots=True)
class BuildResult:
    root: Path
    site_dir: Path
    config_file: Path
    binary: str


@dataclass(frozen=True, slots=True)
class ServeResult:
    root: Path
    pid: int
    pid_file: Path
    log_file: Path
    config_file: Path
    binary: str
    dev_addr: str


def run_build(start: Path | None = None) -> BuildResult:
    """Refresh generated config and run `<engine> build -f …` in the foreground."""
    paths, config, binary = _prepare(start)
    config_rel = paths.engine.as_posix()
    try:
        completed = subprocess.run(
            [binary, "build", "-f", config_rel],
            cwd=paths.root,
            check=False,
        )
    except FileNotFoundError as err:
        raise SiteError(f"{binary} not found on PATH") from err
    if completed.returncode != 0:
        raise SiteError(f"{binary} build failed with exit {completed.returncode}")
    return BuildResult(
        root=paths.root,
        site_dir=Path(config.engine.site_dir),
        config_file=paths.engine,
        binary=binary,
    )


def run_serve(start: Path | None = None) -> ServeResult:
    """Refresh generated config and start `<engine> serve -f …` in the background."""
    paths, config, binary = _prepare(start)
    stop_serve(paths.root)
    config_rel = paths.engine.as_posix()
    log_path = paths.root / _SERVE_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path = paths.root / _PID_FILE
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    # Serve stays up; stdout/stderr go to .codoc/logs/serve.log.
    # Close the parent handle after Popen; the child keeps the inherited fd.
    with open(log_path, "w", encoding="utf-8") as log_handle:
        try:
            proc = subprocess.Popen(
                [binary, "serve", "-f", config_rel],
                cwd=paths.root,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except FileNotFoundError as err:
            raise SiteError(f"{binary} not found on PATH") from err
    if proc.poll() is not None:
        raise SiteError(
            f"{binary} serve exited immediately with code {proc.returncode}; "
            f"see {_SERVE_LOG.as_posix()}"
        )
    pid_path.write_text(f"{proc.pid}\n", encoding="utf-8")
    return ServeResult(
        root=paths.root,
        pid=proc.pid,
        pid_file=_PID_FILE,
        log_file=_SERVE_LOG,
        config_file=paths.engine,
        binary=binary,
        dev_addr=_DEFAULT_DEV_ADDR,
    )


def stop_serve(root: Path) -> bool:
    """Stop a previous background serve if `.codoc/serve.pid` names a live process."""
    pid_path = root / _PID_FILE
    if not pid_path.is_file():
        return False
    try:
        raw = pid_path.read_text(encoding="utf-8").strip()
        pid = int(raw)
    except (OSError, ValueError):
        pid_path.unlink(missing_ok=True)
        return False
    stopped = _terminate(pid)
    pid_path.unlink(missing_ok=True)
    return stopped


def _prepare(start: Path | None) -> tuple[GeneratedPaths, ProjectConfig, str]:
    if start is None:
        start = Path.cwd()
    try:
        paths = ensure_generated(start)
    except CodegenError as err:
        raise SiteError(str(err)) from err
    try:
        config = load_project_config(paths.root / "codoc.yaml")
    except ConfigError as err:
        raise SiteError(str(err)) from err
    return paths, config, _resolve_binary(config.engine.name)


def _resolve_binary(engine_name: str) -> str:
    name = engine_name.lower()
    if name not in {"zensical", "mkdocs"}:
        raise SiteError(f"unsupported engine {engine_name!r}")
    # Prefer the binary that matches codoc.yaml; no silent mkdocs fallback.
    found = shutil.which(name)
    if found is None:
        raise SiteError(f"{name} not found on PATH")
    return name


def _terminate(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    return True
