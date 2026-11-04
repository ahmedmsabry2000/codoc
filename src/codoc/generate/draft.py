"""Optional BYO LLM draft assist for new and eligible stub pages."""

from pathlib import Path

from codoc.config import LlmConfig
from codoc.generate.frontmatter import FrontmatterError, split_frontmatter
from codoc.llm import LlmError, chat_completion, resolve_api_key
from codoc.model.spec import Page


def draft_stub_body(page: Page, llm: LlmConfig) -> tuple[str | None, str | None]:
    """
    Return (body, note) for a brand-new manual/hybrid page.

    Offline or misconfigured llm always returns (None, note) and never raises.
    """
    if page.type not in {"manual", "hybrid"}:
        return None, None
    return _request_draft(page, llm)


def maybe_rewrite_stub(
    root: Path,
    page: Page,
    llm: LlmConfig,
) -> tuple[str | None, str | None]:
    """
    Optionally rewrite an existing eligible manual stub when configured.

    Never rewrites hybrid exteriors or non-stub manual bodies. Returns
    (None, note) when the model is not called.
    """
    if page.type != "manual":
        return None, None
    if not llm.rewrite_stubs:
        return None, None
    abs_path = root / page.path
    if not abs_path.is_file():
        return None, None
    if not is_eligible_manual_stub(abs_path, page):
        return None, "rewrite skipped: existing page preserved"
    return _request_draft(page, llm)


def is_eligible_manual_stub(path: Path, page: Page) -> bool:
    """True when the page body is still the default `# {id}` stub."""
    try:
        split = split_frontmatter(path.read_text(encoding="utf-8"))
    except (OSError, FrontmatterError, UnicodeDecodeError):
        return False
    body = split.body.strip()
    return body in {f"# {page.id}", ""}


def _request_draft(page: Page, llm: LlmConfig) -> tuple[str | None, str | None]:
    if not llm.provider or not llm.model:
        return None, "draft skipped: llm.provider/model not set"
    if llm.provider.lower() == "cursor-cli":
        from codoc.llm import cursor_agent_path

        if cursor_agent_path() is None:
            return None, "draft skipped: agent not on PATH for cursor-cli"
    api_key = resolve_api_key(llm.provider)
    if not api_key:
        return None, f"draft skipped: no API key for {llm.provider}"
    prompt = (
        f"Write a short Markdown documentation stub for page id {page.id!r} "
        f"(type {page.type}). Use a single H1 and two short paragraphs. "
        "Do not include YAML frontmatter. Do not invent APIs."
    )
    try:
        text = chat_completion(
            provider=llm.provider,
            model=llm.model,
            api_key=api_key,
            messages=[
                {
                    "role": "system",
                    "content": "You draft concise technical documentation stubs.",
                },
                {"role": "user", "content": prompt},
            ],
            timeout_s=60.0 if llm.provider.lower() == "cursor-cli" else 20.0,
        )
    except LlmError as err:
        return None, f"draft skipped: {err}"
    cleaned = text.strip()
    if not cleaned:
        return None, "draft skipped: empty model response"
    if not cleaned.endswith("\n"):
        cleaned += "\n"
    return cleaned, None
