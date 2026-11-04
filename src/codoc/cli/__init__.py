import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from codoc.commands.clean import CleanError, run_clean
from codoc.commands.generate import GenerateError, run_generate
from codoc.commands.init import InitError, run_init
from codoc.commands.lint import LintError, run_lint
from codoc.commands.recommend import RecommendError, run_recommend
from codoc.commands.site import SiteError, run_build, run_serve
from codoc.commands.status import StatusError, run_status
from codoc.commands.validate import ValidateError, run_validate


@dataclass(frozen=True)
class Command:
    """One CLI command. aliases share this command's not-implemented behavior."""

    name: str
    summary: str
    aliases: tuple[str, ...] = ()


COMMANDS: tuple[Command, ...] = (
    Command(
        "init",
        "Create codoc.yaml, a starter codoc.spec.yaml, docs/, and .codoc/scripts/.",
    ),
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
    Command(
        "recommend",
        "Suggest src/ packages that may need a nested codoc.spec.yaml.",
    ),
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
    if behavior == "recommend":
        _run_recommend()
        return
    if behavior == "build":
        _run_build()
        return
    if behavior == "serve":
        _run_serve()
        return
    if behavior == "lint":
        _run_lint(learn=not bool(getattr(args, "no_learn", False)))
        return
    if behavior == "clean":
        _run_clean()
        return
    if behavior == "generate":
        _run_generate(
            scope=getattr(args, "scope", None),
            no_cache=bool(getattr(args, "no_cache", False)),
        )
        return
    if behavior == "validate":
        _run_validate()
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
        if command.name == "lint":
            subparser.add_argument(
                "--no-learn",
                action="store_true",
                help="Do not harvest new terms from docs into .codoc/vocab/learned.txt.",
            )
        if command.name == "generate":
            subparser.add_argument(
                "--scope",
                metavar="DIR",
                help="Regenerate only the spec whose scope_dir matches DIR.",
            )
            subparser.add_argument(
                "--no-cache",
                action="store_true",
                help="Ignore and rewrite the warm generate cache under .codoc/cache/.",
            )
    return parser


def _run_init(*, force: bool) -> None:
    try:
        result = run_init(Path.cwd(), force=force)
    except InitError as err:
        for line in str(err).splitlines():
            print(f"codoc init: {line}", file=sys.stderr)
        raise SystemExit(1) from err
    for note in result.notes:
        print(f"codoc init: {note}", file=sys.stderr)
    for path in result.written:
        print(path.as_posix())


def _run_build() -> None:
    try:
        result = run_build(Path.cwd())
    except SiteError as err:
        print(f"codoc build: {err}", file=sys.stderr)
        raise SystemExit(1) from err
    for note in result.notes:
        print(f"codoc build: {note}", file=sys.stderr)
    print(result.site_dir.as_posix())


def _run_serve() -> None:
    try:
        result = run_serve(Path.cwd())
    except SiteError as err:
        print(f"codoc serve: {err}", file=sys.stderr)
        raise SystemExit(1) from err
    for note in result.notes:
        print(f"codoc serve: {note}", file=sys.stderr)
    print(f"pid\t{result.pid}")
    print(f"url\thttp://{result.dev_addr}/")
    print(f"log\t{result.log_file.as_posix()}")
    print(f"pidfile\t{result.pid_file.as_posix()}")


def _run_lint(*, learn: bool) -> None:
    try:
        result = run_lint(Path.cwd(), learn=learn)
    except LintError as err:
        print(f"codoc lint: {err}", file=sys.stderr)
        raise SystemExit(1) from err
    for note in result.notes:
        print(f"codoc lint: {note}", file=sys.stderr)
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


def _run_generate(*, scope: str | None, no_cache: bool = False) -> None:
    try:
        result = run_generate(Path.cwd(), scope=scope, no_cache=no_cache)
    except GenerateError as err:
        print(f"codoc generate: {err}", file=sys.stderr)
        raise SystemExit(1) from err
    for note in result.notes:
        print(f"codoc generate: {note}", file=sys.stderr)
    print("page_id\tpath\taction")
    for page in result.pages:
        print(f"{page.page_id}\t{page.path.as_posix()}\t{page.action}")


def _run_validate() -> None:
    try:
        result = run_validate(Path.cwd())
    except ValidateError as err:
        print(f"codoc validate: {err}", file=sys.stderr)
        raise SystemExit(1) from err
    for note in result.notes:
        print(f"codoc validate: {note}", file=sys.stderr)
    if result.rag_path is not None:
        print(f"rag\t{result.rag_path.as_posix()}")
    if result.candidates:
        print("candidates\t" + ",".join(result.candidates))
    print("severity\tcode\tpath\tmessage")
    for finding in result.findings:
        path = finding.path or ""
        print(f"{finding.severity}\t{finding.code}\t{path}\t{finding.message}")
    if not result.ok:
        raise SystemExit(1)


def _run_status() -> None:
    try:
        result = run_status(Path.cwd())
    except StatusError as err:
        print(f"codoc status: {err}", file=sys.stderr)
        raise SystemExit(1) from err
    print("spec_path\tscope_dir\tpages")
    for row in result.rows:
        print(f"{row.spec_path.as_posix()}\t{row.scope_dir.as_posix()}\t{row.pages}")
    print(f"registry_pages\t{result.registry_pages}")


def _run_recommend() -> None:
    try:
        result = run_recommend(Path.cwd())
    except RecommendError as err:
        print(f"codoc recommend: {err}", file=sys.stderr)
        raise SystemExit(1) from err
    for note in result.notes:
        print(f"codoc recommend: {note}", file=sys.stderr)
    print("scope_dir\trationale")
    for row in result.rows:
        print(f"{row.scope_dir.as_posix()}\t{row.rationale}")


def _not_implemented(behavior: str) -> None:
    # Exit 2 is a local stub convention so scripts cannot treat NYI as success.
    print(f"codoc {behavior}: not implemented", file=sys.stderr)
    raise SystemExit(2)
