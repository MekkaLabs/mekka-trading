"""
tests/test_cycle_budget_guard_global.py
=======================================
Cap de custo LLM: per-símbolo (existente) + GLOBAL (novo, 2026-06-02) que pausa
TODOS os símbolos no agregado — proteção de créditos.
"""

from __future__ import annotations

import pytest

from src.services.cycle_budget_guard import CycleBudgetGuard


@pytest.fixture()
def no_real_tracker(monkeypatch):
    """Força o fallback para a acumulação local (estimativa via record_cost),
    simulando tracker real indisponível — para testar a lógica do cap global
    sem depender do custo real (que é 0 no processo de teste)."""
    import src.services.llm_cost_tracker as lct
    monkeypatch.setattr(lct, "get_llm_cost_tracker", lambda auto_register=False: None)


def test_global_cap_pauses_all_symbols(no_real_tracker):
    g = CycleBudgetGuard(max_cost_usd_per_session=10.0, max_cost_usd_global=0.5)
    g.record_cost("BTC", 0.3)
    g.record_cost("ETH", 0.3)             # global = 0.6 > 0.5
    assert g.should_skip_vision("BTC")[0] is True
    sol_skip, reason = g.should_skip_vision("SOL")  # SOL nunca gastou
    assert sol_skip is True                # cap global pausa até quem não gastou
    assert "global_budget_exceeded" in reason


def test_per_symbol_cap_isolates(no_real_tracker):
    g = CycleBudgetGuard(max_cost_usd_per_session=0.2, max_cost_usd_global=0.0)
    g.record_cost("BTC", 0.3)             # BTC > 0.2
    assert g.should_skip_vision("BTC")[0] is True
    assert g.should_skip_vision("ETH")[0] is False   # ETH limpo


def test_global_cap_disabled_when_zero(no_real_tracker):
    g = CycleBudgetGuard(max_cost_usd_per_session=10.0, max_cost_usd_global=0.0)
    g.record_cost("BTC", 5.0)
    g.record_cost("ETH", 5.0)             # global = 10 mas cap global = 0 (off)
    assert g.should_skip_vision("SOL")[0] is False


def test_global_uses_real_tracker_cost(monkeypatch):
    """Bug fix (2026-06-02): o cap deve usar o custo REAL do llm_cost_tracker,
    não a estimativa hardcoded de $0.002/call (subestimava ~11x o Claude)."""
    import src.services.llm_cost_tracker as lct

    class _FakeTracker:
        def summary(self):
            return {"session": {"total_cost_usd": 0.80}}

    monkeypatch.setattr(lct, "get_llm_cost_tracker", lambda auto_register=False: _FakeTracker())

    g = CycleBudgetGuard(max_cost_usd_per_session=99.0, max_cost_usd_global=0.5)
    g.record_cost("BTC", 0.002)           # estimativa local minúscula
    # custo REAL (0.80) > cap (0.5) → pausa, apesar da estimativa local ser 0.002
    assert g.global_spent_usd() == 0.80
    skip, reason = g.should_skip_vision("BTC")
    assert skip is True
    assert "global_budget_exceeded" in reason
