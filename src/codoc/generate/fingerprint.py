"""Fingerprint generate inputs and warm-cache outcomes under `.codoc/cache/`."""

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from codoc.model.spec import SpecDocument

_CACHE_VERSION = 2


@dataclass(frozen=True, slots=True)
class CachedPage:
    page_id: str
    path: str
    action: str


def cache_path(root: Path, scope_dir: Path) -> Path:
    """Return `.codoc/cache/generate/<scope-key>.json` for one spec unit."""
    key = _scope_key(scope_dir)
    return root / ".codoc" / "cache" / "generate" / f"{key}.json"


def fingerprint_inputs(
    root: Path,
    *,
    spec_path: Path,
    doc: SpecDocument,
    source_paths: tuple[str, ...],
    scripts_dir: str,
    registry_entries: Sequence[tuple[str, str]] = (),
    llm_provider: str | None = None,
    llm_model: str | None = None,
    rewrite_stubs: bool = False,
) -> str:
    """
    Hash everything that can change generate output for a scope.

    Includes the owning spec, coverage sources, scripts dir contents, the merged
    page registry (id→path), and current page file bodies so hand edits and
    sibling-spec moves invalidate the warm cache.
    """
    hasher = hashlib.sha256()
    hasher.update(b"codoc-generate-v2\n")
    _feed_rel(hasher, root, spec_path.as_posix())
    for rel in sorted(set(source_paths)):
        hasher.update(f"src:{rel}\n".encode())
        _feed_rel(hasher, root, rel)
    hasher.update(f"scripts_dir:{scripts_dir}\n".encode())
    for rel in _scripts_tree(root, scripts_dir):
        hasher.update(f"script-tree:{rel}\n".encode())
        _feed_rel(hasher, root, rel)
    for page_id, page_path in sorted(registry_entries):
        hasher.update(f"registry:{page_id}:{page_path}\n".encode())
    for page in doc.pages():
        hasher.update(f"page:{page.id}:{page.path}\n".encode())
        _feed_rel(hasher, root, page.path)
    hasher.update(
        f"llm:{llm_provider or ''}:{llm_model or ''}:rewrite={int(rewrite_stubs)}\n".encode()
    )
    return hasher.hexdigest()


def read_cache(path: Path) -> tuple[str, tuple[CachedPage, ...]] | None:
    """Return (fingerprint, pages) when the cache file is valid."""
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != _CACHE_VERSION:
        return None
    digest = payload.get("fingerprint")
    pages_raw = payload.get("pages")
    if not isinstance(digest, str) or not isinstance(pages_raw, list):
        return None
    pages: list[CachedPage] = []
    for item in pages_raw:
        if not isinstance(item, dict):
            return None
        page_id = item.get("page_id")
        page_path = item.get("path")
        action = item.get("action")
        if not isinstance(page_id, str) or not isinstance(page_path, str):
            return None
        if not isinstance(action, str):
            return None
        pages.append(CachedPage(page_id=page_id, path=page_path, action=action))
    return digest, tuple(pages)


def write_cache(
    path: Path,
    *,
    fingerprint: str,
    pages: tuple[CachedPage, ...],
) -> None:
    """Persist a warm-cache entry for one scope."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": _CACHE_VERSION,
        "fingerprint": fingerprint,
        "pages": [asdict(page) for page in pages],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def cache_is_warm(
    root: Path,
    *,
    fingerprint: str,
    cached: tuple[str, tuple[CachedPage, ...]] | None,
) -> bool:
    """True when the fingerprint matches and every cached page file still exists."""
    if cached is None:
        return False
    digest, pages = cached
    if digest != fingerprint or not pages:
        return False
    return all((root / page.path).is_file() for page in pages)


def draft_skip_blocks_cache(notes: Iterable[str]) -> bool:
    """
    True when a draft/rewrite skip means the warm cache must not be written.

    Offline free CLI (provider unset) may still warm-cache. Skips that mean a
    later key/agent could change the page (missing key, agent, or model error)
    keep the entry cold so the next configured run can rewrite.
    """
    for note in notes:
        if note.startswith("draft skipped: llm.provider/model not set"):
            continue
        if note.startswith("draft skipped:"):
            return True
        if note.startswith("rewrite skipped:") and "existing page preserved" not in note:
            return True
    return False


def _scope_key(scope_dir: Path) -> str:
    raw = scope_dir.as_posix() if scope_dir != Path(".") else "_root"
    safe = raw.replace("/", "__")
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"{safe}-{digest}"


def _scripts_tree(root: Path, scripts_dir: str) -> tuple[str, ...]:
    base = root / scripts_dir
    if not base.is_dir():
        return ()
    found: list[str] = []
    for path in sorted(base.rglob("*")):
        if path.is_file():
            found.append(path.relative_to(root).as_posix())
    return tuple(found)


def _feed_rel(hasher: object, root: Path, rel: str) -> None:
    hasher.update(f"file:{rel}\n".encode())
    path = root / rel
    if not path.is_file():
        hasher.update(b"missing\n")
        return
    hasher.update(path.read_bytes())
    hasher.update(b"\n")
