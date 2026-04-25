"""
LLM client factory — returns a unified async callable regardless of backend.

Supported backends:
  - openai    → OpenAI API (GPT-4o, GPT-4-turbo, etc.)
  - ollama    → local Ollama server (Qwen3-30B, Llama-3, etc.)
  - vllm      → vLLM OpenAI-compatible server (high-throughput batched inference)
  - tgi       → HuggingFace TGI OpenAI-compatible server
  - litellm   → any OpenAI-compatible endpoint via LiteLLM

All return `(answer_text: str, model_used: str)`.
"""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from typing import Any

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Common interface
# --------------------------------------------------------------------------- #

class LLMClient:
    """Base class; subclasses implement `complete` and `stream`."""

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> tuple[str, str]:
        """Returns (answer_text, model_id_used)."""
        raise NotImplementedError

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        """Yield tokens as they arrive from the LLM. Default: fall back to complete()."""
        text, _ = await self.complete(messages, max_tokens=max_tokens, temperature=temperature)
        for word in text.split(" "):
            yield word + " "

    @property
    def model_id(self) -> str:
        return getattr(self, "_model", "unknown")


# --------------------------------------------------------------------------- #
# OpenAI backend
# --------------------------------------------------------------------------- #

class OpenAIClient(LLMClient):
    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._base_url = base_url

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> tuple[str, str]:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError("Install openai: pip install openai") from exc

        client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
        )
        response = await client.chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = response.choices[0].message.content or ""
        return text.strip(), self._model

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError("Install openai: pip install openai") from exc

        client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
        )
        response = await client.chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content


# --------------------------------------------------------------------------- #
# Ollama backend
# --------------------------------------------------------------------------- #

class OllamaClient(LLMClient):
    """
    Calls a local Ollama server at http://localhost:11434.
    Works with any model you have pulled: qwen3:30b, llama3, mistral, etc.
    """

    def __init__(
        self,
        model: str = "qwen3:30b",
        base_url: str = "http://localhost:11434",
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> tuple[str, str]:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("Install httpx: pip install httpx") from exc

        payload = {
            "model": self._model,
            "messages": messages,
            "options": {"temperature": temperature, "num_predict": max_tokens},
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(f"{self._base_url}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()

        text = data.get("message", {}).get("content", "")
        return text.strip(), self._model

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("Install httpx: pip install httpx") from exc

        payload = {
            "model": self._model,
            "messages": messages,
            "options": {"temperature": temperature, "num_predict": max_tokens},
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST", f"{self._base_url}/api/chat", json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    import json as _json
                    try:
                        data = _json.loads(line)
                    except _json.JSONDecodeError:
                        continue
                    token = data.get("message", {}).get("content", "")
                    if token:
                        yield token


# --------------------------------------------------------------------------- #
# vLLM backend (OpenAI-compatible, high-throughput batched inference)
# --------------------------------------------------------------------------- #

class VLLMClient(OpenAIClient):
    """
    Connects to a vLLM server's OpenAI-compatible endpoint.

    vLLM serves models at ``http://host:8000/v1`` by default.
    Supports continuous batching, PagedAttention, and speculative decoding.

    Start vLLM::

        python -m vllm.entrypoints.openai.api_server \\
            --model mistralai/Mistral-7B-Instruct-v0.3 \\
            --port 8000 --dtype auto --max-model-len 4096

    Environment variables::

        VLLM_BASE_URL   : server URL (default: http://localhost:8000/v1)
        VLLM_API_KEY    : API key if auth is enabled (default: "EMPTY")
    """

    def __init__(
        self,
        model: str = "mistralai/Mistral-7B-Instruct-v0.3",
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(
            model=model,
            api_key=api_key or os.getenv("VLLM_API_KEY", "EMPTY"),
            base_url=base_url or os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1"),
        )


# --------------------------------------------------------------------------- #
# TGI backend (HuggingFace Text Generation Inference, OpenAI-compatible)
# --------------------------------------------------------------------------- #

class TGIClient(OpenAIClient):
    """
    Connects to a HuggingFace TGI server's OpenAI-compatible endpoint.

    TGI serves models at ``http://host:8080/v1`` by default.
    Supports flash-attention, quantization, and token streaming.

    Start TGI::

        docker run --gpus all -p 8080:80 \\
            ghcr.io/huggingface/text-generation-inference:latest \\
            --model-id mistralai/Mistral-7B-Instruct-v0.3

    Environment variables::

        TGI_BASE_URL    : server URL (default: http://localhost:8080/v1)
        TGI_API_KEY     : API key if auth is enabled (default: "EMPTY")
    """

    def __init__(
        self,
        model: str = "tgi",
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(
            model=model,
            api_key=api_key or os.getenv("TGI_API_KEY", "EMPTY"),
            base_url=base_url or os.getenv("TGI_BASE_URL", "http://localhost:8080/v1"),
        )


# --------------------------------------------------------------------------- #
# LiteLLM backend (any OpenAI-compatible endpoint)
# --------------------------------------------------------------------------- #

class LiteLLMClient(LLMClient):
    """Uses litellm.acompletion — supports 100+ providers."""

    def __init__(self, model: str = "gpt-4o", **kwargs: Any) -> None:
        self._model = model
        self._kwargs = kwargs

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> tuple[str, str]:
        try:
            import litellm
        except ImportError as exc:
            raise RuntimeError("Install litellm: pip install litellm") from exc

        response = await litellm.acompletion(
            model=self._model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **self._kwargs,
        )
        text = response.choices[0].message.content or ""
        return text.strip(), self._model

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        try:
            import litellm
        except ImportError as exc:
            raise RuntimeError("Install litellm: pip install litellm") from exc

        response = await litellm.acompletion(
            model=self._model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
            **self._kwargs,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content


# --------------------------------------------------------------------------- #
# Tiered routing client (fast model for simple queries, large for complex)
# --------------------------------------------------------------------------- #

class TieredLLMClient(LLMClient):
    """
    Routes queries to a fast or large LLM based on query complexity.

    Call ``set_complexity(score)`` before each ``complete()`` / ``stream()``
    invocation.  If no fast client is configured, all queries use the large
    client — the system degrades gracefully.

    Environment variables::

        LLM_MODEL_FAST              : fast model name (e.g. "qwen2:7b", "phi3:mini")
        LLM_TIERED_THRESHOLD        : complexity cutoff (default: 0.35)
        LLM_TIERED_ENABLED          : "true" to enable (default: true when fast model set)
    """

    def __init__(
        self,
        fast_client: LLMClient,
        large_client: LLMClient,
        *,
        complexity_threshold: float = 0.35,
    ) -> None:
        self._fast = fast_client
        self._large = large_client
        self._threshold = complexity_threshold
        self._complexity: float = 1.0  # default: use large model

    def set_complexity(self, score: float) -> None:
        self._complexity = score

    def _select(self) -> LLMClient:
        return self._fast if self._complexity < self._threshold else self._large

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> tuple[str, str]:
        client = self._select()
        logger.debug(
            "TieredLLM: complexity=%.3f → %s", self._complexity, client.model_id
        )
        return await client.complete(messages, max_tokens=max_tokens, temperature=temperature)

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        client = self._select()
        logger.debug(
            "TieredLLM stream: complexity=%.3f → %s", self._complexity, client.model_id
        )
        async for token in client.stream(messages, max_tokens=max_tokens, temperature=temperature):
            yield token

    @property
    def model_id(self) -> str:
        return self._select().model_id

    @property
    def fast_model(self) -> str:
        return self._fast.model_id

    @property
    def large_model(self) -> str:
        return self._large.model_id


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #

def create_llm_client(
    backend: str = "openai",
    model: str | None = None,
    **kwargs: Any,
) -> LLMClient:
    """
    Factory function.

    Args:
        backend: "openai" | "ollama" | "vllm" | "tgi" | "litellm"
        model:   model name (defaults per backend if None)
        **kwargs: passed to the client constructor
    """
    backend = backend.lower()
    if backend == "openai":
        return OpenAIClient(model=model or "gpt-4o", **kwargs)
    if backend == "ollama":
        return OllamaClient(model=model or "qwen3:30b", **kwargs)
    if backend == "vllm":
        return VLLMClient(model=model or "mistralai/Mistral-7B-Instruct-v0.3", **kwargs)
    if backend == "tgi":
        return TGIClient(model=model or "tgi", **kwargs)
    if backend == "litellm":
        return LiteLLMClient(model=model or "gpt-4o", **kwargs)
    raise ValueError(f"Unknown LLM backend: {backend!r}. Choose openai/ollama/vllm/tgi/litellm")


def create_tiered_llm_client(
    backend: str = "ollama",
    large_model: str | None = None,
    fast_model: str | None = None,
    complexity_threshold: float = 0.35,
    **kwargs: Any,
) -> LLMClient:
    """
    Create a tiered LLM client if a fast model is configured, otherwise a
    standard single-model client.

    Returns a ``TieredLLMClient`` when ``fast_model`` is set, or a plain
    ``LLMClient`` when it's not (graceful degradation).
    """
    large_client = create_llm_client(backend, model=large_model, **kwargs)

    if not fast_model or fast_model == (large_model or ""):
        logger.info("TieredLLM: no fast model configured, using single model (%s).", large_client.model_id)
        return large_client

    fast_client = create_llm_client(backend, model=fast_model, **kwargs)
    logger.info(
        "TieredLLM: fast=%s, large=%s, threshold=%.2f",
        fast_client.model_id, large_client.model_id, complexity_threshold,
    )
    return TieredLLMClient(
        fast_client=fast_client,
        large_client=large_client,
        complexity_threshold=complexity_threshold,
    )
