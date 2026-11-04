"""Package-data scaffold templates (YAML/Markdown/scripts — not string literals)."""

from importlib import resources
from pathlib import Path


def load_template(name: str) -> str:
    """Return the UTF-8 text of a file under `codoc.templates`."""
    root = resources.files("codoc.templates")
    path = root.joinpath(name)
    with resources.as_file(path) as located:
        text = Path(located).read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    return text


def fill_template(name: str, mapping: dict[str, str] | None = None) -> str:
    """
    Load a template and apply optional `{{KEY}}` replacements.

    Keys must be simple identifiers. Values are inserted verbatim (no YAML
    construction via f-strings).
    """
    text = load_template(name)
    if not mapping:
        return text
    for key, value in mapping.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text
