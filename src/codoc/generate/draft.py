"""Optional BYO LLM draft assist for new manual/hybrid page stubs."""

from codoc.config import LlmConfig
from codoc.llm import LlmError, chat_completion, resolve_api_key
from codoc.model.spec import Page


def draft_stub_body(page: Page, llm: LlmConfig) -> tuple[str | None, str | None]:
    """
    Return (body, note).

    body is Markdown without frontmatter when a draft is produced.
    note is a skip/failure reason when body is None.
    Offline or misconfigured llm always returns (None, note) and never raises.
    """
    if page.type not in {"manual", "hybrid"}:
        return None, None
    if not llm.provider or not llm.model:
        return None, "draft skipped: llm.provider/model not set"
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
            timeout_s=20.0,
        )
    except LlmError as err:
        return None, f"draft skipped: {err}"
    cleaned = text.strip()
    if not cleaned:
        return None, "draft skipped: empty model response"
    if not cleaned.endswith("\n"):
        cleaned += "\n"
    return cleaned, None
