"""Minimal chat-completions client using the standard library."""

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Any


class LlmError(Exception):
    """A BYO LLM call failed."""


def resolve_api_key(provider: str) -> str | None:
    """Return an API key from the environment for the configured provider."""
    name = provider.lower()
    if name in {"openai", "openai-compatible"}:
        return os.environ.get("OPENAI_API_KEY") or os.environ.get("CODOC_LLM_API_KEY") or None
    if name == "anthropic":
        return os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CODOC_LLM_API_KEY") or None
    if name == "cursor-cli":
        key = os.environ.get("CURSOR_API_KEY") or os.environ.get("CODOC_LLM_API_KEY")
        if key:
            return key
        # agent login can work without exporting CURSOR_API_KEY
        return "agent-login" if cursor_agent_path() is not None else None
    return None


def cursor_agent_path() -> str | None:
    """Return the path to the Cursor `agent` binary when present on PATH."""
    return shutil.which("agent")


def chat_completion(
    *,
    provider: str,
    model: str,
    api_key: str,
    messages: list[dict[str, str]],
    timeout_s: float = 30.0,
) -> str:
    """
    Return the assistant text for a short chat request.

    Supports openai, openai-compatible (OPENAI_BASE_URL), anthropic, and cursor-cli.
    """
    name = provider.lower()
    if name in {"openai", "openai-compatible"}:
        return _openai_chat(
            model=model,
            api_key=api_key,
            messages=messages,
            base_url=_openai_base_url(),
            timeout_s=timeout_s,
        )
    if name == "anthropic":
        return _anthropic_chat(
            model=model,
            api_key=api_key,
            messages=messages,
            timeout_s=timeout_s,
        )
    if name == "cursor-cli":
        return _cursor_cli_chat(
            model=model,
            api_key=api_key,
            messages=messages,
            timeout_s=timeout_s,
        )
    raise LlmError(f"unsupported llm.provider {provider!r}")


def _openai_base_url() -> str:
    raw = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    return raw


def _openai_chat(
    *,
    model: str,
    api_key: str,
    messages: list[dict[str, str]],
    base_url: str,
    timeout_s: float,
) -> str:
    payload = {"model": model, "messages": messages, "temperature": 0}
    data = _post_json(
        f"{base_url}/chat/completions",
        payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout_s=timeout_s,
    )
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as err:
        raise LlmError("openai response missing message content") from err
    if not isinstance(content, str) or content == "":
        raise LlmError("openai response content empty")
    return content


def _anthropic_chat(
    *,
    model: str,
    api_key: str,
    messages: list[dict[str, str]],
    timeout_s: float,
) -> str:
    system = ""
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role", "")
        content = message.get("content", "")
        if role == "system":
            system = content
            continue
        if role not in {"user", "assistant"}:
            continue
        converted.append({"role": role, "content": content})
    if not converted:
        raise LlmError("anthropic requires at least one user message")
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": 1024,
        "messages": converted,
        "temperature": 0,
    }
    if system:
        payload["system"] = system
    data = _post_json(
        "https://api.anthropic.com/v1/messages",
        payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        timeout_s=timeout_s,
    )
    try:
        blocks = data["content"]
        text = "".join(
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        )
    except (KeyError, TypeError) as err:
        raise LlmError("anthropic response missing text content") from err
    if text == "":
        raise LlmError("anthropic response content empty")
    return text


def _cursor_cli_chat(
    *,
    model: str,
    api_key: str,
    messages: list[dict[str, str]],
    timeout_s: float,
) -> str:
    agent = cursor_agent_path()
    if agent is None:
        raise LlmError("cursor-cli: agent not found on PATH")
    prompt = _flatten_messages(messages)
    command = [
        agent,
        "-p",
        "--output-format",
        "text",
        "--mode",
        "ask",
        "--trust",
    ]
    if model:
        command.extend(["--model", model])
    command.append(prompt)
    env = os.environ.copy()
    if api_key and api_key != "agent-login":
        env["CURSOR_API_KEY"] = api_key
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
        )
    except subprocess.TimeoutExpired as err:
        raise LlmError(f"cursor-cli timed out after {timeout_s}s") from err
    except OSError as err:
        raise LlmError(f"cursor-cli failed to start: {err}") from err
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[:200]
        raise LlmError(f"cursor-cli exit {completed.returncode}: {detail}")
    text = completed.stdout.strip()
    if not text:
        raise LlmError("cursor-cli response empty")
    return text


def _flatten_messages(messages: list[dict[str, str]]) -> str:
    parts: list[str] = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        parts.append(f"{role}:\n{content}")
    return "\n\n".join(parts)


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
