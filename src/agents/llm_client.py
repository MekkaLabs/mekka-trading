"""
src/agents/llm_client.py
========================
Unified LLM client with automatic provider fallback.

Priority order:
  1. OpenAI  — if OPENAI_API_KEY is present and valid
  2. Anthropic Claude — if ANTHROPIC_API_KEY is present

Both providers expose the same interface:
    await llm_client.chat(system_prompt, user_prompt) -> str

The returned string is the raw model output (JSON text for Vision/VisionCritic).
"""

from __future__ import annotations

import os
from typing import Optional

from loguru import logger

# ── OpenAI ────────────────────────────────────────────────────────────────────
try:
    from openai import AsyncOpenAI
    from openai import APIError as OpenAIAPIError
    from openai import APITimeoutError as OpenAITimeoutError
    from openai import RateLimitError as OpenAIRateLimitError
    _OPENAI_AVAILABLE = True
except ImportError:
    AsyncOpenAI = None  # type: ignore[assignment,misc]
    OpenAIAPIError = OpenAITimeoutError = OpenAIRateLimitError = Exception  # type: ignore[misc,assignment]
    _OPENAI_AVAILABLE = False

# ── Anthropic ─────────────────────────────────────────────────────────────────
try:
    import anthropic
    from anthropic import AsyncAnthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    AsyncAnthropic = None  # type: ignore[assignment,misc]
    _ANTHROPIC_AVAILABLE = False


class LLMClient:
    """
    Async LLM client with OpenAI → Claude fallback.

    Usage
    -----
    client = LLMClient(
        openai_key=settings.openai_api_key,
        openai_model=settings.openai_model,
        anthropic_key=settings.anthropic_api_key,
        anthropic_model=settings.anthropic_model,
        temperature=settings.openai_temperature,
        max_tokens=settings.openai_max_tokens,
    )
    raw_json = await client.chat(system_prompt, user_prompt)
    await client.close()
    """

    def __init__(
        self,
        openai_key: str = "",
        openai_model: str = "gpt-4o",
        anthropic_key: str = "",
        anthropic_model: str = "claude-sonnet-4-6",
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> None:
        self._openai_key = openai_key.strip()
        self._openai_model = openai_model
        self._anthropic_key = anthropic_key.strip()
        self._anthropic_model = anthropic_model
        self._temperature = temperature
        self._max_tokens = max_tokens

        self._openai_client: Optional[AsyncOpenAI] = None
        self._anthropic_client: Optional[AsyncAnthropic] = None

        # Determine which providers are usable
        self._has_openai = (
            _OPENAI_AVAILABLE
            and bool(self._openai_key)
            and not self._openai_key.startswith("sk-your-")
            and self._openai_key != ""
        )
        self._has_anthropic = (
            _ANTHROPIC_AVAILABLE
            and bool(self._anthropic_key)
            and self._anthropic_key != ""
        )

        if self._has_openai:
            logger.debug(f"[LLMClient] Primary: OpenAI ({self._openai_model})")
        if self._has_anthropic:
            logger.debug(f"[LLMClient] Fallback: Anthropic Claude ({self._anthropic_model})")
        if not self._has_openai and not self._has_anthropic:
            logger.warning("[LLMClient] No LLM provider configured — Vision will HOLD on every call")

    @property
    def active_provider(self) -> str:
        """Which provider will be used first."""
        if self._has_openai:
            return f"openai/{self._openai_model}"
        if self._has_anthropic:
            return f"anthropic/{self._anthropic_model}"
        return "none"

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def close(self) -> None:
        if self._openai_client is not None:
            await self._openai_client.close()
            self._openai_client = None
        if self._anthropic_client is not None:
            await self._anthropic_client.aclose()
            self._anthropic_client = None

    # ── Public API ────────────────────────────────────────────────────────────

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a chat request and return the raw text response.

        Tries OpenAI first; on any authentication/rate/API error
        automatically falls back to Anthropic Claude.

        Raises RuntimeError if no provider is available or both fail.
        """
        if not self._has_openai and not self._has_anthropic:
            raise RuntimeError("No LLM provider configured (set OPENAI_API_KEY or ANTHROPIC_API_KEY)")

        # Try OpenAI first
        if self._has_openai:
            try:
                return await self._call_openai(system_prompt, user_prompt)
            except (OpenAIAPIError, OpenAITimeoutError, OpenAIRateLimitError) as exc:
                logger.warning(
                    f"[LLMClient] OpenAI failed ({type(exc).__name__}: {exc}) "
                    f"— falling back to Claude"
                )
                if not self._has_anthropic:
                    raise RuntimeError(f"OpenAI error and no Claude fallback: {exc}") from exc
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[LLMClient] OpenAI unexpected error: {exc} — trying Claude")
                if not self._has_anthropic:
                    raise

        # Fallback: Anthropic Claude
        return await self._call_anthropic(system_prompt, user_prompt)

    # ── Internal: OpenAI ──────────────────────────────────────────────────────

    def _get_openai(self) -> "AsyncOpenAI":
        if self._openai_client is None:
            self._openai_client = AsyncOpenAI(api_key=self._openai_key)
        return self._openai_client

    async def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        client = self._get_openai()
        response = await client.chat.completions.create(
            model=self._openai_model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or "{}"

    # ── Internal: Anthropic ───────────────────────────────────────────────────

    def _get_anthropic(self) -> "AsyncAnthropic":
        if self._anthropic_client is None:
            self._anthropic_client = AsyncAnthropic(api_key=self._anthropic_key)
        return self._anthropic_client

    async def _call_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        client = self._get_anthropic()

        # Claude doesn't have a JSON mode — append instruction to system prompt
        system_with_json = (
            system_prompt
            + "\n\nCRITICAL: Your response MUST be a single valid JSON object only. "
            "No markdown, no code fences, no commentary. Output raw JSON."
        )

        response = await client.messages.create(
            model=self._anthropic_model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=system_with_json,
            messages=[{"role": "user", "content": user_prompt}],
        )
        # Extract text content
        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text
        return content.strip() or "{}"


def make_llm_client() -> LLMClient:
    """
    Factory that reads settings and constructs the LLMClient.
    Imported lazily to avoid circular imports.
    """
    from src.config.settings import settings  # noqa: WPS433

    return LLMClient(
        openai_key=getattr(settings, "openai_api_key", ""),
        openai_model=getattr(settings, "openai_model", "gpt-4o"),
        anthropic_key=getattr(settings, "anthropic_api_key", ""),
        anthropic_model=getattr(settings, "anthropic_model", "claude-sonnet-4-6"),
        temperature=getattr(settings, "openai_temperature", 0.2),
        max_tokens=getattr(settings, "openai_max_tokens", 2048),
    )
