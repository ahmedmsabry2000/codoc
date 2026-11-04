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

    def test_resolve_api_key_cursor_cli(self) -> None:
        with patch.dict("os.environ", {"CURSOR_API_KEY": "sk-c"}, clear=True):
            assert resolve_api_key("cursor-cli") == "sk-c"

    def test_resolve_api_key_cursor_cli_falls_back_to_agent_login(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("codoc.llm.chat.cursor_agent_path", return_value="/bin/agent"),
        ):
            assert resolve_api_key("cursor-cli") == "agent-login"

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

    def test_cursor_cli_runs_agent_print(self) -> None:
        completed = MagicMock()
        completed.returncode = 0
        completed.stdout = "from agent\n"
        completed.stderr = ""
        with (
            patch("codoc.llm.chat.cursor_agent_path", return_value="/bin/agent"),
            patch("codoc.llm.chat.subprocess.run", return_value=completed) as run,
        ):
            text = chat_completion(
                provider="cursor-cli",
                model="composer-2",
                api_key="sk-c",
                messages=[{"role": "user", "content": "hi"}],
            )
        assert text == "from agent"
        command = run.call_args.args[0]
        assert command[0] == "/bin/agent"
        assert "-p" in command
        assert "--output-format" in command
        assert "text" in command
        assert "--api-key" not in command
        assert "--trust" in command
        env = run.call_args.kwargs["env"]
        assert env["CURSOR_API_KEY"] == "sk-c"

    def test_unsupported_provider(self) -> None:
        with pytest.raises(LlmError):
            chat_completion(
                provider="cursor",
                model="x",
                api_key="sk",
                messages=[{"role": "user", "content": "hi"}],
            )
