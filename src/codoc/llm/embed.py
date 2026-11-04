"""Optional BYO embeddings for RAG (OpenAI / openai-compatible)."""

import json
import math
import os
import urllib.error
import urllib.request
from typing import Any

from codoc.llm.chat import LlmError


def embed_texts(
    texts: list[str],
    *,
    provider: str,
    model: str,
    api_key: str,
    timeout_s: float = 30.0,
) -> list[list[float]]:
    """
    Return one embedding vector per text.

    Supports openai and openai-compatible providers. Other providers raise LlmError
    so callers can fall back to token-overlap retrieval.
    """
    name = provider.lower()
    if name not in {"openai", "openai-compatible"}:
        raise LlmError(f"embeddings unsupported for provider {provider!r}")
    if not texts:
        return []
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    payload = {"model": model, "input": texts}
    data = _post_json(
        f"{base_url}/embeddings",
        payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout_s=timeout_s,
    )
    try:
        items = data["data"]
        ordered = sorted(items, key=lambda item: item["index"])
        vectors = [list(item["embedding"]) for item in ordered]
    except (KeyError, TypeError, IndexError) as err:
        raise LlmError("embeddings response missing data") from err
    if len(vectors) != len(texts):
        raise LlmError("embeddings response length mismatch")
    return vectors


def resolve_embedding_model(provider: str, configured: str | None) -> str | None:
    """Return an embedding model id when the provider can embed."""
    name = provider.lower()
    if name not in {"openai", "openai-compatible"}:
        return None
    if configured:
        return configured
    return os.environ.get("CODOC_EMBEDDING_MODEL", "text-embedding-3-small")


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Return cosine similarity, or 0.0 when either vector is empty."""
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_l = math.sqrt(sum(a * a for a in left))
    norm_r = math.sqrt(sum(b * b for b in right))
    if norm_l == 0.0 or norm_r == 0.0:
        return 0.0
    return dot / (norm_l * norm_r)


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_s: float,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        raise LlmError(f"llm HTTP {err.code}: {detail[:200]}") from err
    except urllib.error.URLError as err:
        raise LlmError(f"llm request failed: {err.reason}") from err
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as err:
        raise LlmError("llm response is not JSON") from err
    if not isinstance(loaded, dict):
        raise LlmError("llm response must be a JSON object")
    return loaded
