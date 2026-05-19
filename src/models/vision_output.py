"""Story 250 — Vision Structured Output.

TradingSignalOutput: modelo Pydantic que espelha o schema JSON que a Vision
emite. Usado como response_format no OpenAI Structured Output
(client.beta.chat.completions.parse), eliminando json.loads e o risco de
respostas malformadas.

Tipos primitivos (str/float/int) em vez de Enum garantem compatibilidade
máxima com o schema simplificado exigido pelo OpenAI Structured Output.
"""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, Field


class TradingSignalOutput(BaseModel):
    """Saída estruturada da Vision — validada diretamente pelo OpenAI.

    Mapeamento exato dos campos que _build_signal() lê do payload JSON.
    Campos com default garantem que HOLD seja retornado mesmo se o modelo
    omitir algum campo opcional.
    """

    action: str = Field(
        default="HOLD",
        description="Trade action: LONG, SHORT, or HOLD",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Decision confidence from 0.0 (no conviction) to 1.0 (maximum conviction)",
    )
    entry_price: float = Field(
        default=0.0,
        ge=0.0,
        description="Suggested entry price in USD",
    )
    stop_loss: float = Field(
        default=0.0,
        ge=0.0,
        description="Stop-loss price in USD",
    )
    take_profit: float = Field(
        default=0.0,
        ge=0.0,
        description="Take-profit price in USD",
    )
    size_pct: float = Field(
        default=0.02,
        ge=0.0,
        le=1.0,
        description="Position size as fraction of equity (e.g. 0.02 = 2%)",
    )
    leverage: int = Field(
        default=1,
        ge=1,
        le=50,
        description="Leverage multiplier (1–50)",
    )
    reasoning: str = Field(
        default="",
        description="LLM explanation of the trade decision",
    )
    agent_contributions: Dict[str, Any] = Field(
        default_factory=dict,
        description="Which agents influenced the decision and how",
    )
