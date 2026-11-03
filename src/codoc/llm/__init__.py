"""BYO LLM helpers (env keys; no hosted Codoc model)."""

from codoc.llm.chat import LlmError, chat_completion, resolve_api_key

__all__ = ["LlmError", "chat_completion", "resolve_api_key"]
