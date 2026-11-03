"""Run parse/inject scripts under the git root."""

import os
import subprocess
import sys
from pathlib import Path


class ScriptError(Exception):
    """A generate script failed."""


def run_script(
    root: Path,
    script: str,
    *,
    page_id: str,
    scope_dir: Path,
    scripts_dir: str = ".codoc/scripts",
    placeholder_id: str | None = None,
) -> str:
    """
    Execute a repo-root-relative script and return stdout text.

    Uses the current Python interpreter. cwd is the git root. The resolved
    script must stay under the git root and under scripts_dir. Non-zero exit
    or a missing script raises ScriptError.
    """
    root_resolved = root.resolve()
    scripts_root = (root / scripts_dir).resolve()
    script_path = (root / script).resolve()
    if not script_path.is_file():
        raise ScriptError(f"script not found: {script}")
    try:
        script_path.relative_to(root_resolved)
    except ValueError as err:
        raise ScriptError(f"script escapes repo: {script}") from err
    try:
        script_path.relative_to(scripts_root)
    except ValueError as err:
        raise ScriptError(f"script outside scripts_dir: {script}") from err
    env = os.environ.copy()
    env["CODOC_ROOT"] = os.fspath(root)
    env["CODOC_PAGE_ID"] = page_id
    env["CODOC_SCOPE_DIR"] = scope_dir.as_posix()
    if placeholder_id is not None:
        env["CODOC_PLACEHOLDER_ID"] = placeholder_id
    try:
        completed = subprocess.run(
            [sys.executable, os.fspath(script_path)],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    except OSError as err:
        raise ScriptError(f"{script}: {err}") from err
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "failed"
        raise ScriptError(f"{script}: exit {completed.returncode}: {detail}")
    return completed.stdout
