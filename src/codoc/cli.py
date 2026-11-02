import argparse
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    """One CLI name. implements is the behavior name. An alias repeats another command's name."""

    name: str
    summary: str
    implements: str


COMMANDS: tuple[Command, ...] = (
    Command("init", "Create codoc.yaml, a starter codoc.spec.yaml, docs/, and .codoc/scripts/.", "init"),
    Command("build", "Build the Zensical site.", "build"),
    Command("serve", "Serve the Zensical site locally.", "serve"),
    Command("generate", "Find every codoc.spec.yaml and write docs/.", "generate"),
    Command("validate", "Check docs with git as the staleness signal.", "validate"),
    Command("lint", "Run Vale.", "lint"),
    Command("status", "List discovered specs, scope directories, and page counts.", "status"),
    Command("clean", "Remove generated outputs.", "clean"),
    Command("drift", "Run validate.", "validate"),
)

_BY_NAME: dict[str, Command] = {command.name: command for command in COMMANDS}


def main(argv: list[str] | None = None) -> None:
    """Process boundary. None reads sys.argv. A list is the full argv after the program name."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        raise SystemExit(0)
    _not_implemented(_BY_NAME[args.command].implements)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codoc", description="Codoc command line tool.")
    sub = parser.add_subparsers(dest="command", required=False)
    for command in COMMANDS:
        sub.add_parser(command.name, help=command.summary)
    return parser


def _not_implemented(behavior: str) -> None:
    print(f"codoc {behavior}: not implemented", file=sys.stderr)
    raise SystemExit(2)
