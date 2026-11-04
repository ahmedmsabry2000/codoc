"""Draft prompt includes optional intent/audience/purpose."""

from codoc.config import LlmConfig
from codoc.generate.draft import draft_stub_body
from codoc.model.spec import Page, SpecDocument


class DraftPromptTests:
    def test_prompt_includes_prose_guidance(self, monkeypatch) -> None:
        captured: dict[str, object] = {}

        def fake_chat(**kwargs: object) -> str:
            captured["messages"] = kwargs["messages"]
            return "# Guide\n\nBody.\n"

        monkeypatch.setattr("codoc.generate.draft.chat_completion", fake_chat)
        monkeypatch.setattr("codoc.generate.draft.resolve_api_key", lambda _provider: "key")
        page = Page(
            "guide",
            "manual",
            "docs/guide.md",
            purpose="Orient a new reader to the CLI loop.",
        )
        doc = SpecDocument(
            docs=(page,),
            intent="Explain how to use Codoc locally.",
            audience="CLI contributors",
        )
        body, note = draft_stub_body(
            page,
            LlmConfig(provider="openai", model="gpt-test"),
            doc=doc,
        )
        assert note is None
        assert body is not None
        messages = captured["messages"]
        assert isinstance(messages, list)
        user = messages[1]["content"]
        assert "Scope intent: Explain how to use Codoc locally." in user
        assert "Audience: CLI contributors" in user
        assert "Page purpose: Orient a new reader to the CLI loop." in user
        system = messages[0]["content"]
        assert "guidance" in system.lower()

    def test_prompt_omits_missing_prose(self, monkeypatch) -> None:
        captured: dict[str, object] = {}

        def fake_chat(**kwargs: object) -> str:
            captured["messages"] = kwargs["messages"]
            return "# Guide\n\nBody.\n"

        monkeypatch.setattr("codoc.generate.draft.chat_completion", fake_chat)
        monkeypatch.setattr("codoc.generate.draft.resolve_api_key", lambda _provider: "key")
        page = Page("guide", "manual", "docs/guide.md")
        body, note = draft_stub_body(
            page,
            LlmConfig(provider="openai", model="gpt-test"),
            doc=SpecDocument(docs=(page,)),
        )
        assert note is None
        assert body is not None
        user = captured["messages"][1]["content"]  # type: ignore[index]
        assert "Scope intent:" not in user
        assert "Audience:" not in user
        assert "Page purpose:" not in user
