import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

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

    def test_each_command_prints_not_implemented_to_stderr(self) -> None:
        for command in cli.COMMANDS:
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as caught:
                    cli.main([command.name])
            self.assertEqual(caught.exception.code, 2)
            self.assertEqual(
                stderr.getvalue(),
                f"codoc {command.name}: not implemented\n",
            )

    def test_drift_alias_prints_validate_not_implemented(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                cli.main(["drift"])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(stderr.getvalue(), "codoc validate: not implemented\n")

    def test_aliases_point_at_existing_commands(self) -> None:
        by_name = {command.name: command for command in cli.COMMANDS}
        for command in cli.COMMANDS:
            for alias in command.aliases:
                self.assertNotIn(alias, by_name)
        validate = by_name["validate"]
        self.assertEqual(validate.aliases, ("drift",))

    def _assert_help_lists_commands(self, text: str) -> None:
        self.assertIn("usage: codoc", text)
        normalized = " ".join(text.split())
        for command in cli.COMMANDS:
            self.assertIn(command.name, text)
            self.assertIn(command.summary, normalized)
        self.assertIn("drift", text)


if __name__ == "__main__":
    unittest.main()
