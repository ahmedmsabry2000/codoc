import json
from unittest.mock import MagicMock, patch

import pytest

from codoc.llm.chat import LlmError, chat_completion, resolve_api_key


class LlmChatTests:
    def test_resolve_api_key_openai(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-o"}, clear=True):
            assert resolve_api_key("openai") == "sk-o"
            assert resolve_api_key("openai-compatible") == "sk-o"
            assert resolve_api_key("anthropic") is None

    def test_resolve_api_key_anthropic(self) -> None:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-a"}, clear=True):
            assert resolve_api_key("anthropic") == "sk-a"

    def test_openai_chat_reads_content(self) -> None:
        payload = {"choices": [{"message": {"content": "hello"}}]}
        response = MagicMock()
        response.read.return_value = json.dumps(payload).encode("utf-8")
        response.__enter__.return_value = response
        response.__exit__.return_value = None
        with patch("codoc.llm.chat.urllib.request.urlopen", return_value=response):
            text = chat_completion(
                provider="openai",
                model="gpt-4.1",
                api_key="sk",
                messages=[{"role": "user", "content": "hi"}],
            )
        assert text == "hello"

    def test_unsupported_provider(self) -> None:
        with pytest.raises(LlmError):
            chat_completion(
                provider="cursor",
                model="x",
                api_key="sk",
                messages=[{"role": "user", "content": "hi"}],
            )
