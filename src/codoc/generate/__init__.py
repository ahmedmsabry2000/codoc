"""Type-aware docs generation helpers."""

from codoc.generate.ensure import PageOutcome, ensure_page
from codoc.generate.frontmatter import CodocFrontmatter, FrontmatterError, split_frontmatter

__all__ = [
    "CodocFrontmatter",
    "FrontmatterError",
    "PageOutcome",
    "ensure_page",
    "split_frontmatter",
]
