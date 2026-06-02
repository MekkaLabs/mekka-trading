"""
tests/test_beast_learning_consumer.py
=====================================
Beast consome o diário de aprendizado: padrões de prejuízo recorrente
(outcome-loss muito reforçados) viram propostas de investigação.
Cobre top_reinforced() e Beast._analyze_agent_learnings().
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture()
def journal(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_LEARNING_VAULT_DISABLED", "true")
    import src.services.agent_learning_journal as alj
    monkeypatch.setattr(alj, "_DB_PATH", tmp_path / "j.db")
    return alj


def test_top_reinforced_filters_by_count_and_category(journal):
    for _ in range(5):
        journal.record("Cyclops", "BTC long fecha no stop", category="outcome-loss")
    for _ in range(2):
        journal.record("Cyclops", "ETH short fecha no stop", category="outcome-loss")
    journal.record("Cyclops", "SOL long atingiu TP", category="outcome-win")

    top = journal.top_reinforced(min_count=3, category="outcome-loss")
    assert len(top) == 1                       # só o BTC (5) passa o min_count=3
    assert top[0]["reinforced_count"] == 5
    # win não entra no filtro de loss
    assert all(r["category"] == "outcome-loss" for r in top)


@pytest.mark.asyncio
async def test_beast_proposes_from_recurring_loss(journal):
    for _ in range(6):
        journal.record("Cyclops", "BTC long fecha no stop", category="outcome-loss")
    from src.agents.beast import Beast
    props = await Beast()._analyze_agent_learnings()
    assert len(props) == 1
    assert props[0].impact == "HIGH"           # >=5 reforços → HIGH
    assert props[0].area == "risk_gates"


@pytest.mark.asyncio
async def test_beast_no_proposal_below_threshold(journal):
    journal.record("Cyclops", "BTC long fecha no stop", category="outcome-loss")  # 1×
    from src.agents.beast import Beast
    props = await Beast()._analyze_agent_learnings()
    assert props == []                         # 1 reforço < min_count=3
