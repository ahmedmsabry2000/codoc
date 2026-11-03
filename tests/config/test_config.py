from pathlib import Path

import pytest

from codoc.config import (
    ConfigError,
    EngineConfig,
    LlmConfig,
    PathsConfig,
    ProjectConfig,
    ValeConfig,
    load_project_config,
)
from tests.support.fs import yaml_file

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


class ConfigTests:
    @pytest.mark.parametrize("text", ["", "# comment only\n", "null\n", "~\n"])
    def test_empty_file_loads_defaults(self, text: str) -> None:
        with yaml_file(text) as path:
            assert load_project_config(path) == ProjectConfig()

    def test_valid_project(self) -> None:
        with yaml_file(_PROJECT) as path:
            loaded = load_project_config(path)
        assert loaded == ProjectConfig(
            engine=EngineConfig("zensical", "docs", "site", "Documentation"),
            vale=ValeConfig(True),
            llm=LlmConfig("openai", "gpt-4.1"),
            paths=PathsConfig(".codoc/scripts"),
            terms=("codoc", "codoc"),
            ignore_dirs=frozenset({"node_modules", "dist"}),
        )

    def test_omitted_keys_use_defaults(self) -> None:
        with yaml_file("engine: {}\nllm: {}\nvale: {}\npaths: {}\n") as path:
            loaded = load_project_config(path)
        assert loaded.engine == EngineConfig()
        assert loaded.llm == LlmConfig(None, None)
        assert loaded.vale.enabled
        assert loaded.paths.scripts_dir == ".codoc/scripts"
        assert loaded.terms == ()
        assert loaded.ignore_dirs == frozenset()

    def test_quoted_boolean_is_rejected(self) -> None:
        with (
            yaml_file('vale:\n  enabled: "true"\n') as path,
            pytest.raises(ConfigError) as caught,
        ):
            load_project_config(path)
        assert str(caught.value) == f"{path}: vale.enabled: expected a boolean"

    def test_null_leaf_is_rejected(self) -> None:
        with (
            yaml_file("llm:\n  provider: null\n") as path,
            pytest.raises(ConfigError) as caught,
        ):
            load_project_config(path)
        assert str(caught.value) == f"{path}: llm.provider: expected a non-empty string"

    def test_unknown_key_names_the_first_sorted_field(self) -> None:
        with (
            yaml_file("serve: true\nalpha: 1\n") as path,
            pytest.raises(ConfigError) as caught,
        ):
            load_project_config(path)
        assert str(caught.value) == f"{path}: document: unknown field 'alpha'"

    def test_unknown_nested_key(self) -> None:
        with (
            yaml_file("engine:\n  port: 8000\n") as path,
            pytest.raises(ConfigError) as caught,
        ):
            load_project_config(path)
        assert str(caught.value) == f"{path}: engine: unknown field 'port'"

    @pytest.mark.parametrize(
        "text",
        [
            "ignore:\n  - node_modules/pkg\n",
            "ignore:\n  - .\n",
            "ignore:\n  - ..\n",
            "ignore:\n  - ''\n",
        ],
    )
    def test_ignore_entry_must_be_one_directory_name(self, text: str) -> None:
        with yaml_file(text) as path, pytest.raises(ConfigError) as caught:
            load_project_config(path)
        assert str(caught.value) == f"{path}: ignore[0]: expected a single directory name"

    @pytest.mark.parametrize(
        ("text", "field"),
        [
            ("engine:\n  docs_dir: ../docs\n", "engine.docs_dir"),
            ("engine:\n  docs_dir: /docs\n", "engine.docs_dir"),
            ("paths:\n  scripts_dir: ~/scripts\n", "paths.scripts_dir"),
        ],
    )
    def test_relative_path_rejects_parent_and_absolute(self, text: str, field: str) -> None:
        with yaml_file(text) as path, pytest.raises(ConfigError) as caught:
            load_project_config(path)
        assert str(caught.value) == f"{path}: {field}: expected a relative path"

    def test_repeated_key_is_rejected(self) -> None:
        text = "engine:\n  name: zensical\n  name: other\n"
        with yaml_file(text) as path, pytest.raises(ConfigError) as caught:
            load_project_config(path)
        message = str(caught.value)
        assert f"{path}: invalid YAML:" in message
        assert "duplicate key" in message

    def test_merge_key_is_rejected(self) -> None:
        text = "engine: &base\n  name: zensical\nvale:\n  <<: *base\n"
        with yaml_file(text) as path, pytest.raises(ConfigError) as caught:
            load_project_config(path)
        assert "invalid YAML:" in str(caught.value)
        assert "merge key" in str(caught.value)

    def test_document_must_be_a_mapping(self) -> None:
        with yaml_file("- codoc\n") as path, pytest.raises(ConfigError) as caught:
            load_project_config(path)
        assert str(caught.value) == f"{path}: document must be a mapping"

    def test_invalid_utf8(self, tmp_dir: Path) -> None:
        path = tmp_dir / "codoc.yaml"
        path.write_bytes(b"\xff")
        with pytest.raises(ConfigError) as caught:
            load_project_config(path)
        assert f"{path}: invalid UTF-8:" in str(caught.value)
