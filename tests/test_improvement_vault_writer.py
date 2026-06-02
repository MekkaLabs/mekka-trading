"""
tests/test_improvement_vault_writer.py
========================================
Smoke tests do write-back loop: improvement_vault_writer.

Cobertura:
  - is_writer_enabled honra a flag de ambiente
  - append_accepted_daily cria/append arquivo diário com header
  - write_merged_review cria nota em 30 - Resources/Reviews/
  - write_handoff_summary extrai TL;DR e adiciona ao daily
  - boundary check rejeita paths fora dos dirs permitidos
  - sanitização: chaves perigosas não vazam pro vault
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_vault(tmp_path, monkeypatch):
    """Cria vault temporário com estrutura mínima e aponta MEKKA_VAULT_PATH."""
    vault = tmp_path / "vault"
    (vault / "60 - Daily").mkdir(parents=True)
    (vault / "30 - Resources" / "Reviews").mkdir(parents=True)
    monkeypatch.setenv("MEKKA_VAULT_PATH", str(vault))
    monkeypatch.setenv("IMPROVEMENT_VAULT_WRITER_ENABLED", "true")
    return vault


@pytest.fixture
def writer_module():
    """Importa o módulo limpando o throttler entre testes."""
    from src.services import improvement_vault_writer as ivw
    # Reset throttler entre testes pra não dar falsa rejeição.
    ivw._throttle._events.clear()
    return ivw


# ---------------------------------------------------------------------------
# Tests — flag e config
# ---------------------------------------------------------------------------


def test_disabled_by_default(monkeypatch, writer_module):
    """Sem a flag, o writer é no-op."""
    monkeypatch.delenv("IMPROVEMENT_VAULT_WRITER_ENABLED", raising=False)
    assert writer_module.is_writer_enabled() is False
    assert writer_module.append_accepted_daily({"id": "x"}) is None
    assert writer_module.write_merged_review({"id": "x"}) is None


def test_enabled_flag_recognizes_true(monkeypatch, writer_module):
    for val in ("true", "1", "yes", "on"):
        monkeypatch.setenv("IMPROVEMENT_VAULT_WRITER_ENABLED", val)
        assert writer_module.is_writer_enabled() is True


def test_disabled_flag_recognizes_false(monkeypatch, writer_module):
    for val in ("false", "0", "no", "off", ""):
        monkeypatch.setenv("IMPROVEMENT_VAULT_WRITER_ENABLED", val)
        assert writer_module.is_writer_enabled() is False


# ---------------------------------------------------------------------------
# Tests — append_accepted_daily
# ---------------------------------------------------------------------------


def test_append_creates_header(temp_vault, writer_module):
    """Primeira escrita cria header com tags + warning."""
    rec = {
        "rec_id": "abc123", "title": "Test improvement",
        "area": "agents", "impact": "MEDIUM", "priority": "P2",
        "source": "agents_scanner",
    }
    result = writer_module.append_accepted_daily(rec)
    assert result is not None
    text = result.read_text(encoding="utf-8")
    # Header foi criado
    assert "---" in text
    assert "type: daily-improvements" in text
    assert "auto_generated: true" in text
    # Bloco do rec foi inserido
    assert "IMP-abc123" in text
    assert "Test improvement" in text


def test_append_idempotent_same_day(temp_vault, writer_module):
    """Duas escritas no mesmo dia → append no mesmo arquivo, header preservado."""
    rec_a = {"rec_id": "a", "title": "A", "area": "x", "source": "scanner_a"}
    rec_b = {"rec_id": "b", "title": "B", "area": "y", "source": "scanner_b"}
    p1 = writer_module.append_accepted_daily(rec_a)
    p2 = writer_module.append_accepted_daily(rec_b)
    assert p1 == p2  # mesmo arquivo
    text = p1.read_text(encoding="utf-8")
    assert text.count("type: daily-improvements") == 1  # header só uma vez
    assert "IMP-a" in text
    assert "IMP-b" in text


def test_secret_keys_not_leaked(temp_vault, writer_module):
    """Chaves perigosas (api_key, private_key) não vazam pro vault."""
    rec = {
        "rec_id": "sec1", "title": "Sensitive",
        "api_key": "sk-leaked-do-not-write",
        "private_key": "0xabcdef0123456789",
        "secret": "should-not-appear",
        "password": "p@ssw0rd",
        "description": "OK to include",
    }
    p = writer_module.append_accepted_daily(rec)
    assert p is not None
    text = p.read_text(encoding="utf-8")
    assert "sk-leaked-do-not-write" not in text
    assert "0xabcdef" not in text
    assert "p@ssw0rd" not in text
    assert "should-not-appear" not in text
    # Mas description permanece
    assert "OK to include" in text


# ---------------------------------------------------------------------------
# Tests — write_merged_review
# ---------------------------------------------------------------------------


def test_review_creates_note(temp_vault, writer_module):
    rec = {
        "rec_id": "deadbeef", "title": "Fix bridge silent failure",
        "area": "memory", "impact": "HIGH",
        "description": "Improve error handling in record_decision",
        "rationale": "Pre-2026-05-27 hook silenced exceptions",
    }
    result = writer_module.write_merged_review(
        rec,
        before_kpis={"win_rate": 0.40},
        after_kpis={"win_rate": 0.55},
        pr_number=42, commit_sha="abc12345fedcba",
    )
    assert result is not None
    assert result.exists()
    text = result.read_text(encoding="utf-8")
    assert "type: review-improvement" in text
    assert "rec_id: deadbeef" in text
    assert "PR `#42`" in text
    assert "commit `abc12345`" in text
    assert "win_rate" in text


def test_review_idempotent(temp_vault, writer_module):
    """Mesma rec_id não sobrescreve nota existente."""
    rec = {"rec_id": "same", "title": "Same review"}
    p1 = writer_module.write_merged_review(rec)
    # Modifica a nota manualmente
    p1.write_text("operator manual notes", encoding="utf-8")
    p2 = writer_module.write_merged_review(rec)
    assert p1 == p2
    # Não sobrescreveu
    assert p2.read_text(encoding="utf-8") == "operator manual notes"


# ---------------------------------------------------------------------------
# Tests — boundary check
# ---------------------------------------------------------------------------


def test_boundary_check_blocks_escape_attempt(temp_vault, writer_module):
    """Tentativa de escrever fora dos dirs permitidos é bloqueada."""
    # _is_within_allowed deve recusar paths fora de 60 - Daily / 30 - Resources/Reviews
    forbidden = temp_vault / "00 - Inbox" / "evil.md"
    assert writer_module._is_within_allowed(forbidden, temp_vault) is False
    ok_daily = temp_vault / "60 - Daily" / "ok.md"
    assert writer_module._is_within_allowed(ok_daily, temp_vault) is True
    ok_review = temp_vault / "30 - Resources" / "Reviews" / "ok.md"
    assert writer_module._is_within_allowed(ok_review, temp_vault) is True


# ---------------------------------------------------------------------------
# Tests — handoff_summary
# ---------------------------------------------------------------------------


def test_handoff_extracts_tldr(temp_vault, writer_module, tmp_path):
    handoff_text = """# Test Handoff

## ⚡ TL;DR

Esta sessão fez X, Y e Z.
- Item A
- Item B

## Próximos passos

Coisa nova.
"""
    handoff_path = tmp_path / "HANDOFF-test.md"
    handoff_path.write_text(handoff_text, encoding="utf-8")
    result = writer_module.write_handoff_summary(handoff_path)
    assert result is not None
    daily_text = result.read_text(encoding="utf-8")
    assert "HANDOFF-test.md" in daily_text
    assert "Esta sessão fez X, Y e Z." in daily_text
    # Próxima seção não vaza
    assert "Próximos passos" not in daily_text


def test_handoff_missing_tldr_skips(temp_vault, writer_module, tmp_path):
    handoff_text = "# No TL;DR section here\n\nJust body."
    p = tmp_path / "HANDOFF-x.md"
    p.write_text(handoff_text, encoding="utf-8")
    assert writer_module.write_handoff_summary(p) is None


# ---------------------------------------------------------------------------
# Test — stats
# ---------------------------------------------------------------------------


def test_stats_reports_state(temp_vault, writer_module):
    s = writer_module.stats()
    assert s["enabled"] is True
    assert str(temp_vault) in s["vault_path"]
    assert s["vault_available"] is True
    assert "60 - Daily" in s["allowed_subdirs"]
