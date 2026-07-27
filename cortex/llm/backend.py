"""Pluggable LLM backend abstraction.

Cortex is deterministic-first: everything except enrichment works with no
LLM at all. This module isolates the one place that talks to a model so the
provider is swappable (OpenRouter, Azure OpenAI, Ollama, vLLM via the
OpenAI protocol; AWS Bedrock natively) and so `CORTEX_LLM_BACKEND=none`
guarantees zero network calls.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cortex.config import CortexSettings

logger = logging.getLogger(__name__)


class LLMBackend(ABC):
    """Provider-agnostic chat-completion interface."""

    #: False means enrichment is unavailable and callers must skip it.
    enabled: bool = True
    #: Provider-native model identifier, recorded in note provenance.
    model_id: str = ""

    @abstractmethod
    async def complete(
        self, system: str, user: str, *, max_tokens: int = 4096
    ) -> str:
        """Send one system+user exchange, return the assistant's text."""

    def markitdown_kwargs(self) -> dict[str, Any]:
        """Extra MarkItDown kwargs to enable vision captioning, or {}."""
        return {}


class DisabledBackend(LLMBackend):
    """Explicit no-LLM mode: never calls out, fails loudly if asked to."""

    enabled = False

    async def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        raise RuntimeError(
            "LLM backend is disabled (CORTEX_LLM_BACKEND=none or no API key); "
            "callers must check backend.enabled before requesting completions"
        )


class OpenAICompatibleBackend(LLMBackend):
    """Any endpoint speaking the OpenAI protocol: OpenRouter, Azure OpenAI,
    Ollama, vLLM, LM Studio. Differ only in base_url and key."""

    def __init__(self, settings: CortexSettings) -> None:
        from openai import AsyncOpenAI

        self._settings = settings
        self.model_id = settings.compiler_model
        self.client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )

    async def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        response = await self.client.chat.completions.create(
            model=self.model_id,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""

    def markitdown_kwargs(self) -> dict[str, Any]:
        from openai import OpenAI

        from cortex.compiler.prompts import IMAGE_CAPTION_PROMPT

        return {
            "llm_client": OpenAI(
                api_key=self._settings.llm_api_key,
                base_url=self._settings.llm_base_url,
            ),
            "llm_model": self._settings.compiler_vision_model
            or self._settings.compiler_model,
            "llm_prompt": IMAGE_CAPTION_PROMPT,
        }


class BedrockBackend(LLMBackend):
    """AWS Bedrock via the Converse API. boto3 is imported lazily so the
    backend can be configured without it installed; credentials come from
    the standard AWS chain (env, profile, instance role)."""

    def __init__(self, settings: CortexSettings) -> None:
        self.model_id = settings.compiler_model
        self._client = None

    def _bedrock_client(self):
        if self._client is None:
            try:
                import boto3
            except ImportError as exc:
                raise RuntimeError(
                    "CORTEX_LLM_BACKEND=bedrock requires boto3; "
                    "install it with `uv add boto3` or pip install boto3"
                ) from exc
            self._client = boto3.client("bedrock-runtime")
        return self._client

    async def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        import asyncio

        client = self._bedrock_client()

        def _converse() -> str:
            response = client.converse(
                modelId=self.model_id,
                system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": user}]}],
                inferenceConfig={"maxTokens": max_tokens},
            )
            parts = response["output"]["message"]["content"]
            return "".join(p.get("text", "") for p in parts)

        return await asyncio.to_thread(_converse)

    # markitdown_kwargs stays {} — MarkItDown's vision path requires an
    # OpenAI-protocol client, which Bedrock does not expose.


def create_backend(settings: CortexSettings) -> LLMBackend:
    """Build the configured backend; falls back to disabled when unusable."""
    if settings.llm_backend == "none":
        return DisabledBackend()
    if settings.llm_backend == "bedrock":
        return BedrockBackend(settings)
    # openai-compatible needs a key to be usable.
    if not settings.llm_api_key:
        return DisabledBackend()
    return OpenAICompatibleBackend(settings)
