"""Type-aware docs generation helpers."""

from codoc.generate.ensure import PageOutcome, ensure_page
from codoc.generate.frontmatter import CodocFrontmatter, split_frontmatter

__all__ = [
    "CodocFrontmatter",
    "PageOutcome",
    "ensure_page",
    "split_frontmatter",
]
