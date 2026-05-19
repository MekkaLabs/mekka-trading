"""Story 251 — Cycle Checkpoint.

CycleCheckpointStore: salva e restaura o estado intermediário de um ciclo
de trading no banco de dados, permitindo que NickFury retome de onde parou
após um crash — sem re-executar agentes já completados.

Padrão de persistência: reutiliza MekkaRepository.log_event() + list_audit_events()
(mesmo padrão da Story 249 — Decision Memory), sem dependência de LangGraph.

Etapas suportadas:
  ANALYSIS  — resultado do ProfessorX (MarketAnalysis)
  SIGNAL    — sinal produzido pela Vision (TradingSignal)

Uso em NickFury._cycle_for_symbol():
  # Antes de ProfessorX: verifica se análise já foi feita
  cp = get_cycle_checkpoint_store()
  if await cp.exists(cycle_id, symbol, "ANALYSIS"):
      analysis_dict = await cp.load(cycle_id, symbol, "ANALYSIS")
      analysis = MarketAnalysis(**analysis_dict)
  else:
      analysis = await self._professor.run(symbol=symbol)
      await cp.save(cycle_id, symbol, "ANALYSIS", analysis.model_dump())

  # Antes de Vision: mesma lógica para "SIGNAL"
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_CHECKPOINT_AGENT = "NICKFURY"
_CHECKPOINT_EVENT = "CYCLE_CHECKPOINT"
_DEFAULT_MAX_AGE_MINUTES = 60


class CycleCheckpointStore:
    """Salva e restaura checkpoints de ciclo via AuditRecord no banco de dados.

    Cada checkpoint é um AuditRecord com:
      agent   = "NICKFURY"
      event   = "CYCLE_CHECKPOINT"
      symbol  = <symbol>
      payload = {"cycle_id": str, "stage": str, "data": dict}

    A chave de lookup é (cycle_id, symbol, stage) — única por ciclo.
    """

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def save(
        self,
        cycle_id: str | int,
        symbol: str,
        stage: str,
        payload: dict[str, Any],
    ) -> None:
        """Persiste um checkpoint no banco de dados.

        Args:
            cycle_id:  Identificador único do ciclo (UUID ou int).
            symbol:    Símbolo de trading (ex: "BTC", "ETH").
            stage:     Etapa do pipeline ("ANALYSIS" ou "SIGNAL").
            payload:   Dados serializáveis da etapa concluída.

        Silencia qualquer falha — o pipeline não deve quebrar por causa do checkpoint.
        """
        try:
            from src.persistence.repository import MekkaRepository  # noqa: WPS433

            await MekkaRepository.log_event(
                agent=_CHECKPOINT_AGENT,
                event=_CHECKPOINT_EVENT,
                message=f"checkpoint stage={stage} cycle={cycle_id}",
                symbol=symbol,
                severity="DEBUG",
                payload={
                    "cycle_id": str(cycle_id),
                    "stage": stage,
                    "data": payload,
                },
            )
            logger.debug(
                f"[CycleCheckpoint:251] saved {symbol} stage={stage} cycle={cycle_id}"
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[CycleCheckpoint:251] save skipped: {exc}")

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def load(
        self,
        cycle_id: str | int,
        symbol: str,
        stage: str,
    ) -> dict[str, Any] | None:
        """Carrega dados de checkpoint do banco de dados.

        Returns:
            dict com os dados da etapa se o checkpoint existir, ou None.
        """
        try:
            from src.persistence.repository import MekkaRepository  # noqa: WPS433

            records = await MekkaRepository.list_audit_events(
                agent=_CHECKPOINT_AGENT,
                event=_CHECKPOINT_EVENT,
                symbol=symbol,
                limit=20,
            )
            _cid = str(cycle_id)
            for rec in records:
                p = rec.get("payload") or {}
                if isinstance(p, str):
                    try:
                        p = json.loads(p)
                    except Exception:  # noqa: BLE001
                        p = {}
                if p.get("cycle_id") == _cid and p.get("stage") == stage:
                    data = p.get("data") or {}
                    logger.debug(
                        f"[CycleCheckpoint:251] loaded {symbol} stage={stage} cycle={cycle_id}"
                    )
                    return data
            return None
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[CycleCheckpoint:251] load skipped: {exc}")
            return None

    async def exists(
        self,
        cycle_id: str | int,
        symbol: str,
        stage: str,
    ) -> bool:
        """Retorna True se o checkpoint existir no banco de dados."""
        result = await self.load(cycle_id, symbol, stage)
        return result is not None

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def clear_expired(
        self,
        max_age_minutes: int = _DEFAULT_MAX_AGE_MINUTES,
    ) -> int:
        """Remove checkpoints mais antigos que max_age_minutes.

        Nota: implementação via SQLAlchemy DELETE direto no AuditRecord.
        Retorna o número de registros removidos (0 em caso de falha).
        """
        try:
            from datetime import datetime, timedelta, timezone  # noqa: WPS433
            from sqlalchemy import delete  # noqa: WPS433
            from src.persistence.database import get_session  # noqa: WPS433
            from src.persistence.models import AuditRecord  # noqa: WPS433

            cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
            async with get_session() as session:
                result = await session.execute(
                    delete(AuditRecord).where(
                        AuditRecord.agent == _CHECKPOINT_AGENT,
                        AuditRecord.event == _CHECKPOINT_EVENT,
                        AuditRecord.timestamp < cutoff,
                    )
                )
                await session.commit()
                deleted = result.rowcount or 0
            logger.debug(
                f"[CycleCheckpoint:251] clear_expired removed {deleted} records "
                f"(max_age={max_age_minutes}min)"
            )
            return deleted
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[CycleCheckpoint:251] clear_expired skipped: {exc}")
            return 0


# ------------------------------------------------------------------
# Singleton factory
# ------------------------------------------------------------------

_store: CycleCheckpointStore | None = None


def get_cycle_checkpoint_store() -> CycleCheckpointStore:
    """Retorna a instância singleton de CycleCheckpointStore."""
    global _store  # noqa: WPS420
    if _store is None:
        _store = CycleCheckpointStore()
    return _store
