import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from codoc.config import (
    ConfigError,
    EngineConfig,
    LlmConfig,
    PathsConfig,
    ProjectConfig,
    ValeConfig,
    load_project_config,
)


@contextmanager
def _file(text: str) -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as raw:
        path = Path(raw) / "codoc.yaml"
        path.write_text(text)
        yield path


_PROJECT = """\
engine: { name: zensical, docs_dir: docs, site_dir: site }
vale: { enabled: true }
llm: { provider: openai, model: gpt-4.1 }
paths: { scripts_dir: .codoc/scripts }
terms:
  - codoc
  - codoc
ignore:
  - node_modules
  - dist
  - node_modules
"""


class ConfigTests(unittest.TestCase):
    def test_empty_file_loads_defaults(self) -> None:
        for text in ("", "# comment only\n", "null\n", "~\n"):
            with self.subTest(text=text):
                with _file(text) as path:
                    loaded = load_project_config(path)
                self.assertEqual(loaded, ProjectConfig())

    def test_valid_project(self) -> None:
        with _file(_PROJECT) as path:
            loaded = load_project_config(path)
        self.assertEqual(
            loaded,
            ProjectConfig(
                engine=EngineConfig("zensical", "docs", "site"),
                vale=ValeConfig(True),
                llm=LlmConfig("openai", "gpt-4.1"),
                paths=PathsConfig(".codoc/scripts"),
                terms=("codoc", "codoc"),
                ignore_dirs=frozenset({"node_modules", "dist"}),
            ),
        )

    def test_omitted_keys_use_defaults(self) -> None:
        with _file("engine: {}\nllm: {}\nvale: {}\npaths: {}\n") as path:
            loaded = load_project_config(path)
        self.assertEqual(loaded.engine, EngineConfig())
        self.assertEqual(loaded.llm, LlmConfig(None, None))
        self.assertTrue(loaded.vale.enabled)
        self.assertEqual(loaded.paths.scripts_dir, ".codoc/scripts")
        self.assertEqual(loaded.terms, ())
        self.assertEqual(loaded.ignore_dirs, frozenset())

    def test_quoted_boolean_is_rejected(self) -> None:
        with _file('vale:\n  enabled: "true"\n') as path:
            with self.assertRaises(ConfigError) as caught:
                load_project_config(path)
        self.assertEqual(
            str(caught.exception),
            f"{path}: vale.enabled: expected a boolean",
        )

    def test_null_leaf_is_rejected(self) -> None:
        with _file("llm:\n  provider: null\n") as path:
            with self.assertRaises(ConfigError) as caught:
                load_project_config(path)
        self.assertEqual(
            str(caught.exception),
            f"{path}: llm.provider: expected a non-empty string",
        )

    def test_unknown_key_names_the_first_sorted_field(self) -> None:
        with _file("serve: true\nalpha: 1\n") as path:
            with self.assertRaises(ConfigError) as caught:
                load_project_config(path)
        self.assertEqual(
            str(caught.exception),
            f"{path}: document: unknown field 'alpha'",
        )

    def test_unknown_nested_key(self) -> None:
        with _file("engine:\n  port: 8000\n") as path:
            with self.assertRaises(ConfigError) as caught:
                load_project_config(path)
        self.assertEqual(
            str(caught.exception),
            f"{path}: engine: unknown field 'port'",
        )

    def test_ignore_entry_must_be_one_directory_name(self) -> None:
        for text in (
            "ignore:\n  - node_modules/pkg\n",
            "ignore:\n  - .\n",
            "ignore:\n  - ..\n",
            "ignore:\n  - ''\n",
        ):
            with self.subTest(text=text):
                with _file(text) as path:
                    with self.assertRaises(ConfigError) as caught:
                        load_project_config(path)
                self.assertEqual(
                    str(caught.exception),
                    f"{path}: ignore[0]: expected a single directory name",
                )

    def test_relative_path_rejects_parent_and_absolute(self) -> None:
        cases = {
            "engine:\n  docs_dir: ../docs\n": "engine.docs_dir",
            "engine:\n  docs_dir: /docs\n": "engine.docs_dir",
            "paths:\n  scripts_dir: ~/scripts\n": "paths.scripts_dir",
        }
        for text, field in cases.items():
            with self.subTest(field=field):
                with _file(text) as path:
                    with self.assertRaises(ConfigError) as caught:
                        load_project_config(path)
                self.assertEqual(
                    str(caught.exception),
                    f"{path}: {field}: expected a relative path",
                )

    def test_repeated_key_is_rejected(self) -> None:
        text = "engine:\n  name: zensical\n  name: other\n"
        with _file(text) as path:
            with self.assertRaises(ConfigError) as caught:
                load_project_config(path)
        message = str(caught.exception)
        self.assertIn(f"{path}: invalid YAML:", message)
        self.assertIn("duplicate key", message)

    def test_merge_key_is_rejected(self) -> None:
        text = "engine: &base\n  name: zensical\nvale:\n  <<: *base\n"
        with _file(text) as path:
            with self.assertRaises(ConfigError) as caught:
                load_project_config(path)
        self.assertIn("invalid YAML:", str(caught.exception))
        self.assertIn("merge key", str(caught.exception))

    def test_document_must_be_a_mapping(self) -> None:
        with _file("- codoc\n") as path:
            with self.assertRaises(ConfigError) as caught:
                load_project_config(path)
        self.assertEqual(str(caught.exception), f"{path}: document must be a mapping")

    def test_invalid_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "codoc.yaml"
            path.write_bytes(b"\xff")
            with self.assertRaises(ConfigError) as caught:
                load_project_config(path)
        self.assertIn(f"{path}: invalid UTF-8:", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
