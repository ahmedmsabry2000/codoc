"""Run the codoc CLI against a given cwd in tests."""

import io
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import codoc.cli as cli


def run_cli(path: Path, argv: list[str]) -> tuple[str, str, int | None]:
    """Invoke `cli.main(argv)` with cwd=path. Return stdout, stderr, exit code."""
    previous = os.getcwd()
    os.chdir(path)
    stdout = io.StringIO()
    stderr = io.StringIO()
    code: int | None = None
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                cli.main(argv)
            except SystemExit as caught:
                status = caught.code
                code = status if isinstance(status, int) else None
        return stdout.getvalue(), stderr.getvalue(), code
    finally:
        os.chdir(previous)
