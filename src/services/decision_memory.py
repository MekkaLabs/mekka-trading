"""Story 249 — Decision Memory.

Persiste cada decisão da Vision com resultado posterior, injeta reflexão
no próximo ciclo. Padrão inspirado no TradingAgents (TauricResearch):
decision log com outcome feedback. Ajuda a Vision calibrar confiança
baseada em performance histórica de decisões similares.

Fluxo:
  1. Após Vision emitir TradingSignal → save_decision() persiste o registro
  2. Quando trade fecha com PnL → record_outcome() atualiza resultado
  3. No início do próximo ciclo → get_recent_with_outcomes() + build_reflection_block()
     injeta reflexão contextual no prompt da Vision

Armazenamento: reutiliza AuditRecord via MekkaRepository.log_event()
com event="DECISION_MEMORY" para persistência sem novo modelo de DB.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

_log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Modelos de domínio
# ──────────────────────────────────────────────────────────


@dataclass
class DecisionRecord:
    """Snapshot de uma decisão da Vision no momento em que foi emitida."""

    cycle_id: str
    symbol: str
    signal_action: str            # LONG | SHORT | HOLD
    entry_price: float
    confidence: float             # 0.0 – 1.0
    debate_confidence: float      # confiança do DebateVerdict (0.0 se ausente)
    regime: str                   # BULL | BEAR | SIDEWAYS | VOLATILE | UNKNOWN
    timestamp: datetime


@dataclass
class DecisionOutcome:
    """Resultado de uma decisão após o trade fechar."""

    realized_pnl_pct: float       # % de PnL realizado (positivo = lucro)
    hit_target: bool              # atingiu take-profit
    duration_hours: float         # duração do trade em horas
    exit_reason: str              # TP | SL | MANUAL | EXPIRED


# ──────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────

_STORE_INSTANCE: "DecisionMemoryStore | None" = None


def get_decision_memory() -> "DecisionMemoryStore":
    """Retorna instância global do DecisionMemoryStore (lazy init)."""
    global _STORE_INSTANCE  # noqa: PLW0603
    if _STORE_INSTANCE is None:
        _STORE_INSTANCE = DecisionMemoryStore()
    return _STORE_INSTANCE


# ──────────────────────────────────────────────────────────
# Store principal
# ──────────────────────────────────────────────────────────


class DecisionMemoryStore:
    """Salva e recupera decisões da Vision para reflexão contextual.

    Usa MekkaRepository.log_event() com event="DECISION_MEMORY" para
    persistência, evitando criação de novo modelo de DB.

    Formato do payload em AuditRecord.payload (JSON):
    {
        "type": "decision",       # "decision" | "outcome"
        "cycle_id": "...",
        "symbol": "BTC",
        "action": "LONG",
        "confidence": 0.82,
        "debate_confidence": 0.75,
        "regime": "BULL",
        "entry_price": 67000.0,
        "timestamp": "2026-01-01T10:00:00",
        # campos de outcome (type="outcome"):
        "pnl_pct": 2.5,
        "hit_target": true,
        "duration_hours": 4.5,
        "exit_reason": "TP"
    }
    """

    # Evento marcador no AuditRecord
    _EVENT_DECISION = "DECISION_MEMORY"
    _EVENT_OUTCOME = "DECISION_OUTCOME"

    def summary(self) -> dict:
        """INV-3 (2026-05-29) — snapshot pro /api/memory/snapshot.
        Conta decisions, outcomes, win_rate via audit_log direto."""
        out = {
            "total_decisions": 0, "with_outcome": 0, "pending": 0,
            "win_rate": None, "last_decision_ts": None,
        }
        try:
            from pathlib import Path as _P
            import sqlite3 as _sqlite3
            db = _P(__file__).resolve().parents[2] / "data" / "mekka_trading.db"
            if not db.exists():
                return out
            conn = _sqlite3.connect(str(db))
            try:
                cur = conn.execute(
                    "SELECT COUNT(*) FROM audit_log WHERE event='DECISION_MEMORY'"
                )
                out["total_decisions"] = int(cur.fetchone()[0] or 0)
                cur = conn.execute(
                    "SELECT COUNT(*) FROM audit_log WHERE event='DECISION_OUTCOME'"
                )
                out["with_outcome"] = int(cur.fetchone()[0] or 0)
                out["pending"] = max(0, out["total_decisions"] - out["with_outcome"])
                cur = conn.execute(
                    "SELECT MAX(timestamp) FROM audit_log WHERE event='DECISION_MEMORY'"
                )
                ts = cur.fetchone()[0]
                if ts:
                    out["last_decision_ts"] = ts
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[DecisionMemory] summary failed: {exc}")
        return out

    # ── escrita ──────────────────────────────────────────

    async def save_decision(self, record: DecisionRecord) -> None:
        """Persiste decisão da Vision no AuditRecord."""
        try:
            from src.persistence.repository import MekkaRepository  # noqa: WPS433

            payload: dict[str, Any] = {
                "type": "decision",
                "cycle_id": record.cycle_id,
                "symbol": record.symbol,
                "action": record.signal_action,
                "confidence": round(record.confidence, 4),
                "debate_confidence": round(record.debate_confidence, 4),
                "regime": record.regime,
                "entry_price": record.entry_price,
                "timestamp": record.timestamp.isoformat(),
            }
            await MekkaRepository.log_event(
                agent="Vision",
                event=self._EVENT_DECISION,
                message=f"Decision saved: {record.signal_action} {record.symbol} conf={record.confidence:.0%}",
                symbol=record.symbol,
                severity="INFO",
                payload=payload,
            )
            _log.debug(
                "[249] Decision saved: %s %s cycle=%s",
                record.signal_action,
                record.symbol,
                record.cycle_id,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning("[249] save_decision failed (non-critical): %s", exc)

    async def record_outcome(
        self,
        cycle_id: str,
        symbol: str,
        outcome: DecisionOutcome,
    ) -> None:
        """Registra resultado de uma decisão após o trade fechar."""
        try:
            from src.persistence.repository import MekkaRepository  # noqa: WPS433

            payload: dict[str, Any] = {
                "type": "outcome",
                "cycle_id": cycle_id,
                "symbol": symbol,
                "pnl_pct": round(outcome.realized_pnl_pct, 4),
                "hit_target": outcome.hit_target,
                "duration_hours": round(outcome.duration_hours, 2),
                "exit_reason": outcome.exit_reason,
                "timestamp": datetime.utcnow().isoformat(),
            }
            result_label = "✓ LUCRO" if outcome.realized_pnl_pct > 0 else "✗ PERDA"
            await MekkaRepository.log_event(
                agent="Vision",
                event=self._EVENT_OUTCOME,
                message=(
                    f"Outcome recorded: {symbol} {result_label} "
                    f"pnl={outcome.realized_pnl_pct:+.2f}% exit={outcome.exit_reason}"
                ),
                symbol=symbol,
                severity="INFO",
                payload=payload,
            )
            _log.debug(
                "[249] Outcome recorded: %s cycle=%s pnl=%.2f%%",
                symbol,
                cycle_id,
                outcome.realized_pnl_pct,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning("[249] record_outcome failed (non-critical): %s", exc)

    # ── leitura ──────────────────────────────────────────

    async def get_recent_with_outcomes(
        self,
        symbol: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Retorna decisões recentes com outcomes associados para um símbolo.

        Faz cross-join em memória entre eventos DECISION e OUTCOME
        pelo cycle_id. Retorna lista ordenada do mais recente ao mais antigo.
        """
        try:
            from src.persistence.repository import MekkaRepository  # noqa: WPS433

            # Busca eventos de decisão e outcome para o símbolo
            decisions_raw = await MekkaRepository.list_audit_events(
                agent="Vision",
                event=self._EVENT_DECISION,
                symbol=symbol,
                limit=limit * 2,  # busca extra para ter folga
            )
            outcomes_raw = await MekkaRepository.list_audit_events(
                agent="Vision",
                event=self._EVENT_OUTCOME,
                symbol=symbol,
                limit=limit * 2,
            )

            # Index outcomes por cycle_id
            outcomes_by_cycle: dict[str, dict[str, Any]] = {}
            for rec in outcomes_raw:
                payload = rec.get("payload") or {}
                if isinstance(payload, str):
                    payload = json.loads(payload)
                cid = payload.get("cycle_id", "")
                if cid:
                    outcomes_by_cycle[cid] = payload

            # Combina decisões com outcomes
            combined: list[dict[str, Any]] = []
            for rec in decisions_raw:
                payload = rec.get("payload") or {}
                if isinstance(payload, str):
                    payload = json.loads(payload)

                cid = payload.get("cycle_id", "")
                entry: dict[str, Any] = {
                    "cycle_id": cid,
                    "symbol": payload.get("symbol", symbol),
                    "action": payload.get("action", "HOLD"),
                    "confidence": payload.get("confidence", 0.5),
                    "debate_confidence": payload.get("debate_confidence", 0.0),
                    "regime": payload.get("regime", "UNKNOWN"),
                    "entry_price": payload.get("entry_price", 0.0),
                    "timestamp": payload.get("timestamp", ""),
                    "outcome": outcomes_by_cycle.get(cid),
                }
                combined.append(entry)
                if len(combined) >= limit:
                    break

            return combined

        except Exception as exc:  # noqa: BLE001
            _log.debug("[249] get_recent_with_outcomes failed (non-critical): %s", exc)
            return []

    # ── construção do bloco de reflexão ──────────────────

    def build_reflection_block(
        self,
        decisions: list[dict[str, Any]],
        symbol: str,
    ) -> str:
        """Formata decisões recentes como bloco de reflexão para a Vision.

        Cada entrada inclui: ação, regime, confiança e resultado (se disponível).
        O modelo recebe contexto de acertos/erros recentes para calibrar a decisão atual.
        """
        if not decisions:
            return ""

        lines: list[str] = [
            f"## 🧠 Decision Memory — Histórico Recente ({symbol})",
            "",
            "Suas últimas decisões para este símbolo e seus resultados:",
            "",
        ]

        wins = 0
        losses = 0
        total_pnl = 0.0

        for i, d in enumerate(decisions, 1):
            action = d.get("action", "HOLD")
            conf = d.get("confidence", 0.0)
            debate_conf = d.get("debate_confidence", 0.0)
            regime = d.get("regime", "UNKNOWN")
            ts = d.get("timestamp", "")[:10] if d.get("timestamp") else "?"

            outcome = d.get("outcome")
            if outcome:
                pnl = outcome.get("pnl_pct", 0.0)
                hit = outcome.get("hit_target", False)
                exit_r = outcome.get("exit_reason", "?")
                dur = outcome.get("duration_hours", 0.0)
                total_pnl += pnl

                if pnl > 0:
                    wins += 1
                    result_icon = "✅"
                else:
                    losses += 1
                    result_icon = "❌"

                outcome_str = (
                    f"{result_icon} PnL: {pnl:+.2f}% | "
                    f"Saída: {exit_r} | "
                    f"Duração: {dur:.1f}h | "
                    f"Target atingido: {'Sim' if hit else 'Não'}"
                )
            else:
                outcome_str = "⏳ Aguardando resultado"

            debate_str = f" | Debate conf: {debate_conf:.0%}" if debate_conf > 0 else ""
            lines.append(
                f"{i}. [{ts}] **{action}** | Regime: {regime} | "
                f"Confiança: {conf:.0%}{debate_str}\n"
                f"   → {outcome_str}"
            )

        # Sumário de performance
        total_with_outcome = wins + losses
        if total_with_outcome > 0:
            win_rate = wins / total_with_outcome
            lines.extend([
                "",
                f"**Resumo:** {wins}W/{losses}L | "
                f"Win rate: {win_rate:.0%} | "
                f"PnL total: {total_pnl:+.2f}%",
            ])

            # Insight reflexivo baseado no histórico
            if win_rate >= 0.7:
                lines.append(
                    "💡 *Seu histórico recente neste símbolo é forte. "
                    "Mantenha disciplina de entradas de alta qualidade.*"
                )
            elif win_rate <= 0.3:
                lines.append(
                    "⚠️ *Histórico recente fraco neste símbolo. "
                    "Considere aumentar o limiar de confiança ou reduzir tamanho.*"
                )
            elif total_pnl < -5.0:
                lines.append(
                    "⚠️ *PnL acumulado negativo recente. "
                    "Seja mais seletivo nas entradas neste ciclo.*"
                )

        lines.append("")
        return "\n".join(lines)

    # ── utilitário síncrono para contextos não-async ──────

    def build_reflection_block_from_closed_trades(
        self,
        closed_trades: list[Any],
        symbol: str,
        limit: int = 5,
    ) -> str:
        """Constrói bloco de reflexão a partir de TradeRecord fechados (fallback síncrono).

        Usado quando o loop async não está disponível. Recebe lista de
        TradeRecord do MekkaRepository.list_recent_closed_trades().
        """
        if not closed_trades:
            return ""

        decisions: list[dict[str, Any]] = []
        for trade in closed_trades[:limit]:
            # TradeRecord tem metadata dict com realized_pnl_usd, entry_price etc.
            meta = getattr(trade, "metadata", {}) or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:  # noqa: BLE001
                    meta = {}

            pnl_usd = float(meta.get("realized_pnl_usd", 0.0))
            entry_price = float(meta.get("entry_price", 0.0))
            exit_price = float(meta.get("exit_price", 0.0))
            pnl_pct = 0.0
            if entry_price > 0:
                pnl_pct = ((exit_price - entry_price) / entry_price) * 100

            side = getattr(trade, "side", meta.get("side", "LONG"))
            exit_reason = meta.get("exit_reason", "UNKNOWN")

            # Estima duração em horas
            created = getattr(trade, "created_at", None)
            updated = getattr(trade, "updated_at", None)
            duration_h = 0.0
            if created and updated:
                try:
                    duration_h = (updated - created).total_seconds() / 3600.0
                except Exception:  # noqa: BLE001
                    pass

            decisions.append({
                "cycle_id": str(getattr(trade, "id", "?")),
                "symbol": getattr(trade, "symbol", symbol),
                "action": side.upper() if side else "LONG",
                "confidence": float(meta.get("confidence", 0.5)),
                "debate_confidence": 0.0,
                "regime": meta.get("regime", "UNKNOWN"),
                "entry_price": entry_price,
                "timestamp": created.isoformat() if created else "",
                "outcome": {
                    "pnl_pct": round(pnl_pct, 2),
                    "hit_target": exit_reason == "TP",
                    "duration_hours": round(duration_h, 1),
                    "exit_reason": exit_reason,
                },
            })

        return self.build_reflection_block(decisions, symbol)
