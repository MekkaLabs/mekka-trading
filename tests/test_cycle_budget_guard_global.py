"""
tests/test_cycle_budget_guard_global.py
=======================================
Cap de custo LLM: per-símbolo (existente) + GLOBAL (novo, 2026-06-02) que pausa
TODOS os símbolos no agregado — proteção de créditos.
"""

from __future__ import annotations

from src.services.cycle_budget_guard import CycleBudgetGuard


def test_global_cap_pauses_all_symbols():
    g = CycleBudgetGuard(max_cost_usd_per_session=10.0, max_cost_usd_global=0.5)
    g.record_cost("BTC", 0.3)
    g.record_cost("ETH", 0.3)             # global = 0.6 > 0.5
    assert g.should_skip_vision("BTC")[0] is True
    sol_skip, reason = g.should_skip_vision("SOL")  # SOL nunca gastou
    assert sol_skip is True                # cap global pausa até quem não gastou
    assert "global_budget_exceeded" in reason


def test_per_symbol_cap_isolates():
    g = CycleBudgetGuard(max_cost_usd_per_session=0.2, max_cost_usd_global=0.0)
    g.record_cost("BTC", 0.3)             # BTC > 0.2
    assert g.should_skip_vision("BTC")[0] is True
    assert g.should_skip_vision("ETH")[0] is False   # ETH limpo


def test_global_cap_disabled_when_zero():
    g = CycleBudgetGuard(max_cost_usd_per_session=10.0, max_cost_usd_global=0.0)
    g.record_cost("BTC", 5.0)
    g.record_cost("ETH", 5.0)             # global = 10 mas cap global = 0 (off)
    assert g.should_skip_vision("SOL")[0] is False
