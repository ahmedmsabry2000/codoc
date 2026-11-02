import argparse
import sys
from dataclasses import dataclass

from codoc.discover import DiscoverError, SpecUnit, discover


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
    if behavior == "status":
        _run_status()
        return
    _not_implemented(behavior)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codoc", description="Codoc command line tool.")
    sub = parser.add_subparsers(dest="command", required=False)
    for command in COMMANDS:
        sub.add_parser(
            command.name,
            help=command.summary,
            aliases=list(command.aliases),
        )
    return parser


def _run_status() -> None:
    try:
        units = discover()
    except DiscoverError as err:
        print(f"codoc status: {err}", file=sys.stderr)
        raise SystemExit(1) from err
    _print_status(units)


def _print_status(units: tuple[SpecUnit, ...]) -> None:
    print("spec_path\tscope_dir\tpages")
    for unit in units:
        print(f"{unit.spec_path.as_posix()}\t{unit.scope_dir.as_posix()}\tn/a")


def _not_implemented(behavior: str) -> None:
    # Exit 2 is a local stub convention so scripts cannot treat NYI as success.
    print(f"codoc {behavior}: not implemented", file=sys.stderr)
    raise SystemExit(2)
