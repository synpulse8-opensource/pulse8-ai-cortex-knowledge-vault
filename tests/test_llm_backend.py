"""Tests for the pluggable LLM backend abstraction."""
from __future__ import annotations

import pytest


def _settings(**overrides):
    from cortex.config import CortexSettings

    return CortexSettings(**overrides)


def test_backend_none_is_disabled():
    """llm_backend=none yields a disabled backend even when a key is set."""
    from cortex.llm.backend import create_backend

    backend = create_backend(_settings(llm_backend="none", llm_api_key="sk-or-x"))
    assert backend.enabled is False


def test_openai_compatible_without_key_is_disabled():
    """openai-compatible without an API key cannot make calls -> disabled."""
    from cortex.llm.backend import create_backend

    backend = create_backend(_settings(llm_backend="openai-compatible", llm_api_key=""))
    assert backend.enabled is False


def test_disabled_backend_refuses_completion():
    """A disabled backend must fail loudly, not silently call out."""
    import asyncio

    from cortex.llm.backend import create_backend

    backend = create_backend(_settings(llm_backend="none"))
    with pytest.raises(RuntimeError):
        asyncio.run(backend.complete("sys", "user"))


def test_disabled_backend_markitdown_kwargs_empty():
    """No vision client is attached when the backend is disabled."""
    from cortex.llm.backend import create_backend

    backend = create_backend(_settings(llm_backend="none"))
    assert backend.markitdown_kwargs() == {}


def test_openai_compatible_enabled_with_key():
    """openai-compatible with a key is enabled and exposes the model id."""
    from cortex.llm.backend import create_backend

    backend = create_backend(
        _settings(
            llm_backend="openai-compatible",
            llm_api_key="sk-or-test",
            compiler_model="test/model-1",
        )
    )
    assert backend.enabled is True
    assert backend.model_id == "test/model-1"


def test_openai_compatible_markitdown_kwargs():
    """Vision attachment: sync client + vision model (fallback to compiler model) + prompt."""
    from cortex.compiler.prompts import IMAGE_CAPTION_PROMPT
    from cortex.llm.backend import create_backend

    backend = create_backend(
        _settings(
            llm_backend="openai-compatible",
            llm_api_key="sk-or-test",
            compiler_model="test/model-1",
            compiler_vision_model="test/vision-1",
        )
    )
    kwargs = backend.markitdown_kwargs()
    assert kwargs["llm_model"] == "test/vision-1"
    assert kwargs["llm_prompt"] == IMAGE_CAPTION_PROMPT
    assert kwargs["llm_client"] is not None


async def test_openai_compatible_complete_delegates_to_client(monkeypatch):
    """complete() sends system+user messages and returns the assistant text."""
    from cortex.llm.backend import create_backend

    backend = create_backend(
        _settings(llm_backend="openai-compatible", llm_api_key="sk-or-test")
    )

    captured = {}

    class _FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)

            class _Msg:
                content = "assistant says hi"

            class _Choice:
                message = _Msg()

            class _Resp:
                choices = [_Choice()]

            return _Resp()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    monkeypatch.setattr(backend, "client", _FakeClient())

    text = await backend.complete("the system prompt", "the user content", max_tokens=123)
    assert text == "assistant says hi"
    assert captured["max_tokens"] == 123
    assert captured["messages"][0] == {"role": "system", "content": "the system prompt"}
    assert captured["messages"][1] == {"role": "user", "content": "the user content"}


def test_bedrock_backend_constructs_without_boto3():
    """Bedrock backend is lazy: constructing it must not require boto3."""
    from cortex.llm.backend import create_backend

    backend = create_backend(
        _settings(llm_backend="bedrock", compiler_model="anthropic.claude-3-haiku")
    )
    assert backend.enabled is True
    assert backend.model_id == "anthropic.claude-3-haiku"
    # MarkItDown vision needs an OpenAI-protocol client; Bedrock doesn't provide one.
    assert backend.markitdown_kwargs() == {}
