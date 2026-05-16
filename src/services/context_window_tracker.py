"""
src/services/context_window_tracker.py
=======================================
Story 159 — ContextWindowTracker: Pipeline Context Window Management.

Inspirado no ContextWindowManager do SWE-agent (SWE-agent/SWE-agent):

  "The LLM Controller handles context window management, prompt injection,
   and output parsing."

  "last_n_observations: drops all but the most recent N observations from
   the messages array, keeping actions and thoughts in place but blanking
   out the stdout of older steps."

  "cache_control: adds Anthropic prompt-cache breakpoints to the last 2
   messages for cost savings."

  "if output length < 10,000 characters → full output; else → truncate"

Problema resolvido no Mekka Trading:
- Vision, VisionMoA e VisionCritic fazem chamadas LLM sem rastrear tamanho
- Um ciclo com muitos símbolos pode acumular tokens no contexto sem alertas
- Não há visibilidade de qual estágio do pipeline está consumindo mais contexto
- Context overflow silencioso → LLM trunca internamente sem aviso

Design (não-intrusivo):
  ContextWindowTracker — rastreia estimativas de token por estágio
  ContextWindowAlert — evento publicado quando se aproxima do limite
  get_context_window_tracker() — singleton
  record_stage(stage_name, content_or_tokens) — adiciona ao ciclo ativo
  check_limit() → bool — True se próximo do limite
  Integra com EventBus (Story 136) via 'context.window.alert'
  Integra com CycleEventLog (Story 154) via SLOW_CYCLE / STUCK_LOOP events

Estimativa de tokens (sem tiktoken):
  Heurística: ~4 chars por token (GPT-4 média)
  Suficiente para alertas — não precisa ser exato

Limites por modelo (configuráveis):
  gpt-4o:        128k tokens
  gpt-4o-mini:   128k tokens
  claude-3-5:    200k tokens
  default:        32k tokens (conservador)

Uso:
    from src.services.context_window_tracker import get_context_window_tracker

    tracker = get_context_window_tracker()
    cycle_id = "BTC_123"

    # Em cada estágio do pipeline:
    tracker.record_stage(cycle_id, "professor_x", analysis_text)
    tracker.record_stage(cycle_id, "vision_prompt", vision_prompt)
    tracker.record_stage(cycle_id, "vision_response", signal_json)

    # Verificar se está próximo do limite antes da próxima chamada LLM:
    if tracker.check_limit(cycle_id, warn_pct=0.80):
        # Compactar histórico antes de continuar
        pass

    # Resumo ao fim do ciclo:
    summary = tracker.cycle_summary(cycle_id)
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Configuração de limites por modelo
# ---------------------------------------------------------------------------

MODEL_TOKEN_LIMITS: dict[str, int] = {
    # OpenAI
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5-turbo": 16_385,
    # Anthropic
    "claude-3-5-sonnet": 200_000,
    "claude-3-5-haiku": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-opus-4-6": 200_000,
    # Default conservador
    "_default": 32_000,
}

_CHARS_PER_TOKEN = 4  # heurística GPT-4 média


def _estimate_tokens(content: Any) -> int:
    """Estimativa rápida de tokens sem tiktoken."""
    try:
        if isinstance(content, str):
            return max(1, len(content) // _CHARS_PER_TOKEN)
        if isinstance(content, (list, dict)):
            import json
            raw = json.dumps(content, default=str)
            return max(1, len(raw) // _CHARS_PER_TOKEN)
        if isinstance(content, int):
            return content  # já é token count
        return max(1, len(str(content)) // _CHARS_PER_TOKEN)
    except Exception:  # noqa: BLE001
        return 0


# ---------------------------------------------------------------------------
# StageRecord — snapshot de um estágio do pipeline
# ---------------------------------------------------------------------------

@dataclass
class StageRecord:
    """Registro de um estágio do pipeline com sua estimativa de tokens."""
    stage_name: str
    tokens_approx: int
    timestamp: float = field(default_factory=time.monotonic)
    content_preview: str = ""  # primeiros 100 chars para debug


# ---------------------------------------------------------------------------
# CycleWindow — janela de contexto de um ciclo
# ---------------------------------------------------------------------------

@dataclass
class CycleWindow:
    """Janela de contexto acumulada para um ciclo específico."""
    cycle_id: str
    symbol: str
    model: str = "_default"
    stages: list[StageRecord] = field(default_factory=list)
    started_at: float = field(default_factory=time.monotonic)

    @property
    def total_tokens(self) -> int:
        return sum(s.tokens_approx for s in self.stages)

    @property
    def token_limit(self) -> int:
        return MODEL_TOKEN_LIMITS.get(self.model, MODEL_TOKEN_LIMITS["_default"])

    @property
    def usage_pct(self) -> float:
        limit = self.token_limit
        if limit <= 0:
            return 0.0
        return self.total_tokens / limit

    @property
    def elapsed_s(self) -> float:
        return time.monotonic() - self.started_at

    def is_near_limit(self, warn_pct: float = 0.80) -> bool:
        return self.usage_pct >= warn_pct

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "symbol": self.symbol,
            "model": self.model,
            "total_tokens_approx": self.total_tokens,
            "token_limit": self.token_limit,
            "usage_pct": round(self.usage_pct, 3),
            "stages": [
                {
                    "name": s.stage_name,
                    "tokens": s.tokens_approx,
                    "preview": s.content_preview,
                }
                for s in self.stages
            ],
            "elapsed_s": round(self.elapsed_s, 3),
        }


# ---------------------------------------------------------------------------
# ContextWindowTracker — singleton
# ---------------------------------------------------------------------------

class ContextWindowTracker:
    """
    Rastreia estimativas de token por estágio do pipeline.

    Design principles (SWE-agent inspired):
    1. Fail-silent — nunca interrompe o trading cycle
    2. Estimativas aproximadas (sem tiktoken) são suficientes para alertas
    3. Rolling window: mantém no máximo `max_cycles` ciclos em memória
    4. Publicação via EventBus quando próximo do limite
    5. GET /api/context-window para visibilidade no dashboard
    """

    _DEFAULT_MAX_CYCLES = 200
    _DEFAULT_WARN_PCT = 0.80  # alerta em 80% do limite

    def __init__(
        self,
        max_cycles: int = _DEFAULT_MAX_CYCLES,
        warn_pct: float = _DEFAULT_WARN_PCT,
        default_model: str = "gpt-4o",
    ) -> None:
        self._max_cycles = max_cycles
        self._warn_pct = warn_pct
        self._default_model = default_model
        self._cycles: dict[str, CycleWindow] = {}
        self._cycle_order: list[str] = []  # para eviction FIFO
        self._total_alerts: int = 0
        self._total_stages_recorded: int = 0

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def start_cycle(
        self,
        cycle_id: str,
        symbol: str,
        model: Optional[str] = None,
    ) -> CycleWindow:
        """
        Inicia uma nova janela de contexto para um ciclo.

        Eviction FIFO quando max_cycles é atingido.
        """
        try:
            # Evict oldest if at capacity
            while len(self._cycles) >= self._max_cycles and self._cycle_order:
                oldest = self._cycle_order.pop(0)
                self._cycles.pop(oldest, None)

            window = CycleWindow(
                cycle_id=cycle_id,
                symbol=symbol,
                model=model or self._default_model,
            )
            self._cycles[cycle_id] = window
            self._cycle_order.append(cycle_id)
            return window
        except Exception:  # noqa: BLE001
            return CycleWindow(cycle_id=cycle_id, symbol=symbol)

    def record_stage(
        self,
        cycle_id: str,
        stage_name: str,
        content: Any,
        model: Optional[str] = None,
        symbol: str = "",
    ) -> int:
        """
        Registra um estágio do pipeline com seu conteúdo.

        Se o cycle_id não existe, cria automaticamente.
        Retorna a estimativa de tokens do estágio.
        """
        try:
            tokens = _estimate_tokens(content)
            preview = ""
            if isinstance(content, str):
                preview = content[:100]
            elif isinstance(content, dict):
                import json
                preview = json.dumps(content, default=str)[:100]

            if cycle_id not in self._cycles:
                self.start_cycle(cycle_id, symbol=symbol, model=model)

            window = self._cycles[cycle_id]
            window.stages.append(StageRecord(
                stage_name=stage_name,
                tokens_approx=tokens,
                content_preview=preview,
            ))
            self._total_stages_recorded += 1

            # Check limit after recording
            if window.is_near_limit(self._warn_pct):
                self._fire_alert(window)

            return tokens
        except Exception:  # noqa: BLE001
            return 0

    def _fire_alert(self, window: CycleWindow) -> None:
        """Publica alerta de context window via EventBus (fail-silent)."""
        try:
            self._total_alerts += 1
            logger.warning(
                f"[ContextWindowTracker] Context window alert: "
                f"cycle={window.cycle_id} symbol={window.symbol} "
                f"usage={window.usage_pct*100:.1f}% "
                f"({window.total_tokens}/{window.token_limit} tokens approx)"
            )
            # Publicar no EventBus para subscribers (ex: Telegram)
            from src.services.event_bus import get_event_bus  # lazy import
            get_event_bus().publish(
                "context.window.alert",
                {
                    "cycle_id": window.cycle_id,
                    "symbol": window.symbol,
                    "usage_pct": window.usage_pct,
                    "total_tokens": window.total_tokens,
                    "token_limit": window.token_limit,
                    "model": window.model,
                },
            )
        except Exception:  # noqa: BLE001
            pass  # EventBus não disponível → ignora

    # ------------------------------------------------------------------
    # Read paths
    # ------------------------------------------------------------------

    def check_limit(
        self,
        cycle_id: str,
        warn_pct: Optional[float] = None,
    ) -> bool:
        """
        Retorna True se o ciclo está próximo ou acima do limite.

        Uso antes de nova chamada LLM:
            if tracker.check_limit(cycle_id):
                # compactar histórico
                pass
        """
        try:
            window = self._cycles.get(cycle_id)
            if window is None:
                return False
            return window.is_near_limit(warn_pct or self._warn_pct)
        except Exception:  # noqa: BLE001
            return False

    def cycle_summary(self, cycle_id: str) -> dict[str, Any]:
        """Resumo detalhado de um ciclo específico."""
        try:
            window = self._cycles.get(cycle_id)
            if window is None:
                return {"cycle_id": cycle_id, "found": False}
            return {"found": True, **window.to_dict()}
        except Exception:  # noqa: BLE001
            return {"cycle_id": cycle_id, "found": False}

    def get_top_consumers(self, n: int = 10) -> list[dict[str, Any]]:
        """
        Retorna os N ciclos com maior consumo de tokens.

        Útil para identificar símbolos que causam context overflow.
        """
        try:
            sorted_cycles = sorted(
                self._cycles.values(),
                key=lambda w: w.total_tokens,
                reverse=True,
            )
            return [w.to_dict() for w in sorted_cycles[:n]]
        except Exception:  # noqa: BLE001
            return []

    def summary(self) -> dict[str, Any]:
        """
        Resumo global para GET /api/context-window.

        Inclui distribuição por estágio, consumidores top 5, alertas.
        """
        try:
            all_windows = list(self._cycles.values())
            if not all_windows:
                return {
                    "total_cycles_tracked": 0,
                    "total_stages_recorded": self._total_stages_recorded,
                    "total_alerts": self._total_alerts,
                    "top_consumers": [],
                    "stage_token_distribution": {},
                }

            # Aggregate token distribution by stage name
            stage_dist: dict[str, int] = defaultdict(int)
            for window in all_windows:
                for stage in window.stages:
                    stage_dist[stage.stage_name] += stage.tokens_approx

            # Top consumers
            top = sorted(
                all_windows, key=lambda w: w.total_tokens, reverse=True
            )[:5]

            # Near-limit cycles
            near_limit = [
                {"cycle_id": w.cycle_id, "symbol": w.symbol, "usage_pct": round(w.usage_pct, 3)}
                for w in all_windows
                if w.is_near_limit(self._warn_pct)
            ]

            return {
                "total_cycles_tracked": len(all_windows),
                "total_stages_recorded": self._total_stages_recorded,
                "total_alerts": self._total_alerts,
                "warn_threshold_pct": self._warn_pct,
                "default_model": self._default_model,
                "stage_token_distribution": dict(stage_dist),
                "top_consumers": [w.to_dict() for w in top],
                "near_limit_cycles": near_limit,
            }
        except Exception:  # noqa: BLE001
            return {"error": "summary_failed"}

    # ------------------------------------------------------------------
    # last_n_observations helper (SWE-agent history processor)
    # ------------------------------------------------------------------

    @staticmethod
    def compress_history(
        history: list[dict[str, Any]],
        keep_last_n: int = 5,
        payload_key: str = "payload",
        summary_key: str = "_compressed",
    ) -> list[dict[str, Any]]:
        """
        SWE-agent `last_n_observations` pattern aplicado ao audit trail.

        Comprime observações antigas (antes das últimas N) descartando
        payloads grandes mas preservando event_type, symbol, cycle_id.

        Args:
            history: lista de eventos do audit trail
            keep_last_n: quantas observações recentes manter intactas
            payload_key: chave do dict que contém dados grandes
            summary_key: marca eventos comprimidos com este flag

        Returns:
            Nova lista (não muta a original)
        """
        try:
            if len(history) <= keep_last_n:
                return history

            old = history[:-keep_last_n]
            recent = history[-keep_last_n:]

            # Comprimir eventos antigos: manter apenas metadados
            KEEP_KEYS = {"event_type", "symbol", "cycle_id", "timestamp", "agent"}
            compressed_old = []
            for evt in old:
                slim = {k: v for k, v in evt.items() if k in KEEP_KEYS}
                slim[summary_key] = True  # marcar como comprimido
                compressed_old.append(slim)

            return compressed_old + recent
        except Exception:  # noqa: BLE001
            return history


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: Optional[ContextWindowTracker] = None


def get_context_window_tracker(
    default_model: str = "gpt-4o",
    warn_pct: float = 0.80,
) -> ContextWindowTracker:
    """
    Retorna o ContextWindowTracker singleton.

    Parâmetros só têm efeito na primeira chamada.
    """
    global _instance
    if _instance is None:
        _instance = ContextWindowTracker(
            default_model=default_model,
            warn_pct=warn_pct,
        )
    return _instance


def reset_context_window_tracker() -> None:
    """Reset singleton — usado em testes."""
    global _instance
    _instance = None
