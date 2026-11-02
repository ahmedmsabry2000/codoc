import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import codoc.cli as cli


class CliTests(unittest.TestCase):
    def test_bare_invocation_prints_help_and_exits_zero(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as caught:
                cli.main([])
        self.assertEqual(caught.exception.code, 0)
        self._assert_help_lists_commands(stdout.getvalue())

    def test_help_flag_exits_zero(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as caught:
                cli.main(["--help"])
        self.assertEqual(caught.exception.code, 0)
        self._assert_help_lists_commands(stdout.getvalue())

    def test_each_command_prints_its_behavior_to_stderr(self) -> None:
        for command in cli.COMMANDS:
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as caught:
                    cli.main([command.name])
            self.assertEqual(caught.exception.code, 2)
            self.assertEqual(
                stderr.getvalue(),
                f"codoc {command.implements}: not implemented\n",
            )

    def test_drift_prints_validate_not_implemented(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                cli.main(["drift"])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(stderr.getvalue(), "codoc validate: not implemented\n")

    def test_implements_names_a_command_that_implements_itself(self) -> None:
        by_name = {command.name: command for command in cli.COMMANDS}
        for command in cli.COMMANDS:
            target = by_name[command.implements]
            self.assertEqual(target.implements, target.name)
        drift = by_name["drift"]
        self.assertEqual(drift.implements, "validate")

    def test_src_codoc_has_no_subpackages(self) -> None:
        root = Path(__file__).resolve().parents[1] / "src" / "codoc"
        directories = [
            path
            for path in root.rglob("*")
            if path.is_dir() and "__pycache__" not in path.parts
        ]
        self.assertEqual(directories, [])
        inits = [
            path
            for path in root.rglob("__init__.py")
            if "__pycache__" not in path.parts
        ]
        self.assertEqual(inits, [root / "__init__.py"])

    def _assert_help_lists_commands(self, text: str) -> None:
        self.assertIn("usage: codoc", text)
        usage_choices = "{" + ",".join(command.name for command in cli.COMMANDS) + "}"
        self.assertIn(usage_choices, text)
        normalized = " ".join(text.split())
        for command in cli.COMMANDS:
            self.assertIn(command.summary, normalized)


if __name__ == "__main__":
    unittest.main()
