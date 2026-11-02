import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from codoc.clean_cmd import CleanError, run_clean
from codoc.config import ConfigError
from codoc.discover import DiscoverError, discover, git_root
from codoc.init_cmd import InitError, run_init
from codoc.lint_cmd import LintError, run_lint
from codoc.registry import build_page_registry
from codoc.site_cmd import SiteError, run_build, run_serve
from codoc.spec import SpecDocument, SpecError, load_spec


@dataclass(frozen=True)
class Command:
    """One CLI command. aliases share this command's not-implemented behavior."""

    name: str
    summary: str
    aliases: tuple[str, ...] = ()


COMMANDS: tuple[Command, ...] = (
    Command("init", "Create codoc.yaml, a starter codoc.spec.yaml, docs/, and .codoc/scripts/."),
    Command("build", "Build the Zensical site."),
    Command("serve", "Serve the Zensical site locally."),
    Command("generate", "Find every codoc.spec.yaml and write docs/."),
    Command(
        "validate",
        "Check docs with git as the staleness signal.",
        aliases=("drift",),
    ),
    Command("lint", "Run Vale."),
    Command("status", "List discovered specs, scope dirs, and page counts."),
    Command("clean", "Remove generated outputs."),
)

# argparse may set dest to the alias the user typed. Map back to the command name.
_BEHAVIOR_BY_TOKEN: dict[str, str] = {}
for _command in COMMANDS:
    _BEHAVIOR_BY_TOKEN[_command.name] = _command.name
    for _alias in _command.aliases:
        _BEHAVIOR_BY_TOKEN[_alias] = _command.name


def main(argv: list[str] | None = None) -> None:
    """Process boundary. None reads sys.argv. A list is the full argv after the program name."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        raise SystemExit(0)
    behavior = _BEHAVIOR_BY_TOKEN[args.command]
    if behavior == "init":
        _run_init(force=bool(getattr(args, "force", False)))
        return
    if behavior == "status":
        _run_status()
        return
    if behavior == "build":
        _run_build()
        return
    if behavior == "serve":
        _run_serve()
        return
    if behavior == "lint":
        _run_lint()
        return
    if behavior == "clean":
        _run_clean()
        return
    _not_implemented(behavior)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codoc", description="Codoc command line tool.")
    sub = parser.add_subparsers(dest="command", required=False)
    for command in COMMANDS:
        subparser = sub.add_parser(
            command.name,
            help=command.summary,
            aliases=list(command.aliases),
        )
        if command.name == "init":
            subparser.add_argument(
                "--force",
                action="store_true",
                help="Overwrite codoc.yaml, the starter spec, and docs/index.md.",
            )
    return parser


def _run_init(*, force: bool) -> None:
    try:
        result = run_init(Path.cwd(), force=force)
    except InitError as err:
        for line in str(err).splitlines():
            print(f"codoc init: {line}", file=sys.stderr)
        raise SystemExit(1) from err
    for path in result.written:
        print(path.as_posix())


def _run_build() -> None:
    try:
        result = run_build(Path.cwd())
    except SiteError as err:
        print(f"codoc build: {err}", file=sys.stderr)
        raise SystemExit(1) from err
    print(result.site_dir.as_posix())


def _run_serve() -> None:
    try:
        result = run_serve(Path.cwd())
    except SiteError as err:
        print(f"codoc serve: {err}", file=sys.stderr)
        raise SystemExit(1) from err
    print(f"pid\t{result.pid}")
    print(f"url\thttp://{result.dev_addr}/")
    print(f"log\t{result.log_file.as_posix()}")
    print(f"pidfile\t{result.pid_file.as_posix()}")


def _run_lint() -> None:
    try:
        result = run_lint(Path.cwd())
    except LintError as err:
        print(f"codoc lint: {err}", file=sys.stderr)
        raise SystemExit(1) from err
    if result.skipped:
        print("codoc lint: vale disabled", file=sys.stderr)
        return
    print(result.docs_dir.as_posix())


def _run_clean() -> None:
    try:
        result = run_clean(Path.cwd())
    except CleanError as err:
        print(f"codoc clean: {err}", file=sys.stderr)
        raise SystemExit(1) from err
    if result.stopped_serve:
        print("stopped\tserve")
    for path in result.removed:
        print(path.as_posix())


def _run_status() -> None:
    try:
        root = git_root(Path.cwd())
        units = discover(root)
        loaded: list[tuple[Path, SpecDocument]] = []
        for unit in units:
            spec_path = root / unit.spec_path
            loaded.append((spec_path, load_spec(spec_path)))
        registry = build_page_registry(loaded)
    except (DiscoverError, ConfigError, SpecError) as err:
        print(f"codoc status: {err}", file=sys.stderr)
        raise SystemExit(1) from err
    print("spec_path\tscope_dir\tpages")
    for unit, (_, doc) in zip(units, loaded, strict=True):
        line = f"{unit.spec_path.as_posix()}\t{unit.scope_dir.as_posix()}\t{doc.page_count}"
        print(line)
    print(f"registry_pages\t{len(registry)}")


def _not_implemented(behavior: str) -> None:
    # Exit 2 is a local stub convention so scripts cannot treat NYI as success.
    print(f"codoc {behavior}: not implemented", file=sys.stderr)
    raise SystemExit(2)
