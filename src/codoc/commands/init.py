import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from codoc.discover import DEFAULT_SKIP, DiscoverError, git_root
from codoc.engine.engulf import EngulfError, seed_engine_from_legacy

_PROJECT_FILE = "codoc.yaml"
_SPEC_FILE = "codoc.spec.yaml"
_INDEX_FILE = Path("docs") / "index.md"
_GITKEEP = Path(".codoc") / "scripts" / ".gitkeep"

def _project_template(*, name: str, docs_dir: str, site_dir: str) -> str:
    return (
        "engine:\n"
        f"  name: {name}\n"
        f"  docs_dir: {docs_dir}\n"
        f"  site_dir: {site_dir}\n"
        "vale:\n"
        "  enabled: true\n"
        "paths:\n"
        "  scripts_dir: .codoc/scripts\n"
        "terms: []\n"
    )

_SPEC_TEMPLATE = """\
docs:
  - id: index
    type: manual
    path: docs/index.md
coverage:
  source:
    - id: package
      type: auto-generated
      paths:
        - "**/*.py"
      docs:
        - id: package.overview
          path: docs/package.md
"""

_INDEX_TEMPLATE = "# Documentation site\n\nPackage overview\n"

_CODOC_IGNORE_LINES = (".codoc/*", "!.codoc/scripts/", "!.codoc/scripts/**")
# Engine shim is generated from codoc.yaml; not a second source of truth.
_SITE_IGNORE_LINES = ("site/", ".codoc-engine.yml")
_GITIGNORE_FRESH = "\n".join([*_CODOC_IGNORE_LINES, *_SITE_IGNORE_LINES]) + "\n"


class InitError(Exception):
    """Init could not scaffold the project."""


@dataclass(frozen=True, slots=True)
class InitResult:
    root: Path
    spec_path: Path
    written: tuple[Path, ...]
    notes: tuple[str, ...] = ()


def run_init(start: Path | None = None, *, force: bool = False) -> InitResult:
    """Scaffold Codoc files at the git root that contains start."""
    if start is None:
        start = Path.cwd()
    try:
        root = git_root(start)
    except DiscoverError as err:
        raise InitError(str(err)) from err

    pkg = _choose_package_dir(root)
    spec_rel = pkg / _SPEC_FILE
    project = root / _PROJECT_FILE
    spec_abs = root / spec_rel

    _reject_path_shape_errors(root, pkg)

    if not force:
        conflicts: list[str] = []
        if project.exists():
            conflicts.append(_PROJECT_FILE)
        if spec_abs.exists():
            conflicts.append(spec_rel.as_posix())
        if conflicts:
            raise InitError("\n".join(f"{name} exists" for name in conflicts))

    notes: list[str] = []
    try:
        engine, note = seed_engine_from_legacy(root)
    except EngulfError as err:
        raise InitError(str(err)) from err
    if note:
        notes.append(note)

    written: list[Path] = []

    _atomic_write(
        project,
        _project_template(
            name=engine.name, docs_dir=engine.docs_dir, site_dir=engine.site_dir
        ),
    )
    written.append(Path(_PROJECT_FILE))

    # pkg is repo-relative; always mkdir under root (not cwd).
    (root / pkg).mkdir(parents=True, exist_ok=True)
    _atomic_write(spec_abs, _SPEC_TEMPLATE)
    written.append(spec_rel)

    index = root / _INDEX_FILE
    index.parent.mkdir(parents=True, exist_ok=True)
    if force or not index.exists():
        _atomic_write(index, _INDEX_TEMPLATE)
        written.append(_INDEX_FILE)

    gitkeep = root / _GITKEEP
    gitkeep.parent.mkdir(parents=True, exist_ok=True)
    if not gitkeep.exists():
        _atomic_write(gitkeep, "")
        written.append(_GITKEEP)

    gitignore = root / ".gitignore"
    if _ensure_gitignore(gitignore):
        written.append(Path(".gitignore"))

    ordered = tuple(sorted(written, key=lambda path: path.as_posix()))
    return InitResult(
        root=root,
        spec_path=spec_rel,
        written=ordered,
        notes=tuple(notes),
    )


def _reject_path_shape_errors(root: Path, pkg: Path) -> None:
    checks: list[tuple[Path, bool]] = [
        (root / "src", True),
        (root / pkg, True),
        (root / "docs", True),
        (root / _INDEX_FILE, False),
        (root / ".codoc", True),
        (root / ".codoc" / "scripts", True),
        (root / ".gitignore", False),
        (root / _PROJECT_FILE, False),
        (root / pkg / _SPEC_FILE, False),
    ]
    for path, expect_dir in checks:
        if not path.exists():
            continue
        if expect_dir and not path.is_dir():
            raise InitError(f"{path.relative_to(root).as_posix()} is not a directory")
        if not expect_dir and path.is_dir():
            raise InitError(f"{path.relative_to(root).as_posix()} is a directory")


def _choose_package_dir(root: Path) -> Path:
    src = root / "src"
    if src.exists() and not src.is_dir():
        raise InitError("src is not a directory")
    if src.is_symlink():
        try:
            resolved = src.resolve()
        except OSError as err:
            raise InitError("src is not a directory") from err
        if not resolved.is_relative_to(root.resolve()):
            raise InitError("src resolves outside the git root")

    candidates = _package_candidates(root, src) if src.is_dir() else []
    name = _package_name_from_root(root)
    named = Path("src") / name

    if len(candidates) == 1:
        return candidates[0]
    if (root / named).is_dir() and named in candidates:
        return named
    if (root / named).is_dir() and _is_candidate(root, root / named):
        return named
    return named


def _package_candidates(root: Path, src: Path) -> list[Path]:
    out: list[Path] = []
    for child in sorted(src.iterdir(), key=lambda path: path.name):
        if not _is_candidate(root, child):
            continue
        out.append(Path("src") / child.name)
    return out


def _is_candidate(root: Path, path: Path) -> bool:
    if not path.is_dir():
        return False
    name = path.name
    if name in DEFAULT_SKIP:
        return False
    if name.startswith("."):
        return False
    if name.endswith(".egg-info") or name.endswith(".dist-info"):
        return False
    if path.is_symlink():
        try:
            resolved = path.resolve()
        except OSError:
            return False
        if not resolved.is_relative_to(root.resolve()):
            return False
    return True


def _package_name_from_root(root: Path) -> str:
    raw = re.sub(r"[^A-Za-z0-9_]", "_", root.name)
    if not raw or raw[0].isdigit():
        raw = f"_{raw}"
    while raw in DEFAULT_SKIP or raw.startswith(".") or raw.endswith((".egg-info", ".dist-info")):
        raw = f"_{raw}"
    return raw


def _atomic_write(path: Path, text: str) -> None:
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


def _ensure_gitignore(path: Path) -> bool:
    if not path.exists():
        _atomic_write(path, _GITIGNORE_FRESH)
        return True
    if path.is_dir():
        raise InitError(".gitignore is a directory")
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines()
    changed = False
    new_lines = list(lines)

    if not _has_codoc_subsequence(new_lines):
        new_lines.extend(_CODOC_IGNORE_LINES)
        changed = True
    for line in _SITE_IGNORE_LINES:
        if line not in new_lines:
            new_lines.append(line)
            changed = True
    if not changed:
        return False

    text = "\n".join(new_lines) + "\n"
    if original and not original.endswith("\n"):
        # Append path already rebuilt full content with trailing newline.
        pass
    _atomic_write(path, text)
    return True


def _has_codoc_subsequence(lines: list[str]) -> bool:
    need = list(_CODOC_IGNORE_LINES)
    index = 0
    for line in lines:
        if line == need[index]:
            index += 1
            if index == len(need):
                return True
    return False
