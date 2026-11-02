import unittest
from pathlib import Path

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


class RegistryTests(unittest.TestCase):
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
        self.assertEqual(len(registry), 3)
        self.assertEqual(
            registry.entries,
            (
                RegistryEntry("cli-core.ref", "docs/cli.md", "auto-generated", other),
                RegistryEntry("guide", "docs/guide.md", "hybrid", owning),
                RegistryEntry("overview", "docs/overview.md", "manual", owning),
            ),
        )
        overview = registry.lookup("overview")
        self.assertEqual(overview.path, "docs/overview.md")
        self.assertEqual(overview.type, "manual")
        self.assertEqual(overview.spec_path, owning)
        guide = registry.lookup("guide")
        self.assertEqual(guide.path, "docs/guide.md")
        self.assertEqual(guide.type, "hybrid")
        self.assertEqual(guide.spec_path, owning)
        ref = registry.lookup("cli-core.ref")
        self.assertEqual(ref.path, "docs/cli.md")
        self.assertEqual(ref.type, "auto-generated")
        self.assertEqual(ref.spec_path, other)
        self.assertIn("guide", registry)
        self.assertNotIn("missing", registry)
        with self.assertRaises(KeyError):
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
            with self.assertRaises(SpecError) as caught:
                build_page_registry(((earlier, first), (later, second)))
        self.assertEqual(caught.exception.path, later)
        self.assertEqual(
            caught.exception.detail,
            f"duplicate page id 'overview' also in {earlier}",
        )

    def test_empty_registry(self) -> None:
        registry = build_page_registry(())
        self.assertEqual(len(registry), 0)
        self.assertEqual(registry.entries, ())
        self.assertNotIn("overview", registry)
        with self.assertRaises(KeyError):
            registry.lookup("overview")


if __name__ == "__main__":
    unittest.main()
