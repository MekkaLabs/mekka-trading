"""
src/services/debate_verdict_logger.py
========================================
DebateVerdictLogger — Story 242 (Milestone 39: Multiagent Debate).

Persiste o DebateVerdict no audit_log do SQLite para rastreabilidade
completa do debate multiagente. Usa o padrão existente de log de eventos.

Uso::

    logger_svc = DebateVerdictLogger()
    await logger_svc.log(verdict, symbol="BTC", cycle_id="cycle-001")
"""
from __future__ import annotations

from typing import Optional

from loguru import logger

from src.services.debate_moderator import DebateVerdict


class DebateVerdictLogger:
    """
    Persiste DebateVerdict no audit_log via MekkaRepository.

    Formato do registro
    -------------------
    agent   : "DebateModerator"
    event   : "DEBATE_VERDICT"
    symbol  : símbolo debatido
    payload : {
        consensus_action,
        consensus_confidence,
        total_votes,
        rounds_run,
        dissent_agents,
        votes: [{agent, action, confidence, round, reasoning}],
        notes,
    }
    """

    def __init__(self) -> None:
        self._log = logger.bind(service="DebateVerdictLogger")

    async def log(
        self,
        verdict: DebateVerdict,
        symbol: Optional[str] = None,
        cycle_id: Optional[str] = None,
    ) -> bool:
        """
        Grava o DebateVerdict no audit_log.

        Returns:
            True se gravado com sucesso, False caso contrário.
        """
        from src.services.consensus_weighter import ConsensusWeighter
        try:
            from src.persistence.repository import MekkaRepository

            weighter   = ConsensusWeighter()
            vote_table = weighter.summary_table(verdict.votes)

            payload = {
                "consensus_action":     verdict.consensus_action,
                "consensus_confidence": verdict.consensus_confidence,
                "total_votes":          verdict.total_votes,
                "rounds_run":           verdict.rounds_run,
                "dissent_agents":       verdict.dissent_agents,
                "notes":                verdict.notes,
                "votes":                vote_table,
            }
            if cycle_id:
                payload["cycle_id"] = cycle_id

            await MekkaRepository.log_event(
                agent="DebateModerator",
                event="DEBATE_VERDICT",
                symbol=symbol,
                payload=payload,
            )

            self._log.info(
                f"DebateVerdictLogger: gravado — "
                f"symbol={symbol} action={verdict.consensus_action} "
                f"conf={verdict.consensus_confidence:.0%} "
                f"votos={verdict.total_votes} rodadas={verdict.rounds_run}"
            )
            return True

        except Exception as exc:
            self._log.warning(f"DebateVerdictLogger: falha ao gravar — {exc}")
            return False

    async def fetch_recent(
        self,
        symbol: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        """
        Recupera os últimos DebateVerdicts do audit_log.

        Returns:
            Lista de dicts com os campos do payload + timestamp.
        """
        try:
            from src.persistence.repository import MekkaRepository
            rows = await MekkaRepository.list_recent_audit(limit=limit * 5)

            debate_rows = [
                r for r in rows
                if r.agent == "DebateModerator" and r.event == "DEBATE_VERDICT"
                and (symbol is None or (r.symbol or "").upper().startswith(symbol.upper()))
            ][-limit:]

            return [
                {
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                    "symbol":    r.symbol,
                    **(r.payload or {}),
                }
                for r in debate_rows
            ]
        except Exception as exc:
            self._log.warning(f"DebateVerdictLogger.fetch_recent: {exc}")
            return []
