"""
tests/test_operation_mode.py
============================
Modo de Operação (manual/automatic) — switch raiz de aprovação.

Cobre:
  - default seguro (manual)
  - decisões derivadas (requires_trade_approval / improvements_auto_apply)
  - persistência/override em runtime via set_operation_mode
  - wiring dos consumidores (mentor_applier, implementer worker)
  - invariante de segurança: env opt-in legado ainda funciona em manual
"""

from __future__ import annotations

import importlib
import os

import pytest


@pytest.fixture()
def om(monkeypatch, tmp_path):
    """Carrega operation_mode com persistência isolada em tmp_path e
    estado em memória resetado. Garante default 'manual' das settings."""
    import src.config.operation_mode as om_mod

    importlib.reload(om_mod)
    # isola o arquivo de override do runtime
    monkeypatch.setattr(om_mod, "_MODE_FILE", tmp_path / "operation_mode.json")
    monkeypatch.setattr(om_mod, "_DATA_DIR", tmp_path)
    om_mod._reset_for_tests()
    yield om_mod
    om_mod._reset_for_tests()


# ---------------------------------------------------------------------------
# Default & decisões derivadas
# ---------------------------------------------------------------------------

def test_default_is_manual_safe(om):
    assert om.get_operation_mode() == "manual"
    assert om.is_manual() is True
    assert om.is_automatic() is False


def test_manual_requires_approval_and_no_autoapply(om):
    assert om.requires_trade_approval() is True
    assert om.improvements_auto_apply() is False


def test_automatic_flips_decisions(om):
    om.set_operation_mode("automatic")
    assert om.is_automatic() is True
    assert om.requires_trade_approval() is False
    # Melhorias SEMPRE exigem aprovação — o modo não as auto-aplica.
    assert om.improvements_auto_apply() is False


def test_round_trip_back_to_manual(om):
    om.set_operation_mode("automatic")
    om.set_operation_mode("manual")
    assert om.requires_trade_approval() is True
    assert om.improvements_auto_apply() is False


# ---------------------------------------------------------------------------
# Validação & persistência
# ---------------------------------------------------------------------------

def test_unknown_mode_raises(om):
    with pytest.raises(ValueError):
        om.set_operation_mode("turbo")


def test_auto_alias_not_valid_via_set(om):
    # set_operation_mode é estrito: 'auto' não é um modo válido (só via /auto no Telegram).
    with pytest.raises(ValueError):
        om.set_operation_mode("auto")


def test_persistence_survives_reload(om):
    om.set_operation_mode("automatic")
    assert om._MODE_FILE.exists()
    om._reset_for_tests()  # esquece o estado em memória
    assert om.get_operation_mode() == "automatic"  # relê do disco


def test_corrupt_file_falls_back_to_default(om):
    om._MODE_FILE.write_text("{not json", encoding="utf-8")
    om._reset_for_tests()
    assert om.get_operation_mode() == "manual"


def test_snapshot_atomic(om):
    om.set_operation_mode("automatic")
    snap = om.snapshot()
    assert snap["mode"] == "automatic"
    assert snap["requires_trade_approval"] is False
    # Melhorias sempre exigem aprovação — snapshot reflete False sempre.
    assert snap["improvements_auto_apply"] is False
    assert "snapshot_at" in snap


# ---------------------------------------------------------------------------
# Wiring dos consumidores — MELHORIAS SÃO DESACOPLADAS DO MODO (2026-06-02).
# O modo manual/automatic governa só TRADES. Melhorias só auto-aplicam com
# opt-in EXPLÍCITO via env (default OFF), independente do modo.
# ---------------------------------------------------------------------------

def test_mentor_applier_ignores_mode(om, monkeypatch):
    monkeypatch.delenv("MENTOR_AUTO_APPLY_ENABLED", raising=False)
    from src.services import mentor_applier
    assert mentor_applier.is_enabled() is False
    om.set_operation_mode("automatic")
    # automatic NÃO liga o mentor auto-apply — melhorias exigem aprovação.
    assert mentor_applier.is_enabled() is False


def test_mentor_applier_env_optin_works_regardless_of_mode(om, monkeypatch):
    monkeypatch.setenv("MENTOR_AUTO_APPLY_ENABLED", "true")
    from src.services import mentor_applier
    assert mentor_applier.is_enabled() is True       # manual + env explícito
    om.set_operation_mode("automatic")
    assert mentor_applier.is_enabled() is True


def test_worker_ignores_mode(om, monkeypatch):
    monkeypatch.delenv("IMPLEMENTER_WORKER_ENABLED", raising=False)
    monkeypatch.delenv("IMPLEMENTER_WORKER_AUTO_APPLY", raising=False)
    from src.services.implementer import worker
    assert worker.worker_is_enabled() is False
    assert worker.worker_should_apply() is False
    om.set_operation_mode("automatic")
    # automatic NÃO liga o worker — melhorias exigem aprovação.
    assert worker.worker_is_enabled() is False
    assert worker.worker_should_apply() is False


def test_worker_env_optin_works_regardless_of_mode(om, monkeypatch):
    monkeypatch.setenv("IMPLEMENTER_WORKER_ENABLED", "true")
    from src.services.implementer import worker
    assert worker.worker_is_enabled() is True        # opt-in explícito
    om.set_operation_mode("automatic")
    assert worker.worker_is_enabled() is True


# ---------------------------------------------------------------------------
# Comandos Telegram (/opmode, /manual, /auto)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_telegram_opmode_shows_and_switches(om):
    from src.services.telegram_inbound import TelegramInboundPoller

    poller = TelegramInboundPoller()

    # mostra modo atual (manual)
    reply = await poller._cmd_opmode([])
    assert "MANUAL" in reply

    # /auto → muda para automatic
    reply = await poller._cmd_opmode_auto()
    assert "AUTOMÁTICO" in reply
    assert om.get_operation_mode() == "automatic"

    # /manual → volta para manual
    reply = await poller._cmd_opmode_manual()
    assert "MANUAL" in reply
    assert om.get_operation_mode() == "manual"


@pytest.mark.asyncio
async def test_telegram_opmode_rejects_unknown(om):
    from src.services.telegram_inbound import TelegramInboundPoller

    poller = TelegramInboundPoller()
    reply = await poller._cmd_opmode(["turbo"])
    assert "desconhecido" in reply.lower()
    # estado não muda
    assert om.get_operation_mode() == "manual"


@pytest.mark.asyncio
async def test_telegram_opmode_auto_alias(om):
    from src.services.telegram_inbound import TelegramInboundPoller

    poller = TelegramInboundPoller()
    # 'auto' como alias de 'automatic' via /opmode auto
    reply = await poller._cmd_opmode(["auto"])
    assert "AUTOMÁTICO" in reply
    assert om.get_operation_mode() == "automatic"
