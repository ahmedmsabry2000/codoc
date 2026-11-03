"""Harvest project terminology from docs into a Codoc-owned learned vocab."""

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Machine-local under gitignored `.codoc/*`. Re-harvest on lint/codegen rebuilds
# from docs, so CI does not need this file committed.
LEARNED_REL = Path(".codoc") / "vocab" / "learned.txt"

_LEARNED_HEADER = "# Learned by codoc from docs. Seed terms stay in codoc.yaml `terms:`.\n"

# Deterministic POC heuristics — no LLM.
_CAMEL = re.compile(r"\b[A-Z][a-z0-9]*(?:[A-Z][a-z0-9]+)+\b")
_SNAKE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_QUOTED = re.compile(r'"([A-Za-z][A-Za-z0-9_.-]{1,})"')
_PROPER = re.compile(r"\b[A-Z][a-z]{2,}\b")
_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")

_COMMON_PROPER = frozenset(
    {
        "The",
        "This",
        "That",
        "These",
        "Those",
        "When",
        "Where",
        "What",
        "Which",
        "While",
        "With",
        "From",
        "For",
        "And",
        "But",
        "Not",
        "You",
        "Your",
        "Our",
        "Their",
        "Each",
        "Every",
        "Some",
        "Any",
        "All",
        "None",
        "Here",
        "There",
        "Then",
        "Than",
        "Also",
        "After",
        "Before",
        "Above",
        "Below",
        "Under",
        "Over",
        "Into",
        "Onto",
        "About",
        "Between",
        "Through",
        "During",
        "Without",
        "Within",
        "Using",
        "Use",
        "Used",
        "Note",
        "Notes",
        "See",
        "Example",
        "Examples",
        "Warning",
        "Important",
        "Default",
        "Optional",
        "Required",
        "True",
        "False",
        "Null",
        "Markdown",
        "Python",
        "Linux",
        "Windows",
        "Macos",
        "Http",
        "Https",
        "Json",
        "Yaml",
        "Toml",
    }
)


@dataclass(frozen=True, slots=True)
class VocabGrowth:
    """Result of merging a docs harvest into `.codoc/vocab/learned.txt`."""

    learned_path: Path
    learned: tuple[str, ...]
    added: tuple[str, ...]


def learned_path(root: Path) -> Path:
    return root / LEARNED_REL


def read_learned(root: Path) -> tuple[str, ...]:
    path = learned_path(root)
    if not path.is_file():
        return ()
    terms: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        terms.append(stripped)
    return _ordered_unique(terms)


def write_learned(root: Path, terms: tuple[str, ...]) -> Path:
    path = learned_path(root)
    body = "".join(f"{term}\n" for term in _ordered_unique(terms))
    _atomic_write(path, f"{_LEARNED_HEADER}{body}")
    return path


def merge_accept_terms(seed: tuple[str, ...], learned: tuple[str, ...]) -> tuple[str, ...]:
    """Seed first (curated order), then learned terms not already present."""
    seen: set[str] = set()
    out: list[str] = []
    for term in (*seed, *learned):
        if term in seen:
            continue
        seen.add(term)
        out.append(term)
    return tuple(out)


def harvest_docs(docs_dir: Path) -> tuple[str, ...]:
    """Collect candidate terms from Markdown under docs_dir (deterministic POC)."""
    if not docs_dir.is_dir():
        return ()
    camel: set[str] = set()
    snake: set[str] = set()
    quoted: set[str] = set()
    inline: set[str] = set()
    proper_counts: dict[str, int] = {}
    for path in sorted(docs_dir.rglob("*.md")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        camel.update(_CAMEL.findall(text))
        snake.update(_SNAKE.findall(text))
        for match in _QUOTED.findall(text):
            if _TOKEN.fullmatch(match):
                quoted.add(match)
        for match in _INLINE_CODE.findall(text):
            token = match.strip()
            if _TOKEN.fullmatch(token) and _looks_like_term(token):
                inline.add(token)
        for match in _PROPER.findall(text):
            if match in _COMMON_PROPER:
                continue
            proper_counts[match] = proper_counts.get(match, 0) + 1
    proper = {word for word, count in proper_counts.items() if count >= 2}
    return _ordered_unique((*camel, *snake, *quoted, *inline, *proper))


def grow_learned(
    root: Path,
    docs_dir: Path,
    *,
    seed: tuple[str, ...] = (),
) -> VocabGrowth:
    """Union harvest into learned vocab; never rewrite seed terms in codoc.yaml."""
    seed_set = set(seed)
    existing = read_learned(root)
    harvested = tuple(term for term in harvest_docs(root / docs_dir) if term not in seed_set)
    before = set(existing)
    merged = _ordered_unique((*existing, *harvested))
    added = tuple(term for term in merged if term not in before)
    write_learned(root, merged)
    return VocabGrowth(learned_path=LEARNED_REL, learned=merged, added=added)


def _looks_like_term(token: str) -> bool:
    if len(token) < 2:
        return False
    if _CAMEL.fullmatch(token) or _SNAKE.fullmatch(token):
        return True
    if "." in token or "-" in token or "_" in token:
        return True
    # Capitalized product-like token in backticks (e.g. `Codoc`, `Zensical`).
    return token[0].isupper() and token.isalpha() and token not in _COMMON_PROPER


def _ordered_unique(terms: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for term in sorted(terms):
        if term in seen:
            continue
        seen.add(term)
        out.append(term)
    return tuple(out)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
