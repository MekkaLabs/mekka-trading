"""
src/services/chat_history_compressor.py
=========================================
Story 161 — ChatHistoryCompressor: Context-Aware Prompt Compression.

Inspirado em:
  aider/history.py — "Aider automatically compresses the chat history when
  it approaches the context window limit. Older messages are summarized
  using a concise representation that preserves intent while reducing tokens."

  "The summarizer keeps the most recent N turns intact and replaces older
  turns with a structured summary: [SUMMARIZED: N messages, covering topics X, Y, Z]"

  "Aider uses a separate 'summarize' step that runs a small LLM call to
  compress the history, then resumes the main conversation."

Adaptação para Mekka Trading:
  Sem chamada LLM para comprimir — compressão estrutural determinística
  (igual à abordagem do BoundedOutput / ContextWindowTracker).

  O Vision e VisionMoA constroem prompts com múltiplas seções (análise de
  mercado, memórias, sinais anteriores). Com ciclos longos e muitos símbolos,
  o histórico de prompts pode crescer e ultrapassar o context window.

Problema resolvido:
  - Prompts Vision acumulam seções de ciclos anteriores sem compressão
  - Não há mecanismo para comprimir automaticamente quando se aproxima do limite
  - A compressão manual perde contexto valioso (preços, sinais anteriores)

Design:
  PromptTurn — uma mensagem do histórico (role + content + metadata)
  CompressionResult — resultado da compressão (turns comprimidos + stats)
  ChatHistoryCompressor — compressor com configuração
  compress_on_limit() — helper: comprime se ContextWindowTracker estiver > warn_pct

Estratégia de compressão (Aider-inspired):
  1. Mantém as últimas N turns completas (keep_last=5 por default)
  2. Turns antigas: extrai "key facts" via heurística (linhas com números,
     símbolos de trading, ações, preços)
  3. Formata antigas como: [COMPRESSED: N turns | key: BTC LONG $50k rr=2.1]
  4. Calcula tokens antes/depois para métricas

Uso:
    from src.services.chat_history_compressor import ChatHistoryCompressor

    compressor = ChatHistoryCompressor()
    history = [
        {"role": "system", "content": "Você é um trader..."},
        {"role": "user", "content": "Analise BTC: RSI=72 ..."},
        {"role": "assistant", "content": "LONG, entry=50k, sl=48k, tp=55k..."},
        # ... muitas turns anteriores
    ]
    result = compressor.compress(history, keep_last=3)
    compressed_history = result.turns
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Padrões para extração de "key facts" das mensagens comprimidas
# ---------------------------------------------------------------------------

# Detecta informações de trading relevantes para preservar no summary
_PRICE_RE = re.compile(r"\$[\d,]+(?:\.\d+)?|\b\d{4,7}(?:\.\d+)?\b")
_SYMBOL_RE = re.compile(r"\b([A-Z]{2,6}(?:USDT?|BTC|ETH|USD)?)\b")
_ACTION_RE = re.compile(r"\b(LONG|SHORT|HOLD|BUY|SELL|ENTRY|SL|TP|R:R|RSI|MACD|EMA)\b", re.IGNORECASE)
_CONFIDENCE_RE = re.compile(r"confidence[:\s=]+([0-9.]+)", re.IGNORECASE)
_VERDICT_RE = re.compile(r"\b(APPROVED|REJECTED|REDUCED|HOLD)\b", re.IGNORECASE)


def _extract_key_facts(content: str, max_facts: int = 8) -> str:
    """
    Extrai informações chave de uma mensagem de trading.

    Inspirado em aider/history.py — "preserve key facts when compressing".
    Heurística determinística (sem LLM call).
    """
    try:
        facts: list[str] = []

        # Símbolos de trading
        symbols = list(dict.fromkeys(_SYMBOL_RE.findall(content)))[:3]
        if symbols:
            facts.append(" ".join(symbols))

        # Ações (LONG/SHORT/HOLD)
        actions = list(dict.fromkeys(
            m.group(0).upper() for m in _ACTION_RE.finditer(content)
        ))[:4]
        if actions:
            facts.append(" ".join(actions))

        # Preços ($50000, 48000.0)
        prices = _PRICE_RE.findall(content)[:3]
        if prices:
            facts.append(" ".join(prices))

        # Confidence
        conf_m = _CONFIDENCE_RE.search(content)
        if conf_m:
            facts.append(f"conf={conf_m.group(1)}")

        # Verdict
        verdict_m = _VERDICT_RE.search(content)
        if verdict_m:
            facts.append(f"verdict={verdict_m.group(1).upper()}")

        return " | ".join(facts[:max_facts]) if facts else "..."
    except Exception:  # noqa: BLE001
        return "..."


# ---------------------------------------------------------------------------
# PromptTurn
# ---------------------------------------------------------------------------

@dataclass
class PromptTurn:
    """
    Uma mensagem do histórico de prompts.

    Compatível com o formato OpenAI: {"role": "...", "content": "..."}
    """
    role: str           # "system" | "user" | "assistant"
    content: str
    metadata: dict = field(default_factory=dict)
    tokens_approx: int = 0

    def __post_init__(self) -> None:
        if self.tokens_approx == 0:
            self.tokens_approx = max(1, len(self.content) // 4)

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PromptTurn":
        return cls(role=d.get("role", "user"), content=d.get("content", ""))


# ---------------------------------------------------------------------------
# CompressionResult
# ---------------------------------------------------------------------------

@dataclass
class CompressionResult:
    """Resultado da compressão do histórico."""
    turns: list[dict[str, str]]         # histórico comprimido (format OpenAI)
    original_turns: int = 0
    compressed_turns: int = 0
    kept_turns: int = 0
    tokens_before: int = 0
    tokens_after: int = 0
    compression_ratio: float = 0.0

    @property
    def tokens_saved(self) -> int:
        return max(0, self.tokens_before - self.tokens_after)

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_turns": self.original_turns,
            "compressed_turns": self.compressed_turns,
            "kept_turns": self.kept_turns,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "tokens_saved": self.tokens_saved,
            "compression_ratio": round(self.compression_ratio, 3),
        }


# ---------------------------------------------------------------------------
# ChatHistoryCompressor
# ---------------------------------------------------------------------------

class ChatHistoryCompressor:
    """
    Comprime histórico de prompts mantendo as N turns recentes intactas.

    Inspirado em aider/history.py:
    - Mantém `keep_last` turns mais recentes sem alteração
    - Agrupa turns antigas em um único bloco [COMPRESSED]
    - Preserva key facts extraídos heuristicamente (preços, símbolos, ações)
    - Nunca remove a system message (role="system")
    - Fail-silent: retorna histórico original em caso de erro

    Design decisions (Aider-inspired):
    - Compressão ESTRUTURAL (sem LLM) = determinística, sem custo adicional
    - Preserva contexto de trading mais recente = última N turns = estado atual
    - Compressão de turns antigas = reduz tokens mantendo essência
    """

    def __init__(
        self,
        keep_last: int = 5,
        min_turns_to_compress: int = 8,
        compress_role: str = "user",  # comprimir apenas user turns por default
        preserve_system: bool = True,
    ) -> None:
        self._keep_last = keep_last
        self._min_turns = min_turns_to_compress
        self._compress_role = compress_role
        self._preserve_system = preserve_system
        self._total_compressions: int = 0
        self._total_tokens_saved: int = 0

    def compress(
        self,
        history: list[dict[str, Any]],
        keep_last: Optional[int] = None,
    ) -> CompressionResult:
        """
        Comprime o histórico mantendo as N turns mais recentes intactas.

        Aider pattern: "Older messages are summarized using a concise
        representation that preserves intent while reducing tokens."

        Args:
            history: lista de dicts {"role": ..., "content": ...}
            keep_last: override do construtor (None = usa self._keep_last)

        Returns:
            CompressionResult com turns comprimidas e métricas.
        """
        try:
            n_keep = keep_last if keep_last is not None else self._keep_last

            if len(history) < self._min_turns:
                return CompressionResult(
                    turns=list(history),
                    original_turns=len(history),
                    kept_turns=len(history),
                    tokens_before=self._count_tokens(history),
                    tokens_after=self._count_tokens(history),
                    compression_ratio=1.0,
                )

            # Separar system message (preservar sempre)
            system_turns = []
            non_system = []
            for msg in history:
                if msg.get("role") == "system" and self._preserve_system:
                    system_turns.append(msg)
                else:
                    non_system.append(msg)

            # Dividir em antigas e recentes
            if len(non_system) <= n_keep:
                return CompressionResult(
                    turns=list(history),
                    original_turns=len(history),
                    kept_turns=len(history),
                    tokens_before=self._count_tokens(history),
                    tokens_after=self._count_tokens(history),
                    compression_ratio=1.0,
                )

            old_turns = non_system[:-n_keep]
            recent_turns = non_system[-n_keep:]

            # Comprimir turns antigas em um bloco [COMPRESSED]
            compressed_block = self._build_compressed_block(old_turns)

            # Montar histórico final
            result_turns: list[dict[str, str]] = []
            result_turns.extend(system_turns)
            result_turns.append(compressed_block)
            result_turns.extend(recent_turns)

            tokens_before = self._count_tokens(history)
            tokens_after = self._count_tokens(result_turns)
            ratio = tokens_after / max(1, tokens_before)

            self._total_compressions += 1
            self._total_tokens_saved += max(0, tokens_before - tokens_after)

            logger.debug(
                f"[ChatHistoryCompressor] Compressed {len(old_turns)} turns → 1 block; "
                f"tokens {tokens_before} → {tokens_after} ({ratio:.1%})"
            )

            return CompressionResult(
                turns=result_turns,
                original_turns=len(history),
                compressed_turns=len(old_turns),
                kept_turns=n_keep,
                tokens_before=tokens_before,
                tokens_after=tokens_after,
                compression_ratio=ratio,
            )

        except Exception:  # noqa: BLE001
            return CompressionResult(
                turns=list(history) if isinstance(history, list) else [],
                original_turns=len(history) if isinstance(history, list) else 0,
            )

    def _build_compressed_block(
        self,
        old_turns: list[dict[str, Any]],
    ) -> dict[str, str]:
        """
        Constrói bloco [COMPRESSED] com key facts das turns antigas.

        Formato Aider-inspired:
          [COMPRESSED: 8 turns | BTC ETH | LONG SHORT | $50000 $3200 | conf=0.75]
        """
        try:
            n = len(old_turns)
            all_content = " ".join(
                t.get("content", "")[:500] for t in old_turns  # primeiros 500 chars cada
            )
            key_facts = _extract_key_facts(all_content)
            timestamp = time.strftime("%H:%M:%S")

            summary = (
                f"[COMPRESSED: {n} earlier turns @ {timestamp} | {key_facts}]\n"
                f"(Earlier context compressed to save tokens. "
                f"Recent {self._keep_last} turns follow.)"
            )
            return {"role": "assistant", "content": summary}
        except Exception:  # noqa: BLE001
            return {"role": "assistant", "content": f"[COMPRESSED: {len(old_turns)} earlier turns]"}

    def compress_if_needed(
        self,
        history: list[dict[str, Any]],
        cycle_id: str = "",
        warn_pct: float = 0.80,
        model: str = "gpt-4o",
    ) -> CompressionResult:
        """
        Comprime APENAS se ContextWindowTracker indica que está próximo do limite.

        Padrão Aider: "compresses automatically when approaching the limit".
        Integra com Story 159 (ContextWindowTracker).

        Returns:
            CompressionResult — se não precisou comprimir, turns == history
        """
        try:
            from src.services.context_window_tracker import get_context_window_tracker
            tracker = get_context_window_tracker()

            # Calcular tokens atuais do histórico
            tokens = sum(max(1, len(t.get("content", "")) // 4) for t in history)

            # Registrar no tracker (se cycle_id fornecido)
            if cycle_id:
                tracker.record_stage(cycle_id, "chat_history", tokens, model=model)
                needs_compression = tracker.check_limit(cycle_id, warn_pct=warn_pct)
            else:
                # Estimativa sem tracker
                from src.services.context_window_tracker import MODEL_TOKEN_LIMITS
                limit = MODEL_TOKEN_LIMITS.get(model, MODEL_TOKEN_LIMITS["_default"])
                needs_compression = (tokens / limit) >= warn_pct

            if needs_compression:
                logger.info(
                    f"[ChatHistoryCompressor] Compressing history "
                    f"({tokens} tokens, {len(history)} turns)"
                )
                return self.compress(history)
            else:
                return CompressionResult(
                    turns=list(history),
                    original_turns=len(history),
                    kept_turns=len(history),
                    tokens_before=tokens,
                    tokens_after=tokens,
                    compression_ratio=1.0,
                )
        except Exception:  # noqa: BLE001
            return CompressionResult(turns=list(history) if isinstance(history, list) else [])

    @staticmethod
    def _count_tokens(history: list[dict[str, Any]]) -> int:
        """Estimativa de tokens do histórico."""
        try:
            return sum(max(1, len(t.get("content", "")) // 4) for t in history)
        except Exception:  # noqa: BLE001
            return 0

    def stats(self) -> dict[str, Any]:
        """Estatísticas de compressão para GET /api/chat-compressor."""
        return {
            "total_compressions": self._total_compressions,
            "total_tokens_saved": self._total_tokens_saved,
            "keep_last": self._keep_last,
            "min_turns_to_compress": self._min_turns,
            "preserve_system": self._preserve_system,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: Optional[ChatHistoryCompressor] = None


def get_chat_compressor(**kwargs: Any) -> ChatHistoryCompressor:
    """
    Retorna o ChatHistoryCompressor singleton.

    Se kwargs fornecido, cria nova instância (para testes).
    """
    global _instance
    if kwargs or _instance is None:
        _instance = ChatHistoryCompressor(**kwargs)
    return _instance


def reset_chat_compressor() -> None:
    """Reset singleton — usado em testes."""
    global _instance
    _instance = None
