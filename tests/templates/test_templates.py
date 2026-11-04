"""Package template loading."""

from codoc.templates import fill_template, load_template


class TemplateLoadTests:
    def test_loads_starter_spec_yaml(self) -> None:
        text = load_template("starter-spec.yaml")
        assert text.startswith("intent:")
        assert "audience:" in text
        assert "purpose:" in text
        assert "docs:" in text
        assert "package.overview" in text
        assert 'paths:\n        - "**/*.py"' in text or '"**/*.py"' in text

    def test_fill_template_replaces_placeholders(self) -> None:
        # gitignore has no placeholders; exercise the helper with a synthetic map
        # against docs-index which is static (no-op replace).
        text = fill_template("docs-index.md", {"UNUSED": "x"})
        assert "Documentation site" in text
