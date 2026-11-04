import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from codoc.commands.wizard import (
    WizardDefaults,
    WizardError,
    apply_wizard_defaults,
    confirm,
    defaults_from_config,
    is_interactive_tty,
    run_wizard,
    site_name_from_root,
)
from codoc.config import ConfigError, ProjectConfig, load_project_config
from codoc.discover import DEFAULT_SKIP, DiscoverError, git_root
from codoc.engine.engulf import (
    EngulfError,
    relocate_legacy_engine_files,
    render_project_yaml,
    seed_engine_from_legacy,
)
from codoc.templates import load_template

_PROJECT_FILE = "codoc.yaml"
_SPEC_FILE = "codoc.spec.yaml"
_INDEX_FILE = Path("docs") / "index.md"
_GITKEEP = Path(".codoc") / "scripts" / ".gitkeep"

# .gitignore lines that must appear as a contiguous Codoc block, then site shim lines.
_CODOC_IGNORE_LINES = (".codoc/*", "!.codoc/scripts/", "!.codoc/scripts/**")
_SITE_IGNORE_LINES = ("site/", ".codoc-engine.yml")


class InitError(Exception):
    """Init could not scaffold the project."""


@dataclass(frozen=True, slots=True)
class InitResult:
    root: Path
    spec_path: Path
    written: tuple[Path, ...]
    notes: tuple[str, ...] = ()


def run_init(
    start: Path | None = None,
    *,
    force: bool = False,
    yes: bool = False,
    interactive: bool | None = None,
    prompt=None,
) -> InitResult:
    """
    Scaffold or update Codoc files at the git root that contains start.

    Non-interactive (`yes=True` or no TTY): Zensical + Vale defaults, no LLM.
    Interactive TTY: wizard for engine, Vale, terms, and optional LLM provider.
    Existing projects: TTY offers config update/merge; `--force` overwrites
    managed scaffold files; `--yes` alone does not clobber.
    """
    if start is None:
        start = Path.cwd()
    try:
        root = git_root(start)
    except DiscoverError as err:
        raise InitError(str(err)) from err

    use_wizard = interactive if interactive is not None else (is_interactive_tty() and not yes)
    pkg = _choose_package_dir(root)
    spec_rel = pkg / _SPEC_FILE
    project = root / _PROJECT_FILE
    spec_abs = root / spec_rel

    _reject_path_shape_errors(root, pkg)

    existing = project.exists() or spec_abs.exists()
    if existing and not force:
        if use_wizard and project.is_file():
            return _update_existing_config(root, project, spec_rel, prompt=prompt)
        conflicts: list[str] = []
        if project.exists():
            conflicts.append(_PROJECT_FILE)
        if spec_abs.exists():
            conflicts.append(spec_rel.as_posix())
        hint = " (pass --force to overwrite, or run interactively to update codoc.yaml)"
        raise InitError("\n".join(f"{name} exists" for name in conflicts) + hint)

    notes: list[str] = []
    try:
        engine, legacy_source = seed_engine_from_legacy(root)
    except EngulfError as err:
        raise InitError(str(err)) from err
    if legacy_source is not None:
        notes.append(f"imported engine settings from {legacy_source.name} into codoc.yaml")

    wizard_site = (
        engine.site_name if engine.site_name != "Documentation" else site_name_from_root(root)
    )
    base = ProjectConfig(engine=engine)
    if use_wizard:
        try:
            choices = run_wizard(
                WizardDefaults(
                    engine_name=engine.name,
                    site_name=wizard_site,
                    vale_enabled=True,
                ),
                prompt=prompt,
            )
        except WizardError as err:
            raise InitError(str(err)) from err
        config = apply_wizard_defaults(base, choices)
        notes.append("configured via interactive wizard")
    else:
        config = apply_wizard_defaults(
            base,
            WizardDefaults(
                engine_name=engine.name,
                site_name=engine.site_name,
                vale_enabled=True,
            ),
        )
        if yes:
            notes.append("used non-interactive defaults (--yes)")

    written: list[Path] = []

    _atomic_write(project, render_project_yaml(config))
    written.append(Path(_PROJECT_FILE))

    # pkg is repo-relative; always mkdir under root (not cwd).
    (root / pkg).mkdir(parents=True, exist_ok=True)
    _atomic_write(spec_abs, load_template("starter-spec.yaml"))
    written.append(spec_rel)

    index = root / _INDEX_FILE
    index.parent.mkdir(parents=True, exist_ok=True)
    if force or not index.exists():
        _atomic_write(index, load_template("docs-index.md"))
        written.append(_INDEX_FILE)

    gitkeep = root / _GITKEEP
    gitkeep.parent.mkdir(parents=True, exist_ok=True)
    if not gitkeep.exists():
        _atomic_write(gitkeep, "")
        written.append(_GITKEEP)

    overview_script = Path(".codoc") / "scripts" / "gen_package_overview.py"
    overview_abs = root / overview_script
    if force or not overview_abs.exists():
        _atomic_write(overview_abs, load_template("gen_package_overview.py"))
        written.append(overview_script)

    gitignore = root / ".gitignore"
    if _ensure_gitignore(gitignore):
        written.append(Path(".gitignore"))

    # One live project config: archive root engine ymls under .codoc/imported/.
    notes.extend(relocate_legacy_engine_files(root))

    ordered = tuple(sorted(written, key=lambda path: path.as_posix()))
    return InitResult(
        root=root,
        spec_path=spec_rel,
        written=ordered,
        notes=tuple(notes),
    )


def _update_existing_config(
    root: Path,
    project: Path,
    spec_rel: Path,
    *,
    prompt=None,
) -> InitResult:
    """Merge wizard answers into an existing codoc.yaml after confirmation."""
    try:
        if not confirm(
            "codoc.yaml exists. Update project config",
            default=False,
            prompt=prompt,
        ):
            raise InitError("aborted (existing project unchanged)")
        current = load_project_config(project)
        choices = run_wizard(defaults_from_config(current), prompt=prompt)
    except WizardError as err:
        raise InitError(str(err)) from err
    except ConfigError as err:
        raise InitError(str(err)) from err
    merged = apply_wizard_defaults(current, choices)
    _atomic_write(project, render_project_yaml(merged))
    return InitResult(
        root=root,
        spec_path=spec_rel if (root / spec_rel).is_file() else Path(_PROJECT_FILE),
        written=(Path(_PROJECT_FILE),),
        notes=("updated existing codoc.yaml via interactive wizard",),
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
    fresh = load_template("gitignore")
    if not path.exists():
        _atomic_write(path, fresh)
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
