"""BYO LLM helpers (env keys; no hosted Codoc model)."""

from codoc.llm.chat import LlmError, chat_completion, cursor_agent_path, resolve_api_key
from codoc.llm.embed import cosine_similarity, embed_texts, resolve_embedding_model

__all__ = [
    "LlmError",
    "chat_completion",
    "cosine_similarity",
    "cursor_agent_path",
    "embed_texts",
    "resolve_api_key",
    "resolve_embedding_model",
]
