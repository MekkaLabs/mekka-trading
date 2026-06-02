"""
tests/test_agent_learning_journal.py
====================================
Diário de Aprendizado por Agente — SQLite (fonte da verdade) + espelho Obsidian.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def journal(monkeypatch, tmp_path):
    """Carrega o serviço com DB e vault isolados em tmp_path."""
    import src.services.agent_learning_journal as alj

    importlib.reload(alj)
    db = tmp_path / "test.db"
    vault = tmp_path / "vault"
    (vault / "20 - Areas" / "Agentes IA").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(alj, "_DB_PATH", db)
    monkeypatch.setenv("MEKKA_VAULT_PATH", str(vault))
    monkeypatch.delenv("AGENT_LEARNING_VAULT_DISABLED", raising=False)
    alj._vault_writes.clear()
    yield alj


def test_record_new_lesson(journal):
    r = journal.record("Superman", "RSI<20 reverte em alta vol", category="indicador", confidence=0.7)
    assert r["status"] == "new"
    out = journal.recall("Superman")
    assert len(out) == 1
    assert out[0]["lesson"].startswith("RSI<20")
    assert out[0]["confidence"] == 0.7
    assert out[0]["reinforced_count"] == 1


def test_dedup_reinforces_not_duplicates(journal):
    journal.record("Batman", "exposição > 50% aumenta drawdown", confidence=0.6)
    r2 = journal.record("Batman", "Exposição > 50%   aumenta  drawdown", confidence=0.9)  # mesma lição (norm)
    assert r2["status"] == "reinforced"
    out = journal.recall("Batman")
    assert len(out) == 1                       # não duplicou
    assert out[0]["reinforced_count"] == 2     # reforçou
    assert out[0]["confidence"] == 0.9         # confiança = máx


def test_recall_orders_by_reinforcement_and_confidence(journal):
    journal.record("Vision", "lição fraca", confidence=0.2)
    journal.record("Vision", "lição forte", confidence=0.9)
    journal.record("Vision", "lição forte", confidence=0.9)  # reforça → sobe no ranking
    out = journal.recall("Vision", limit=2)
    assert out[0]["lesson"] == "lição forte"
    assert out[1]["lesson"] == "lição fraca"


def test_recall_query_filter(journal):
    journal.record("Thor", "ATR alto = posição menor", confidence=0.8)
    journal.record("Thor", "funding extremo evita entrada", confidence=0.8)
    out = journal.recall("Thor", query="ATR")
    assert len(out) == 1
    assert "ATR" in out[0]["lesson"]


def test_per_agent_isolation(journal):
    journal.record("Superman", "lição do superman")
    journal.record("Batman", "lição do batman")
    assert len(journal.recall("Superman")) == 1
    assert len(journal.recall("Batman")) == 1
    assert journal.recall("Superman")[0]["lesson"] == "lição do superman"


def test_vault_mirror_creates_note(journal):
    journal.record("Aquaman", "spread largo = slippage alto", category="liquidez", confidence=0.7)
    note = journal.get_vault_path() / "20 - Areas/Agentes IA/Aprendizados/Aquaman.md"
    assert note.exists()
    content = note.read_text(encoding="utf-8")
    assert "Aprendizados — Aquaman" in content
    assert "spread largo" in content
    assert "[[Aquaman]]" in content       # link para a identidade curada


def test_vault_mirror_appends_only(journal):
    journal.record("Flash", "lição 1")
    journal.record("Flash", "lição 2")
    note = journal.get_vault_path() / "20 - Areas/Agentes IA/Aprendizados/Flash.md"
    content = note.read_text(encoding="utf-8")
    assert "lição 1" in content and "lição 2" in content


def test_vault_disabled_skips_mirror(journal, monkeypatch):
    monkeypatch.setenv("AGENT_LEARNING_VAULT_DISABLED", "true")
    journal.record("Cyclops", "sem espelho")
    note = journal.get_vault_path() / "20 - Areas/Agentes IA/Aprendizados/Cyclops.md"
    assert not note.exists()                 # vault desligado
    assert len(journal.recall("Cyclops")) == 1  # mas SQLite (verdade) tem


def test_build_context_snippet(journal):
    journal.record("Spider-Man", "volume spike = anomalia", confidence=0.8)
    journal.record("Spider-Man", "volume spike = anomalia", confidence=0.8)  # reforça
    out = journal.recall("Spider-Man")
    snippet = journal.build_context_snippet("Spider-Man", out)
    assert "Spider-Man" in snippet
    assert "volume spike" in snippet
    assert "×2" in snippet                   # mostra reforço

def test_empty_lesson_skipped(journal):
    r = journal.record("Mentor", "   ")
    assert r["status"] == "skipped"
    assert journal.recall("Mentor") == []


# ---------------------------------------------------------------------------
# Comando Telegram /aprendizados
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_telegram_aprendizados_command(journal):
    journal.record("IronMan", "BTC long slippa acima do limite", category="execução", confidence=0.6)
    journal.record("Mentor", "win-rate baixo → apertar confiança", confidence=0.7)
    from src.services.telegram_inbound import TelegramInboundPoller
    p = TelegramInboundPoller()

    resumo = await p._cmd_learnings([])
    assert "IronMan" in resumo and "Mentor" in resumo

    detalhe = await p._cmd_learnings(["IronMan"])
    assert "slippa" in detalhe

    vazio = await p._cmd_learnings(["Batman"])
    assert "ainda não registrou" in vazio
