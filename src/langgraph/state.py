"""
src/langgraph/state.py
======================
Story 126 — MekkaCycleState: estado serializável que flui entre nós do grafo.

Apenas tipos JSON-serializáveis aqui. Instâncias de agentes (Vision, Batman etc.)
vivem no NickFury e são capturadas por closure nos nós — NUNCA no estado.
"""

from __future__ import annotations

import operator
from typing import Annotated, Optional

from typing_extensions import TypedDict


class MekkaCycleState(TypedDict):
    """Estado serializável do ciclo NickFury no LangGraph.

    Campos:
        cycle_id:            UUID único por invocação do grafo.
        equity_usd:          Equity efetivo no início do ciclo (CLI override ou snapshot).
        symbols_remaining:   Fila de símbolos ainda por processar (decresce a cada nó).
        symbols_completed:   Símbolos já processados neste ciclo.
        reports:             Lista de CycleReport.model_dump() acumulados (reducer: add).
        skip_reason:         Se preenchido, preflight abortou o ciclo (kill_switch, drawdown…).
        open_positions:      Contador de posições abertas — atualizado por símbolo.
        trades_today:        Contador de trades hoje — atualizado por símbolo.
        drawdown_pct:        Drawdown diário lido no preflight.
        running_notional_usd: Notional acumulado das posições abertas neste ciclo.
        error:               Mensagem de erro fatal (opcional).
    """

    cycle_id: str
    equity_usd: float
    symbols_remaining: list[str]
    symbols_completed: list[str]
    # Annotated com operator.add — o LangGraph usa esse reducer para ACUMULAR
    # reports de cada nó em vez de sobrescrever. Cada nó devolve uma lista de
    # 1 item e o reducer faz append na lista global.
    reports: Annotated[list[dict], operator.add]
    skip_reason: Optional[str]
    open_positions: int
    trades_today: int
    drawdown_pct: float
    running_notional_usd: float
    error: Optional[str]
