from pathlib import Path

import pytest

from codoc.model.registry import RegistryEntry, build_page_registry
from codoc.model.spec import (
    Coverage,
    CoverageBlock,
    Page,
    SpecDocument,
    SpecError,
    load_spec,
)
from tests.support.tmpdir import temporary_directory


class RegistryTests:
    def test_merge_lookup_returns_path_type_and_owning_spec(self) -> None:
        owning = Path("src/pkg/codoc.spec.yaml")
        other = Path("src/pkg/cli/codoc.spec.yaml")
        first = SpecDocument(
            docs=(
                Page("overview", "manual", "docs/overview.md"),
                Page("guide", "hybrid", "docs/guide.md"),
            ),
        )
        second = SpecDocument(
            coverage=Coverage(
                source=(
                    CoverageBlock(
                        "cli-core",
                        "auto-generated",
                        ("src/cli/**",),
                        docs=(Page("cli-core.ref", "auto-generated", "docs/cli.md"),),
                    ),
                ),
            ),
        )
        registry = build_page_registry(((owning, first), (other, second)))
        assert len(registry) == 3
        assert registry.entries == (
            RegistryEntry("cli-core.ref", "docs/cli.md", "auto-generated", other),
            RegistryEntry("guide", "docs/guide.md", "hybrid", owning),
            RegistryEntry("overview", "docs/overview.md", "manual", owning),
        )
        overview = registry.lookup("overview")
        assert overview.path == "docs/overview.md"
        assert overview.type == "manual"
        assert overview.spec_path == owning
        guide = registry.lookup("guide")
        assert guide.path == "docs/guide.md"
        assert guide.type == "hybrid"
        assert guide.spec_path == owning
        ref = registry.lookup("cli-core.ref")
        assert ref.path == "docs/cli.md"
        assert ref.type == "auto-generated"
        assert ref.spec_path == other
        assert "guide" in registry
        assert "missing" not in registry
        with pytest.raises(KeyError):
            registry.lookup("missing")

    def test_duplicate_page_id_across_specs_fails(self) -> None:
        text = "\n".join(
            (
                "docs:",
                "  - id: overview",
                "    type: manual",
                "    path: docs/overview.md",
                "",
            )
        )
        with temporary_directory() as root:
            earlier = root / "src" / "my_project" / "codoc.spec.yaml"
            later = root / "src" / "my_project" / "cli" / "codoc.spec.yaml"
            earlier.parent.mkdir(parents=True)
            later.parent.mkdir(parents=True)
            earlier.write_text(text)
            later.write_text(text)
            first = load_spec(earlier)
            second = load_spec(later)
            with pytest.raises(SpecError) as caught:
                build_page_registry(((earlier, first), (later, second)))
        assert caught.value.path == later
        assert caught.value.detail == f"duplicate page id 'overview' also in {earlier}"

    def test_empty_registry(self) -> None:
        registry = build_page_registry(())
        assert len(registry) == 0
        assert registry.entries == ()
        assert "overview" not in registry
        with pytest.raises(KeyError):
            registry.lookup("overview")
