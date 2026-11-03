from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from codoc.model.spec import (
    Coverage,
    CoverageBlock,
    Link,
    Page,
    Placeholder,
    SpecDocument,
    SpecError,
    load_spec,
)
from tests.support.tmpdir import temporary_directory


@contextmanager
def _file(text: str, name: str = "codoc.spec.yaml") -> Iterator[Path]:
    with temporary_directory() as raw:
        path = Path(raw) / name
        path.write_text(text)
        yield path


_SPEC = """\
docs:
  - id: overview
    type: manual
    path: docs/overview.md
  - id: build-serve-loop
    type: hybrid
    path: docs/guides/build-serve.md
    canonical: build-serve-loop
    links:
      - id: cli-core.ref
        label: CLI reference
    placeholders:
      - id: command-table
        script: .codoc/scripts/inject_command_table.py
coverage:
  source:
    - id: cli-core
      type: auto-generated
      paths: ["**/*.py"]
      docs:
        - id: cli-core.ref
          path: docs/reference/cli/index.md
          script: .codoc/scripts/gen_api_ref.py
          links:
            - id: build-serve-loop
              label: Build & serve guide
  features: []
"""


class SpecTests:
    def test_empty_spec_has_no_pages(self) -> None:
        for text in ("", "# comment\n", "null\n"):
            with _file(text) as path:
                loaded = load_spec(path)
            assert loaded == SpecDocument()
            assert loaded.page_count == 0
            assert loaded.pages() == ()

    def test_valid_spec(self) -> None:
        with _file(_SPEC) as path:
            loaded = load_spec(path)
        assert loaded.docs == (
            Page("overview", "manual", "docs/overview.md"),
            Page(
                "build-serve-loop",
                "hybrid",
                "docs/guides/build-serve.md",
                canonical="build-serve-loop",
                links=(Link("cli-core.ref", "CLI reference"),),
                placeholders=(
                    Placeholder("command-table", ".codoc/scripts/inject_command_table.py"),
                ),
            ),
        )
        assert loaded.coverage == Coverage(
            source=(
                CoverageBlock(
                    "cli-core",
                    "auto-generated",
                    ("**/*.py",),
                    docs=(
                        Page(
                            "cli-core.ref",
                            "auto-generated",
                            "docs/reference/cli/index.md",
                            links=(Link("build-serve-loop", "Build & serve guide"),),
                            script=".codoc/scripts/gen_api_ref.py",
                        ),
                    ),
                ),
            ),
        )
        assert tuple(page.id for page in loaded.pages()) == (
            "overview",
            "build-serve-loop",
            "cli-core.ref",
        )
        assert loaded.pages()[2].type == "auto-generated"
        assert loaded.page_count == 3

    def test_explicit_nested_type_must_match_the_block(self) -> None:
        text = "\n".join(
            (
                "coverage:",
                "  source:",
                "    - id: cli-core",
                "      type: auto-generated",
                "      paths: []",
                "      docs:",
                "        - id: cli-core.ref",
                "          type: auto-generated",
                "          path: docs/reference/cli/index.md",
                "",
            )
        )
        with _file(text) as path:
            loaded = load_spec(path)
        assert loaded.pages()[0].type == "auto-generated"
        assert loaded.pages()[0].script is None

    def test_top_level_page_requires_type(self) -> None:
        text = "\n".join(
            (
                "docs:",
                "  - id: overview",
                "    path: docs/overview.md",
                "",
            )
        )
        with _file(text) as path, pytest.raises(SpecError) as caught:
            load_spec(path)
        assert str(caught.value) == f"{path}: docs[0]: missing 'type'"

    def test_missing_required_field(self) -> None:
        text = "\n".join(
            (
                "docs:",
                "  - id: overview",
                "    type: manual",
                "",
            )
        )
        with _file(text) as path, pytest.raises(SpecError) as caught:
            load_spec(path)
        assert str(caught.value) == f"{path}: docs[0]: missing 'path'"

    def test_coverage_block_requires_paths(self) -> None:
        text = "\n".join(
            (
                "coverage:",
                "  source:",
                "    - id: cli-core",
                "      type: manual",
                "",
            )
        )
        with _file(text) as path, pytest.raises(SpecError) as caught:
            load_spec(path)
        assert str(caught.value) == f"{path}: coverage.source[0]: missing 'paths'"

    def test_invalid_type(self) -> None:
        text = "\n".join(
            (
                "docs:",
                "  - id: overview",
                "    type: essay",
                "    path: docs/overview.md",
                "",
            )
        )
        with _file(text) as path, pytest.raises(SpecError) as caught:
            load_spec(path)
        assert (
            str(caught.value) == f"{path}: docs[0].type: expected manual, hybrid, or auto-generated"
        )

    def test_nested_type_must_equal_the_block_type(self) -> None:
        text = "\n".join(
            (
                "coverage:",
                "  source:",
                "    - id: cli-core",
                "      type: auto-generated",
                "      paths: []",
                "      docs:",
                "        - id: cli-core.ref",
                "          type: manual",
                "          path: docs/reference/cli/index.md",
                "",
            )
        )
        with _file(text) as path, pytest.raises(SpecError) as caught:
            load_spec(path)
        assert (
            str(caught.value) == f"{path}: coverage.source[0].docs[0].type: expected auto-generated"
        )

    def test_unknown_key(self) -> None:
        text = "\n".join(
            (
                "docs:",
                "  - id: overview",
                "    type: manual",
                "    path: docs/overview.md",
                "    owner: docs",
                "",
            )
        )
        with _file(text) as path, pytest.raises(SpecError) as caught:
            load_spec(path)
        assert str(caught.value) == f"{path}: docs[0]: unknown field 'owner'"

    def test_script_and_placeholders_follow_type(self) -> None:
        script = "\n".join(
            (
                "docs:",
                "  - id: overview",
                "    type: manual",
                "    path: docs/overview.md",
                "    script: .codoc/scripts/gen.py",
                "",
            )
        )
        with _file(script) as path, pytest.raises(SpecError) as caught:
            load_spec(path)
        assert (
            str(caught.value) == f"{path}: docs[0].script: allowed only when type is auto-generated"
        )
        placeholders = "\n".join(
            (
                "docs:",
                "  - id: overview",
                "    type: manual",
                "    path: docs/overview.md",
                "    placeholders:",
                "      - id: slot",
                "        script: .codoc/scripts/fill.py",
                "",
            )
        )
        with _file(placeholders) as path, pytest.raises(SpecError) as caught:
            load_spec(path)
        assert (
            str(caught.value) == f"{path}: docs[0].placeholders: allowed only when type is hybrid"
        )

    def test_duplicate_page_id_in_one_file(self) -> None:
        text = "\n".join(
            (
                "docs:",
                "  - id: overview",
                "    type: manual",
                "    path: docs/overview.md",
                "  - id: overview",
                "    type: hybrid",
                "    path: docs/other.md",
                "",
            )
        )
        with _file(text) as path, pytest.raises(SpecError) as caught:
            load_spec(path)
        assert str(caught.value) == f"{path}: docs[1].id: duplicate page id 'overview'"

    def test_duplicate_page_id_in_a_coverage_block(self) -> None:
        text = "\n".join(
            (
                "docs:",
                "  - id: overview",
                "    type: manual",
                "    path: docs/overview.md",
                "coverage:",
                "  features:",
                "    - id: cli-core",
                "      type: manual",
                "      paths: []",
                "      docs:",
                "        - id: overview",
                "          path: docs/other.md",
                "",
            )
        )
        with _file(text) as path, pytest.raises(SpecError) as caught:
            load_spec(path)
        assert (
            str(caught.value)
            == f"{path}: coverage.features[0].docs[0].id: duplicate page id 'overview'"
        )

    def test_duplicate_coverage_id(self) -> None:
        text = "\n".join(
            (
                "coverage:",
                "  source:",
                "    - id: cli-core",
                "      type: manual",
                "      paths: []",
                "  features:",
                "    - id: cli-core",
                "      type: hybrid",
                "      paths: []",
                "",
            )
        )
        with _file(text) as path, pytest.raises(SpecError) as caught:
            load_spec(path)
        assert (
            str(caught.value)
            == f"{path}: coverage.features[0].id: duplicate coverage id 'cli-core'"
        )

    def test_block_id_may_match_a_page_id(self) -> None:
        text = "\n".join(
            (
                "docs:",
                "  - id: cli-core",
                "    type: manual",
                "    path: docs/overview.md",
                "coverage:",
                "  source:",
                "    - id: cli-core",
                "      type: manual",
                "      paths: []",
                "",
            )
        )
        with _file(text) as path:
            loaded = load_spec(path)
        assert loaded.page_count == 1
        assert loaded.coverage.source[0].id == "cli-core"

    def test_repeated_key_is_rejected(self) -> None:
        text = "docs:\n  - id: overview\n    id: other\n    type: manual\n    path: docs/a.md\n"
        with _file(text) as path, pytest.raises(SpecError) as caught:
            load_spec(path)
        message = str(caught.value)
        assert f"{path}: invalid YAML:" in message
        assert "duplicate key" in message

    def test_page_path_must_be_relative(self) -> None:
        text = "\n".join(
            (
                "docs:",
                "  - id: overview",
                "    type: manual",
                "    path: /docs/overview.md",
                "",
            )
        )
        with _file(text) as path, pytest.raises(SpecError) as caught:
            load_spec(path)
        assert str(caught.value) == f"{path}: docs[0].path: expected a relative path"
