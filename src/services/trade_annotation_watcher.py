"""
src/services/trade_annotation_watcher.py
==========================================
Story 180 — TradeAnnotationWatcher: watch mode para anotações de analista.

Inspirado no padrão Aider Watch Mode + AI! Comments:
  "If you run aider with --watch-files, it will watch all files in your
   repo and look for AI coding instructions using one-liner comments
   (# … or // …) that either start or end with AI, AI!, or AI?"

  "AI! triggers aider to make changes. AI? triggers aider to answer."

No Mekka, o equivalente é um arquivo JSON que o analista edita em tempo real
com hints/overrides para o próximo ciclo de análise:

    data/trade_hints.json
    ─────────────────────
    {
      "hints": [
        {
          "symbol": "BTCUSDT",
          "bias": "LONG",
          "note": "FOMC amanhã — Fed dovish esperado",
          "strength": "STRONG",    // WEAK | MODERATE | STRONG
          "expires_at": null        // ISO datetime ou null (sem expiração)
        },
        {
          "symbol": "ETHUSDT",
          "bias": "SHORT",
          "note": "ETF outflows detectados",
          "strength": "MODERATE"
        }
      ]
    }

O watcher:
  1. Carrega o arquivo na inicialização
  2. Re-lê o arquivo a cada get_hint() se o mtime mudou (polling lazy)
  3. Retorna hints não-expirados para o símbolo solicitado
  4. Formata o hint como bloco de contexto para injeção no prompt Vision

Integração em Vision.run() (Story 180 block):
  hint = get_trade_annotation_watcher().get_prompt_block(symbol)
  if hint:
      prompt = prompt + "\n\n" + hint

O arquivo é opcional — se não existir, watcher retorna None silenciosamente.
Analistas podem editar o JSON enquanto o pipeline roda; a próxima leitura
captará as mudanças automaticamente.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# TradeHint
# ---------------------------------------------------------------------------

class TradeHint:
    """
    Uma anotação manual de analista para um símbolo específico.
    Equivalente a um "# AI! LONG BTC — FOMC amanhã" comment no Aider.
    """

    VALID_BIASES = {"LONG", "SHORT", "HOLD", "AVOID", "WATCH"}
    VALID_STRENGTHS = {"WEAK", "MODERATE", "STRONG"}

    def __init__(
        self,
        symbol: str,
        bias: str,
        note: str = "",
        strength: str = "MODERATE",
        expires_at: Optional[str] = None,
    ) -> None:
        self.symbol = symbol.upper().strip()
        self.bias = bias.upper().strip()
        self.note = note.strip()
        self.strength = strength.upper().strip()
        self.expires_at = expires_at

    @property
    def is_expired(self) -> bool:
        """True se o hint tem data de expiração e já passou."""
        if not self.expires_at:
            return False
        try:
            exp = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            return datetime.now(timezone.utc) > exp
        except (ValueError, AttributeError):
            return False

    @property
    def is_active(self) -> bool:
        return not self.is_expired

    def to_prompt_line(self) -> str:
        """
        Formata o hint como linha de instrução no estilo AI! comment do Aider.
        Injeta no prompt Vision como contexto de analyst override.
        """
        strength_prefix = {
            "STRONG":   "🔴 STRONG ANALYST OVERRIDE",
            "MODERATE": "🟡 ANALYST HINT",
            "WEAK":     "⚪ SOFT ANALYST SIGNAL",
        }.get(self.strength, "🟡 ANALYST HINT")

        parts = [f"{strength_prefix}: {self.bias} {self.symbol}"]
        if self.note:
            parts.append(f"Rationale: {self.note}")
        return " | ".join(parts)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "bias": self.bias,
            "note": self.note,
            "strength": self.strength,
            "expires_at": self.expires_at,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TradeHint":
        return cls(
            symbol=str(data.get("symbol", "")),
            bias=str(data.get("bias", "WATCH")),
            note=str(data.get("note", "")),
            strength=str(data.get("strength", "MODERATE")),
            expires_at=data.get("expires_at"),
        )


# ---------------------------------------------------------------------------
# TradeAnnotationWatcher
# ---------------------------------------------------------------------------

class TradeAnnotationWatcher:
    """
    Watcher de anotações de analista — lê data/trade_hints.json lazily.

    Padrão Aider Watch Mode: monitora arquivo por mudanças de mtime e
    re-carrega automaticamente quando o arquivo é editado.
    """

    def __init__(
        self,
        hints_file: str | Path = "data/trade_hints.json",
    ) -> None:
        self._hints_file = Path(hints_file)
        self._hints: list[TradeHint] = []
        self._last_mtime: float = 0.0
        self._load_count: int = 0

    def _maybe_reload(self) -> None:
        """
        Recarrega o arquivo se o mtime mudou desde a última leitura.
        Fail-silent: arquivo não existe ou JSON inválido → mantém hints anteriores.
        """
        try:
            if not self._hints_file.exists():
                return

            current_mtime = self._hints_file.stat().st_mtime
            if current_mtime <= self._last_mtime:
                return  # nada mudou

            raw = self._hints_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            hints_raw = data.get("hints", [])

            if not isinstance(hints_raw, list):
                logger.warning(f"[TradeAnnotationWatcher] 'hints' must be a list in {self._hints_file}")
                return

            new_hints = []
            for item in hints_raw:
                try:
                    h = TradeHint.from_dict(item)
                    if h.symbol:  # skip hints sem símbolo
                        new_hints.append(h)
                except Exception as exc:  # noqa: BLE001
                    logger.debug(f"[TradeAnnotationWatcher] skipping malformed hint {item}: {exc}")

            self._hints = new_hints
            self._last_mtime = current_mtime
            self._load_count += 1
            logger.debug(
                f"[TradeAnnotationWatcher] reloaded {len(new_hints)} hints "
                f"from {self._hints_file} (load #{self._load_count})"
            )

        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[TradeAnnotationWatcher] reload failed: {exc}")

    def get_hints(self, symbol: str) -> list[TradeHint]:
        """
        Retorna todos os hints ativos (não-expirados) para o símbolo.
        Reload automático se o arquivo mudou.
        """
        self._maybe_reload()
        sym_upper = symbol.upper().strip()
        # Match exato ou por prefixo (BTC matches BTCUSDT)
        return [
            h for h in self._hints
            if h.is_active and (
                h.symbol == sym_upper
                or sym_upper.startswith(h.symbol)
                or h.symbol.startswith(sym_upper)
            )
        ]

    def get_prompt_block(self, symbol: str) -> str:
        """
        Retorna um bloco de texto formatado para injeção no prompt Vision.
        Vazio se não há hints ativos para o símbolo.

        Formato:
          === Analyst Annotations ({symbol}) ===
          🔴 STRONG ANALYST OVERRIDE: LONG BTC | Rationale: FOMC amanhã
          🟡 ANALYST HINT: AVOID ETHUSDT | Rationale: ETF outflows
        """
        hints = self.get_hints(symbol)
        if not hints:
            return ""

        lines = [f"=== Analyst Annotations ({symbol.upper()}) ==="]
        for h in hints:
            lines.append(h.to_prompt_line())
        return "\n".join(lines)

    def get_all_active(self) -> list[TradeHint]:
        """Retorna todos os hints ativos independente de símbolo."""
        self._maybe_reload()
        return [h for h in self._hints if h.is_active]

    def add_hint(
        self,
        symbol: str,
        bias: str,
        note: str = "",
        strength: str = "MODERATE",
        expires_at: Optional[str] = None,
        persist: bool = True,
    ) -> TradeHint:
        """
        Adiciona um hint programaticamente (API/dashboard).
        Se persist=True, salva no arquivo JSON.
        """
        hint = TradeHint(
            symbol=symbol,
            bias=bias,
            note=note,
            strength=strength,
            expires_at=expires_at,
        )
        self._maybe_reload()
        self._hints.append(hint)

        if persist:
            self._save()

        return hint

    def clear_hints(self, symbol: str = "") -> int:
        """
        Remove todos os hints (ou apenas para um símbolo).
        Retorna número de hints removidos.
        """
        self._maybe_reload()
        before = len(self._hints)

        if symbol:
            sym_upper = symbol.upper().strip()
            self._hints = [
                h for h in self._hints
                if not (h.symbol == sym_upper or sym_upper.startswith(h.symbol))
            ]
        else:
            self._hints = []

        removed = before - len(self._hints)
        if removed > 0:
            self._save()
        return removed

    def _save(self) -> None:
        """Persiste hints atuais no arquivo JSON."""
        try:
            self._hints_file.parent.mkdir(parents=True, exist_ok=True)
            data = {"hints": [h.to_dict() for h in self._hints]}
            self._hints_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._last_mtime = self._hints_file.stat().st_mtime
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[TradeAnnotationWatcher] save failed: {exc}")

    def summary(self) -> dict:
        """Resumo do estado atual do watcher."""
        self._maybe_reload()
        active = [h for h in self._hints if h.is_active]
        by_symbol: dict[str, list[str]] = {}
        for h in active:
            by_symbol.setdefault(h.symbol, []).append(f"{h.bias}({h.strength})")
        return {
            "hints_file": str(self._hints_file),
            "file_exists": self._hints_file.exists(),
            "total_hints": len(self._hints),
            "active_hints": len(active),
            "load_count": self._load_count,
            "by_symbol": by_symbol,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_watcher: Optional[TradeAnnotationWatcher] = None


def get_trade_annotation_watcher(
    hints_file: str | Path = "data/trade_hints.json",
) -> TradeAnnotationWatcher:
    """Retorna o singleton global do TradeAnnotationWatcher."""
    global _watcher
    if _watcher is None:
        _watcher = TradeAnnotationWatcher(hints_file=hints_file)
    return _watcher


def reset_trade_annotation_watcher() -> None:
    """Reseta o singleton — para testes."""
    global _watcher
    _watcher = None
