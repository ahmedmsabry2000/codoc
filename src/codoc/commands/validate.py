"""Git-first validate with structural checks, RAG index, and optional Stage D."""

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from codoc.config import ConfigError, LlmConfig, load_project_config
from codoc.coverage import expand_coverage_paths
from codoc.discover import DiscoverError, SpecUnit, child_scopes, discover, git_root
from codoc.generate.frontmatter import FrontmatterError, split_frontmatter
from codoc.llm import (
    LlmError,
    chat_completion,
    embed_texts,
    resolve_api_key,
    resolve_embedding_model,
)
from codoc.model.registry import PageRegistry, build_page_registry
from codoc.model.spec import Page, SpecDocument, SpecError, load_spec
from codoc.rag.index import attach_embeddings, build_rag_index, retrieve, write_rag_index

_MD_LINK = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)]+)\)")
# CommonMark: fences may indent 0–3 spaces; closers are marker-only (no info string).
_FENCE_OPEN = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")
_FENCE_CLOSE = re.compile(r"^( {0,3})(`{3,}|~{3,})[ \t]*$")


class ValidateError(Exception):
    """Validate found blocking problems."""


@dataclass(frozen=True, slots=True)
class Finding:
    severity: str
    code: str
    message: str
    path: str | None = None


@dataclass(frozen=True, slots=True)
class ValidateResult:
    findings: tuple[Finding, ...]
    candidates: tuple[str, ...]
    rag_path: Path | None
    notes: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(item.severity == "error" for item in self.findings)


def run_validate(start: Path | None = None) -> ValidateResult:
    """Run structural checks, refresh the RAG index, and optionally Stage D."""
    if start is None:
        start = Path.cwd()
    try:
        root = git_root(start)
        config = load_project_config(root / "codoc.yaml")
        units = discover(root)
        loaded: list[tuple[SpecUnit, SpecDocument]] = []
        for unit in units:
            loaded.append((unit, load_spec(root / unit.spec_path)))
        registry = build_page_registry(tuple((root / unit.spec_path, doc) for unit, doc in loaded))
    except (DiscoverError, ConfigError, SpecError) as err:
        raise ValidateError(str(err)) from err

    findings: list[Finding] = []
    page_files: list[tuple[str, Path, str]] = []
    coverage_files: set[str] = set()
    excludes = child_scopes(tuple(unit for unit, _doc in loaded))

    for unit, doc in loaded:
        coverage_files.update(
            _coverage_files(
                root,
                unit.scope_dir,
                doc,
                exclude_scopes=excludes.get(unit.scope_dir, ()),
            )
        )
        for page in doc.pages():
            abs_path = root / page.path
            page_files.append((page.id, abs_path, page.path))
            findings.extend(_check_page(root, page, abs_path, registry))

    candidates = _git_candidates(root, coverage_files)
    rag_chunks = build_rag_index(page_files)
    notes: list[str] = []
    rag_chunks, embed_notes = _maybe_embed(config.llm, rag_chunks)
    notes.extend(embed_notes)
    rag_path = write_rag_index(root, rag_chunks)

    if candidates:
        findings.append(
            Finding(
                "info",
                "git.candidates",
                f"{len(candidates)} coverage file(s) changed since HEAD",
            )
        )
        stage_d = _stage_d(config.llm, candidates, rag_chunks)
        findings.extend(stage_d.findings)
        notes.extend(stage_d.notes)

    return ValidateResult(
        findings=tuple(findings),
        candidates=tuple(candidates),
        rag_path=rag_path,
        notes=tuple(notes),
    )


@dataclass(frozen=True, slots=True)
class _StageD:
    findings: tuple[Finding, ...]
    notes: tuple[str, ...]


def _maybe_embed(llm: LlmConfig, chunks: tuple) -> tuple[tuple, tuple[str, ...]]:
    if not chunks or not llm.provider:
        return chunks, ()
    model = resolve_embedding_model(llm.provider, llm.embedding_model)
    if model is None:
        return chunks, ()
    api_key = resolve_api_key(llm.provider)
    if not api_key:
        return chunks, (f"rag embeddings skipped: no API key for {llm.provider}",)
    try:
        vectors = embed_texts(
            [f"{chunk.heading}\n{chunk.text}" for chunk in chunks],
            provider=llm.provider,
            model=model,
            api_key=api_key,
        )
    except LlmError as err:
        return chunks, (f"rag embeddings skipped: {err}",)
    return attach_embeddings(chunks, vectors), ("rag embeddings attached",)


def _stage_d(
    llm: LlmConfig,
    candidates: tuple[str, ...] | list[str],
    chunks: tuple,
) -> _StageD:
    if not llm.provider or not llm.model:
        return _StageD((), ("stage D skipped: llm.provider/model not set",))
    if llm.provider.lower() == "cursor-cli":
        from codoc.llm import cursor_agent_path

        if cursor_agent_path() is None:
            return _StageD((), ("stage D skipped: agent not on PATH for cursor-cli",))
    api_key = resolve_api_key(llm.provider)
    if not api_key:
        return _StageD((), (f"stage D skipped: no API key for {llm.provider}",))
    query = " ".join(candidates)
    query_embedding = None
    embed_model = resolve_embedding_model(llm.provider, llm.embedding_model)
    if embed_model and any(getattr(chunk, "embedding", None) for chunk in chunks):
        try:
            query_embedding = embed_texts(
                [query],
                provider=llm.provider,
                model=embed_model,
                api_key=api_key,
            )[0]
        except LlmError:
            query_embedding = None
    context = retrieve(chunks, query, limit=5, query_embedding=query_embedding)
    context_text = (
        "\n\n".join(
            f"[{chunk.page_id} {chunk.path}#{chunk.heading}]\n{chunk.text[:400]}"
            for chunk in context
        )
        or "(no docs chunks)"
    )
    prompt = (
        "You review documentation drift for a Python repo.\n"
        "Changed source files:\n"
        + "\n".join(f"- {path}" for path in candidates)
        + "\n\nRelated docs excerpts:\n"
        + context_text
        + "\n\nReply with one short paragraph: OK if docs look aligned, "
        "or name the page ids that likely need regeneration."
    )
    try:
        answer = chat_completion(
            provider=llm.provider,
            model=llm.model,
            api_key=api_key,
            messages=[
                {"role": "system", "content": "You are a concise docs drift reviewer."},
                {"role": "user", "content": prompt},
            ],
            timeout_s=60.0 if llm.provider.lower() == "cursor-cli" else 30.0,
        )
    except LlmError as err:
        return _StageD((), (f"stage D skipped: {err}",))
    message = re.sub(r"[\t\r\n]+", " ", answer.strip())[:500]
    return _StageD((Finding("info", "stage.d", message),), ())


def _check_page(
    root: Path,
    page: Page,
    abs_path: Path,
    registry: PageRegistry,
) -> list[Finding]:
    findings: list[Finding] = []
    if not abs_path.is_file():
        findings.append(
            Finding("error", "page.missing", f"missing page file for {page.id}", page.path)
        )
        return findings

    text = abs_path.read_text(encoding="utf-8")
    try:
        split = split_frontmatter(text)
    except FrontmatterError as err:
        findings.append(Finding("error", "frontmatter.invalid", str(err), page.path))
        split = None

    if split is None:
        body = text
    elif split.frontmatter is None:
        findings.append(
            Finding("error", "frontmatter.missing", "missing codoc frontmatter", page.path)
        )
        body = split.body
    else:
        if split.frontmatter.id != page.id:
            findings.append(
                Finding(
                    "error",
                    "frontmatter.id",
                    f"frontmatter id {split.frontmatter.id!r} != spec {page.id!r}",
                    page.path,
                )
            )
        if split.frontmatter.type != page.type:
            findings.append(
                Finding(
                    "error",
                    "frontmatter.type",
                    f"frontmatter type {split.frontmatter.type!r} != spec {page.type!r}",
                    page.path,
                )
            )
        body = split.body

    if page.type == "auto-generated" and page.script and not (root / page.script).is_file():
        findings.append(
            Finding("error", "script.missing", f"script not found: {page.script}", page.path)
        )
    for placeholder in page.placeholders:
        if not (root / placeholder.script).is_file():
            findings.append(
                Finding(
                    "error",
                    "script.missing",
                    f"placeholder script not found: {placeholder.script}",
                    page.path,
                )
            )

    for link in page.links:
        if link.id not in registry:
            findings.append(
                Finding(
                    "error",
                    "link.unknown",
                    f"links id {link.id!r} not in registry",
                    page.path,
                )
            )
    if page.canonical and page.canonical not in registry:
        findings.append(
            Finding(
                "error",
                "canonical.unknown",
                f"canonical id {page.canonical!r} not in registry",
                page.path,
            )
        )

    for _label, target in _MD_LINK.findall(_without_fenced_code(body)):
        href = _link_href(target)
        if href is None:
            continue
        path_part = href.split("#", 1)[0]
        if not path_part:
            continue
        resolved = (abs_path.parent / path_part).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            findings.append(
                Finding("error", "link.escape", f"link escapes repo: {target}", page.path)
            )
            continue
        if not resolved.exists():
            findings.append(Finding("error", "link.broken", f"broken link: {target}", page.path))
    return findings


def _without_fenced_code(text: str) -> str:
    """Drop closed fenced code blocks so sample links inside them are not checked.

    An unclosed fence is treated as prose so later real links are still checked.
    Nested sample fences with an info string do not close the outer fence.
    """
    lines = text.splitlines(keepends=True)
    kept: list[str] = []
    pending: list[str] = []
    fence_char: str | None = None
    fence_len = 0
    for line in lines:
        raw = line[:-1] if line.endswith("\n") else line
        if raw.endswith("\r"):
            raw = raw[:-1]
        if fence_char is None:
            match = _FENCE_OPEN.match(raw)
            if match:
                marker = match.group(2)
                fence_char = marker[0]
                fence_len = len(marker)
                pending = [line]
                continue
            kept.append(line)
            continue
        pending.append(line)
        close = _FENCE_CLOSE.match(raw)
        if (
            close is not None
            and close.group(2)[0] == fence_char
            and len(close.group(2)) >= fence_len
        ):
            fence_char = None
            fence_len = 0
            pending = []
    if fence_char is not None:
        kept.extend(pending)
    return "".join(kept)


def _link_href(target: str) -> str | None:
    """Return the destination path/URL, stripping optional Markdown link titles."""
    raw = target.strip()
    if not raw:
        return None
    if raw.startswith("<") and ">" in raw:
        raw = raw[1 : raw.index(">")].strip()
    else:
        raw = raw.split(None, 1)[0]
    if raw.startswith(("http://", "https://", "mailto:", "#")):
        return None
    return raw


def _coverage_files(
    root: Path,
    scope_dir: Path,
    doc: SpecDocument,
    *,
    exclude_scopes: tuple[Path, ...] = (),
) -> set[str]:
    found: set[str] = set()
    for block in doc.coverage.source + doc.coverage.features:
        found.update(
            expand_coverage_paths(
                root,
                scope_dir,
                block.paths,
                exclude_scopes=exclude_scopes,
            )
        )
    return found


def _git_candidates(root: Path, coverage_files: set[str]) -> list[str]:
    if not coverage_files:
        return []
    changed = _git_changed_files(root)
    return sorted(path for path in changed if path in coverage_files)


def _git_changed_files(root: Path) -> set[str]:
    commands = (
        ["git", "-C", os.fspath(root), "diff", "--name-only", "HEAD"],
        ["git", "-C", os.fspath(root), "diff", "--name-only", "--cached"],
        ["git", "-C", os.fspath(root), "ls-files", "--others", "--exclude-standard"],
    )
    found: set[str] = set()
    for command in commands:
        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
        for line in completed.stdout.splitlines():
            path = line.strip()
            if path:
                found.add(path)
    return found
