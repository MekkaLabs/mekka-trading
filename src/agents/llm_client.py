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
import time
from typing import Any, Optional, Tuple

from loguru import logger

# Story 142 — LLM Cost Metrics
# Cost table (USD per 1M tokens) — approximate, valid as of 2026-05.
# Update when provider pricing changes.
_COST_TABLE: dict[str, dict[str, float]] = {
    "gpt-4o":           {"input": 5.00,  "output": 15.00},
    "gpt-4o-mini":      {"input": 0.15,  "output": 0.60},
    "gpt-4-turbo":      {"input": 10.00, "output": 30.00},
    "claude-opus-4-6":  {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-6":{"input": 3.00,  "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25},
}
_DEFAULT_COST = {"input": 5.00, "output": 15.00}  # conservative fallback


def _estimate_cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    """Estimate API cost in USD for a single LLM call."""
    rates = _COST_TABLE.get(model, _DEFAULT_COST)
    return (tokens_in * rates["input"] + tokens_out * rates["output"]) / 1_000_000

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

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        agent_id: str = "",
    ) -> str:
        """
        Send a chat request and return the raw text response.

        Tries OpenAI first; on any authentication/rate/API error
        automatically falls back to Anthropic Claude.

        Story 142: publishes `llm.call.completed` event with token usage,
        estimated cost, provider, model, and agent_id for observability.

        Raises RuntimeError if no provider is available or both fail.
        """
        if not self._has_openai and not self._has_anthropic:
            raise RuntimeError("No LLM provider configured (set OPENAI_API_KEY or ANTHROPIC_API_KEY)")

        _t0 = time.monotonic()
        _provider = "none"
        _model = "none"
        _tokens_in = 0
        _tokens_out = 0
        _content = "{}"

        try:
            # Try OpenAI first
            if self._has_openai:
                try:
                    _content, _tokens_in, _tokens_out = await self._call_openai(
                        system_prompt, user_prompt
                    )
                    _provider = "openai"
                    _model = self._openai_model
                except (OpenAIAPIError, OpenAITimeoutError, OpenAIRateLimitError) as exc:
                    logger.warning(
                        f"[LLMClient] OpenAI failed ({type(exc).__name__}: {exc}) "
                        f"— falling back to Claude"
                    )
                    if not self._has_anthropic:
                        raise RuntimeError(f"OpenAI error and no Claude fallback: {exc}") from exc
                    _content, _tokens_in, _tokens_out = await self._call_anthropic(
                        system_prompt, user_prompt
                    )
                    _provider = "anthropic"
                    _model = self._anthropic_model
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"[LLMClient] OpenAI unexpected error: {exc} — trying Claude")
                    if not self._has_anthropic:
                        raise
                    _content, _tokens_in, _tokens_out = await self._call_anthropic(
                        system_prompt, user_prompt
                    )
                    _provider = "anthropic"
                    _model = self._anthropic_model
            else:
                # OpenAI not configured — use Anthropic directly
                _content, _tokens_in, _tokens_out = await self._call_anthropic(
                    system_prompt, user_prompt
                )
                _provider = "anthropic"
                _model = self._anthropic_model

            return _content

        finally:
            # Story 142 — publish cost event (fail-silent, always in finally)
            _elapsed_ms = round((time.monotonic() - _t0) * 1000, 1)
            _cost = _estimate_cost_usd(_model, _tokens_in, _tokens_out)
            try:
                from src.services.event_bus import get_event_bus  # noqa: WPS433
                _eb = get_event_bus()
                _eb.publish_sync("llm.call.completed", {
                    "provider": _provider,
                    "model": _model,
                    "agent_id": agent_id,
                    "tokens_in": _tokens_in,
                    "tokens_out": _tokens_out,
                    "cost_usd": round(_cost, 8),
                    "elapsed_ms": _elapsed_ms,
                })
                logger.debug(
                    f"[LLMClient] {_provider}/{_model} agent={agent_id or '?'} "
                    f"in={_tokens_in} out={_tokens_out} "
                    f"cost=${_cost:.6f} {_elapsed_ms}ms"
                )
            except Exception as _ev_exc:  # noqa: BLE001
                logger.debug(f"[LLMClient] cost event publish skipped: {_ev_exc}")

    # ── Internal: OpenAI ──────────────────────────────────────────────────────

    def _get_openai(self) -> "AsyncOpenAI":
        if self._openai_client is None:
            self._openai_client = AsyncOpenAI(api_key=self._openai_key)
        return self._openai_client

    async def _call_openai(
        self, system_prompt: str, user_prompt: str
    ) -> Tuple[str, int, int]:
        """Returns (content, tokens_in, tokens_out)."""
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
        content = response.choices[0].message.content or "{}"
        usage = response.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0
        return content, tokens_in, tokens_out

    # ── Internal: Anthropic ───────────────────────────────────────────────────

    def _get_anthropic(self) -> "AsyncAnthropic":
        if self._anthropic_client is None:
            self._anthropic_client = AsyncAnthropic(api_key=self._anthropic_key)
        return self._anthropic_client

    async def _call_anthropic(
        self, system_prompt: str, user_prompt: str
    ) -> Tuple[str, int, int]:
        """Returns (content, tokens_in, tokens_out)."""
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
        usage = response.usage
        tokens_in = usage.input_tokens if usage else 0
        tokens_out = usage.output_tokens if usage else 0
        return content.strip() or "{}", tokens_in, tokens_out


    # ── Structured Output (Story 250) ─────────────────────────────────────────

    async def chat_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type,
        agent_id: str = "",
    ) -> Any:
        """Structured output — returns a validated Pydantic model or None.

        OpenAI: uses client.beta.chat.completions.parse() for guaranteed schema.
        Anthropic: falls back to JSON mode + model_validate().

        Returns None on any error; caller should fall back to raw JSON path.
        Story 250 — Vision Structured Output.
        """
        if not self._has_openai and not self._has_anthropic:
            return None

        _t0 = time.monotonic()
        _provider = "none"
        _model = "none"
        _tokens_in = 0
        _tokens_out = 0

        try:
            if self._has_openai:
                try:
                    parsed, _tokens_in, _tokens_out = await self._call_openai_structured(
                        system_prompt, user_prompt, response_model
                    )
                    _provider = "openai"
                    _model = self._openai_model
                except (OpenAIAPIError, OpenAITimeoutError, OpenAIRateLimitError) as exc:
                    logger.warning(
                        f"[LLMClient] OpenAI structured failed ({type(exc).__name__}: {exc})"
                        " — falling back to Claude"
                    )
                    if not self._has_anthropic:
                        return None
                    parsed, _tokens_in, _tokens_out = await self._call_anthropic_structured(
                        system_prompt, user_prompt, response_model
                    )
                    _provider = "anthropic"
                    _model = self._anthropic_model
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        f"[LLMClient] OpenAI structured unexpected: {exc} — trying Claude"
                    )
                    if not self._has_anthropic:
                        return None
                    parsed, _tokens_in, _tokens_out = await self._call_anthropic_structured(
                        system_prompt, user_prompt, response_model
                    )
                    _provider = "anthropic"
                    _model = self._anthropic_model
            else:
                parsed, _tokens_in, _tokens_out = await self._call_anthropic_structured(
                    system_prompt, user_prompt, response_model
                )
                _provider = "anthropic"
                _model = self._anthropic_model

            return parsed

        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[LLMClient] chat_structured failed entirely: {exc}")
            return None

        finally:
            _elapsed_ms = round((time.monotonic() - _t0) * 1000, 1)
            _cost = _estimate_cost_usd(_model, _tokens_in, _tokens_out)
            try:
                from src.services.event_bus import get_event_bus  # noqa: WPS433
                _eb = get_event_bus()
                _eb.publish_sync("llm.call.completed", {
                    "provider": _provider,
                    "model": _model,
                    "agent_id": agent_id,
                    "tokens_in": _tokens_in,
                    "tokens_out": _tokens_out,
                    "cost_usd": round(_cost, 8),
                    "elapsed_ms": _elapsed_ms,
                    "structured": True,
                })
                logger.debug(
                    f"[LLMClient] structured {_provider}/{_model} agent={agent_id or '?'} "
                    f"in={_tokens_in} out={_tokens_out} "
                    f"cost=${_cost:.6f} {_elapsed_ms}ms"
                )
            except Exception as _ev_exc:  # noqa: BLE001
                logger.debug(f"[LLMClient] structured cost event publish skipped: {_ev_exc}")

    async def _call_openai_structured(
        self, system_prompt: str, user_prompt: str, response_model: type
    ) -> Tuple[Any, int, int]:
        """OpenAI Structured Output via beta.chat.completions.parse().

        Returns (parsed_model_instance, tokens_in, tokens_out).
        """
        client = self._get_openai()
        response = await client.beta.chat.completions.parse(
            model=self._openai_model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            response_format=response_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        parsed = response.choices[0].message.parsed
        usage = response.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0
        return parsed, tokens_in, tokens_out

    async def _call_anthropic_structured(
        self, system_prompt: str, user_prompt: str, response_model: type
    ) -> Tuple[Any, int, int]:
        """Anthropic structured output — JSON mode + model_validate().

        Anthropic não tem structured output nativo; usa JSON mode e
        valida via Pydantic model_validate().
        Returns (parsed_model_instance, tokens_in, tokens_out).
        """
        import json as _json  # noqa: WPS433
        content, tokens_in, tokens_out = await self._call_anthropic(system_prompt, user_prompt)
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            cleaned = cleaned.strip()
        payload = _json.loads(cleaned)
        parsed = response_model.model_validate(payload)
        return parsed, tokens_in, tokens_out


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
