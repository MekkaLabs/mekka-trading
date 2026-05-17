"""
src/services/vision_retry_mixin.py
=====================================
Story 194 — VisionRetryMixin: exponential backoff para LLM calls do Vision.

Inspirado no padrão OpenHands RetryMixin (openhands/llm/retry_mixin.py):
  "The LLM retry system uses configurable exponential backoff.
   Retryable exceptions: RateLimitError, ServiceUnavailableError,
   APIConnectionError, Timeout, InternalServerError.
   Non-retryable: LLMMalformedActionError, LLMNoActionError (logic errors).
   Special case: LLMNoResponseError → adjust temperature to 1.0 to break
   deterministic empty-response loop (observed with Gemini models)."

No OpenHands:
  wait_time = min(retry_max_wait, max(retry_min_wait, retry_multiplier * 2^(attempt-1)))
  Defaults: multiplier=8, min=8s, max=64s → waits: 8, 16, 32, 64 (total: 120s)
  retry_listener: callback opcional para notificar UI / EventBus de cada tentativa

No Mekka, o equivalente é:
  VisionRetryMixin é um mixin/helper que qualquer LLM caller pode usar.
  Implementa exponential backoff puro em Python (sem tenacity).
  Suporta:
    - Retryable exceptions configuráveis (default: timeout, rate_limit, server_error)
    - Non-retryable exceptions configuráveis (malformed JSON, invalid signal)
    - Temperature jitter na última tentativa (evita loop de empty response)
    - retry_listener callback → EventBus ou logger
    - Fail-silent: após max_retries, retorna None (não crasha o pipeline)

Arquitetura
-----------
  RetryConfig     — parâmetros de retry (imutável)
  RetryAttempt    — contexto de uma tentativa (attempt_number, wait_s, exc)
  VisionRetryMixin
    ├── call_with_retry(fn, *args, **kwargs) → Any | None
    ├── _should_retry(exc) → bool
    ├── _wait_time(attempt) → float
    └── _on_retry(attempt_ctx)  — dispara retry_listener

Uso:
    from src.services.vision_retry_mixin import VisionRetryMixin, RetryConfig

    retry = VisionRetryMixin(RetryConfig(max_retries=3))
    result = retry.call_with_retry(llm_call_fn, prompt, max_tokens=500)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple, Type

from loguru import logger


# ---------------------------------------------------------------------------
# Exceptions que o mixin conhece por nome (sem importar libs externas)
# ---------------------------------------------------------------------------

# Strings de exception types que indicam erros TRANSIENTES (retentáveis)
_RETRYABLE_EXCEPTION_NAMES: Tuple[str, ...] = (
    "RateLimitError",
    "APIStatusError",
    "ServiceUnavailableError",
    "APIConnectionError",
    "Timeout",
    "TimeoutError",
    "InternalServerError",
    "ConnectionError",
    "ReadTimeout",
    "ConnectTimeout",
    "openai.APIConnectionError",
    "openai.RateLimitError",
    "anthropic.RateLimitError",
    "anthropic.APIConnectionError",
)

# Strings de exception types que NÃO devem ser retentados (erros de lógica)
_NON_RETRYABLE_EXCEPTION_NAMES: Tuple[str, ...] = (
    "LLMMalformedActionError",
    "LLMNoActionError",
    "LLMResponseError",
    "ValueError",
    "KeyError",
    "TypeError",
    "UserCancelledError",
)

# Token de "empty response" (Gemini e outros modelos podem retornar vazio)
_EMPTY_RESPONSE_SIGNALS: Tuple[str, ...] = (
    "empty response",
    "no response",
    "LLMNoResponseError",
    "EmptyResponseError",
)


# ---------------------------------------------------------------------------
# RetryConfig
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetryConfig:
    """
    Configuração de retry para LLM calls.

    Baseado no LLMConfig do OpenHands:
      num_retries=5, retry_multiplier=8.0, retry_min_wait=8s, retry_max_wait=64s.

    Para o Mekka, defaults são menores para não bloquear o pipeline:
      max_retries=3, multiplier=2.0, min_wait=1.0s, max_wait=8.0s.
    """
    max_retries: int = 3
    retry_multiplier: float = 2.0
    retry_min_wait_s: float = 1.0
    retry_max_wait_s: float = 8.0
    temperature_jitter_on_empty: bool = True
    temperature_jitter_value: float = 0.7


# ---------------------------------------------------------------------------
# RetryAttempt — contexto de uma tentativa (para o retry_listener)
# ---------------------------------------------------------------------------

@dataclass
class RetryAttempt:
    """Contexto passado ao retry_listener em cada tentativa."""
    attempt_number: int
    max_retries: int
    exception: Exception
    wait_s: float
    is_empty_response: bool = False

    def __str__(self) -> str:
        return (
            f"Attempt #{self.attempt_number}/{self.max_retries} "
            f"failed with {type(self.exception).__name__}: {self.exception}. "
            f"Waiting {self.wait_s:.1f}s..."
        )


# ---------------------------------------------------------------------------
# VisionRetryMixin
# ---------------------------------------------------------------------------

class VisionRetryMixin:
    """
    Mixin de retry exponencial para LLM calls do Vision.

    Padrão OpenHands RetryMixin:
    - Retryable: erros transientes (rate limit, timeout, server error)
    - Non-retryable: erros de lógica (malformed JSON, invalid signal)
    - Special: LLMNoResponseError → temperature jitter
    - retry_listener: callback para EventBus/logger

    Uso standalone (não precisa ser herdado):
        retry = VisionRetryMixin(RetryConfig(max_retries=3))
        result = retry.call_with_retry(my_llm_fn, prompt, max_tokens=500)
    """

    def __init__(
        self,
        config: Optional[RetryConfig] = None,
        retry_listener: Optional[Callable[[RetryAttempt], None]] = None,
    ) -> None:
        self.config = config or RetryConfig()
        self.retry_listener = retry_listener
        self._total_calls: int = 0
        self._total_retries: int = 0
        self._total_failures: int = 0
        self._total_successes: int = 0

    def call_with_retry(
        self,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Chama fn(*args, **kwargs) com retry exponencial.

        Args:
            fn:      Callable que representa a LLM call
            *args:   Argumentos posicionais
            **kwargs: Argumentos nomeados (aceita 'temperature' para jitter)

        Returns:
            Resultado de fn, ou None se todas as tentativas falharam (fail-silent).
        """
        self._total_calls += 1
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.config.max_retries + 2):  # +1 tentativa inicial
            try:
                result = fn(*args, **kwargs)
                self._total_successes += 1
                return result

            except Exception as exc:  # noqa: BLE001
                last_exc = exc

                # Não retenta erros de lógica
                if not self._should_retry(exc):
                    logger.debug(
                        f"[VisionRetryMixin] non-retryable {type(exc).__name__}: {exc}"
                    )
                    self._total_failures += 1
                    return None

                # Última tentativa — desiste
                if attempt > self.config.max_retries:
                    logger.debug(
                        f"[VisionRetryMixin] exhausted {self.config.max_retries} retries "
                        f"for {fn.__name__ if hasattr(fn, '__name__') else 'fn'}: {exc}"
                    )
                    self._total_failures += 1
                    return None

                wait_s = self._wait_time(attempt)
                is_empty = self._is_empty_response(exc)

                attempt_ctx = RetryAttempt(
                    attempt_number=attempt,
                    max_retries=self.config.max_retries,
                    exception=exc,
                    wait_s=wait_s,
                    is_empty_response=is_empty,
                )
                self._on_retry(attempt_ctx)
                self._total_retries += 1

                # Temperature jitter: se empty response, tenta com temperatura > 0
                if is_empty and self.config.temperature_jitter_on_empty:
                    kwargs["temperature"] = self.config.temperature_jitter_value
                    logger.debug(
                        f"[VisionRetryMixin] empty response — "
                        f"adjusting temperature to {self.config.temperature_jitter_value}"
                    )

                time.sleep(wait_s)

        # Nunca chega aqui, mas fail-safe
        self._total_failures += 1
        return None

    def _should_retry(self, exc: Exception) -> bool:
        """
        Determina se a exceção é retentável.

        Retentável: erros transientes (rate limit, timeout, server errors).
        Não-retentável: erros de lógica (ValueError, TypeError, malformed).
        """
        exc_type = type(exc).__name__
        exc_str = str(exc).lower()

        # Verifica explicitamente não-retentável primeiro
        for non_retry_name in _NON_RETRYABLE_EXCEPTION_NAMES:
            if non_retry_name in exc_type or non_retry_name in str(type(exc)):
                return False

        # Verifica retentável por nome de exception
        for retry_name in _RETRYABLE_EXCEPTION_NAMES:
            if retry_name in exc_type or retry_name in str(type(exc)):
                return True

        # Verifica por mensagem de erro (heurística)
        retryable_phrases = (
            "rate limit", "too many requests", "service unavailable",
            "timeout", "connection", "server error", "503", "429",
            "internal error", "overloaded", "capacity",
        )
        for phrase in retryable_phrases:
            if phrase in exc_str:
                return True

        # Default: retenta exceções genéricas (conservador para não bloquear pipeline)
        return True

    def _is_empty_response(self, exc: Exception) -> bool:
        """Detecta se a exceção representa uma resposta vazia do LLM."""
        exc_type = type(exc).__name__
        exc_str = str(exc).lower()

        for signal in _EMPTY_RESPONSE_SIGNALS:
            if signal.lower() in exc_type.lower() or signal.lower() in exc_str:
                return True
        return False

    def _wait_time(self, attempt: int) -> float:
        """
        Calcula o tempo de espera com exponential backoff.

        Fórmula (idêntica ao OpenHands):
          wait = min(max_wait, max(min_wait, multiplier * 2^(attempt-1)))
        """
        raw = self.config.retry_multiplier * (2 ** (attempt - 1))
        return min(
            self.config.retry_max_wait_s,
            max(self.config.retry_min_wait_s, raw),
        )

    def _on_retry(self, attempt_ctx: RetryAttempt) -> None:
        """Dispara retry_listener e log."""
        logger.debug(f"[VisionRetryMixin] {attempt_ctx}")
        if self.retry_listener is not None:
            try:
                self.retry_listener(attempt_ctx)
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"[VisionRetryMixin] retry_listener failed: {exc}")

    def summary(self) -> dict:
        return {
            "total_calls": self._total_calls,
            "total_retries": self._total_retries,
            "total_successes": self._total_successes,
            "total_failures": self._total_failures,
            "config": {
                "max_retries": self.config.max_retries,
                "retry_multiplier": self.config.retry_multiplier,
                "retry_min_wait_s": self.config.retry_min_wait_s,
                "retry_max_wait_s": self.config.retry_max_wait_s,
            },
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_retry_mixin: Optional[VisionRetryMixin] = None


def get_vision_retry_mixin() -> VisionRetryMixin:
    """Retorna o singleton global do VisionRetryMixin."""
    global _retry_mixin
    if _retry_mixin is None:
        try:
            from src.config.settings import settings
            max_retries = int(getattr(settings, "llm_max_retries", 3))
            min_wait = float(getattr(settings, "llm_retry_min_wait_s", 1.0))
            max_wait = float(getattr(settings, "llm_retry_max_wait_s", 8.0))
            config = RetryConfig(
                max_retries=max_retries,
                retry_min_wait_s=min_wait,
                retry_max_wait_s=max_wait,
            )
        except Exception:  # noqa: BLE001
            config = RetryConfig()
        _retry_mixin = VisionRetryMixin(config=config)
    return _retry_mixin


def reset_vision_retry_mixin() -> None:
    """Reseta o singleton — para testes."""
    global _retry_mixin
    _retry_mixin = None
