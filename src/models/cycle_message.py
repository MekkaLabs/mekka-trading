"""
src/models/cycle_message.py
========================================
Story 184 — TypedCycleMessage: mensagem tipada para roteamento entre estágios.

Inspirado no padrão MetaGPT Message:
  "Roles use the _watch mechanism to monitor important upstream messages.
   Each Message carries cause_by (which Action produced it), sent_from
   (which Role emitted it), send_to (intended recipients), and content
   (the typed payload)."

No MetaGPT, Message é o protocolo universal de comunicação entre Roles:
  msg = Message(content=result, cause_by=WriteCode, send_to="QAEngineer")
  role._publish_message(msg)

No Mekka, o equivalente é um CycleMessage que envolve o output de cada
estágio do ciclo (_cycle_for_symbol) com metadados de roteamento explícitos.
Isso torna o pipeline introspectável — qualquer observador pode ver qual
estágio produziu qual payload, para qual símbolo, em qual ciclo.

Uso
---
    from src.models.cycle_message import CycleMessage, CycleStage

    # NickFury emite após Vision completar
    msg = CycleMessage.from_signal(
        symbol=symbol,
        cycle_id=str(_cycle_id),
        signal=signal,
        sender="NickFury",
    )

    # Downstream (Batman, EventBus, Dashboard) consome
    if msg.stage == CycleStage.SIGNAL_EMITTED:
        signal = msg.as_signal()
"""

from __future__ import annotations

import json
import time
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# CycleStage
# ---------------------------------------------------------------------------

class CycleStage(str, Enum):
    """
    Estágios do ciclo de trading — espelha os CycleEventType do CycleEventLog
    mas focado em roteamento de mensagens entre agentes.
    """
    CYCLE_START       = "CYCLE_START"
    ANALYSIS_DONE     = "ANALYSIS_DONE"
    SIGNAL_EMITTED    = "SIGNAL_EMITTED"
    SIGNAL_LINTED     = "SIGNAL_LINTED"
    RISK_VERDICT      = "RISK_VERDICT"
    EXECUTION_DONE    = "EXECUTION_DONE"
    CYCLE_END         = "CYCLE_END"
    CYCLE_SKIPPED     = "CYCLE_SKIPPED"
    ERROR             = "ERROR"


# ---------------------------------------------------------------------------
# CycleMessage
# ---------------------------------------------------------------------------

class CycleMessage(BaseModel):
    """
    Mensagem tipada emitida por um estágio do ciclo — padrão MetaGPT Message.

    Campos espelham o MetaGPT Message:
      - stage       ↔  cause_by   (qual estágio/Action produziu)
      - sender      ↔  sent_from  (qual agente emitiu)
      - recipients  ↔  send_to    (quem deve consumir)
      - payload_json ↔  content   (payload serializado)
    """

    # Roteamento
    stage: CycleStage = Field(..., description="Estágio do pipeline que emitiu esta mensagem")
    sender: str = Field(default="NickFury", description="Agente que emitiu a mensagem")
    recipients: list[str] = Field(default_factory=list, description="Destinatários (vazio = broadcast)")

    # Contexto
    symbol: str = Field(..., description="Símbolo do ativo (ex: 'BTC')")
    cycle_id: str = Field(default="", description="ID do ciclo")
    timestamp: float = Field(default_factory=time.monotonic)

    # Payload
    payload_type: str = Field(default="", description="Tipo do payload serializado")
    payload_json: str = Field(default="{}", description="Payload serializado como JSON string")

    # Metadados opcionais
    metadata: dict[str, Any] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_signal(
        cls,
        symbol: str,
        signal: Any,
        cycle_id: str = "",
        sender: str = "NickFury",
        stage: CycleStage = CycleStage.SIGNAL_EMITTED,
        recipients: Optional[list[str]] = None,
    ) -> "CycleMessage":
        """Cria CycleMessage a partir de um TradingSignal."""
        try:
            payload = signal.model_dump() if hasattr(signal, "model_dump") else {}
        except Exception:  # noqa: BLE001
            payload = {}
        return cls(
            stage=stage,
            sender=sender,
            recipients=recipients or ["Batman"],
            symbol=symbol.upper(),
            cycle_id=cycle_id,
            payload_type="TradingSignal",
            payload_json=json.dumps(payload, default=str),
        )

    @classmethod
    def from_analysis(
        cls,
        symbol: str,
        analysis: Any,
        cycle_id: str = "",
        sender: str = "NickFury",
    ) -> "CycleMessage":
        """Cria CycleMessage a partir de uma MarketAnalysis."""
        try:
            payload = analysis.model_dump() if hasattr(analysis, "model_dump") else {}
        except Exception:  # noqa: BLE001
            payload = {}
        return cls(
            stage=CycleStage.ANALYSIS_DONE,
            sender=sender,
            recipients=["Vision"],
            symbol=symbol.upper(),
            cycle_id=cycle_id,
            payload_type="MarketAnalysis",
            payload_json=json.dumps(payload, default=str),
        )

    @classmethod
    def cycle_start(cls, symbol: str, cycle_id: str = "", sender: str = "NickFury") -> "CycleMessage":
        return cls(
            stage=CycleStage.CYCLE_START,
            sender=sender,
            symbol=symbol.upper(),
            cycle_id=cycle_id,
            payload_type="",
            payload_json="{}",
        )

    @classmethod
    def cycle_end(
        cls,
        symbol: str,
        cycle_id: str = "",
        sender: str = "NickFury",
        success: bool = True,
        metadata: Optional[dict] = None,
    ) -> "CycleMessage":
        return cls(
            stage=CycleStage.CYCLE_END,
            sender=sender,
            symbol=symbol.upper(),
            cycle_id=cycle_id,
            payload_type="CycleResult",
            payload_json=json.dumps({"success": success}),
            metadata=metadata or {},
        )

    @classmethod
    def cycle_skipped(
        cls,
        symbol: str,
        cycle_id: str = "",
        reason: str = "",
        sender: str = "NickFury",
    ) -> "CycleMessage":
        return cls(
            stage=CycleStage.CYCLE_SKIPPED,
            sender=sender,
            symbol=symbol.upper(),
            cycle_id=cycle_id,
            payload_type="SkipReason",
            payload_json=json.dumps({"reason": reason}),
        )

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_payload(self) -> dict:
        """Desserializa o payload JSON."""
        try:
            return json.loads(self.payload_json)
        except Exception:  # noqa: BLE001
            return {}

    def to_log_line(self) -> str:
        """Linha compacta para logging."""
        return (
            f"[CycleMessage] {self.stage.value} | {self.symbol} | "
            f"cycle={self.cycle_id} | sender={self.sender} | "
            f"type={self.payload_type}"
        )

    def to_dict(self) -> dict:
        return {
            "stage": self.stage.value,
            "sender": self.sender,
            "recipients": self.recipients,
            "symbol": self.symbol,
            "cycle_id": self.cycle_id,
            "payload_type": self.payload_type,
            "payload": self.get_payload(),
            "metadata": self.metadata,
        }
