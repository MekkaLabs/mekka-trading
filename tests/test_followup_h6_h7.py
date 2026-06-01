"""Follow-ups H6 (outbox) + H7 (atribuição por-trade) — 2026-06-01 audit.

H6 — save_pending_trade (PENDING antes da ordem) → finalize_trade (atualiza a
     mesma linha) → reap_stale_pending_trades (marca órfãos como ORPHAN).
H7 — attribute_realized_pnl grava o realizedPnl no trade aberto do símbolo.

Usa um DB SQLite temporário (gerencia o engine global em setup/teardown).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.models.execution import ExecutionResult, ExecutionStatus


@pytest.fixture()
async def temp_db(tmp_path, monkeypatch):
    from src.config.settings import settings
    from src.persistence import db as db_mod

    monkeypatch.setattr(settings, "sqlite_db_path", str(tmp_path / "test.db"))
    await db_mod.dispose()
    await db_mod.init_engine()
    yield
    await db_mod.dispose()


def _exec(status=ExecutionStatus.FILLED, oid="ORD-1", qty=0.5, px=77000.0):
    return ExecutionResult(
        symbol="BTC", status=status, is_paper=False, side="long",
        quantity=qty, avg_price=px, notional_usd=qty * px, order_id=oid,
    )


# ===========================================================================
# H6 — outbox
# ===========================================================================

@pytest.mark.asyncio
async def test_h6_pending_then_finalize_updates_same_row(temp_db):
    from src.persistence.repository import MekkaRepository

    pid = await MekkaRepository.save_pending_trade(
        signal_id=None, symbol="BTC", side="long", quantity=0.0, is_paper=False,
    )
    assert pid is not None

    fid = await MekkaRepository.finalize_trade(pid, execution=_exec())
    assert fid == pid  # mesma linha atualizada, sem duplicar

    # A linha agora é FILLED com o order_id real.
    trades = await MekkaRepository.list_recent_trades(limit=10)
    row = [t for t in trades if t.id == pid][0]
    assert row.status == "FILLED"
    assert row.order_id == "ORD-1"


@pytest.mark.asyncio
async def test_h6_finalize_falls_back_to_insert_when_no_pending(temp_db):
    from src.persistence.repository import MekkaRepository

    # trade_id None → finalize degrada para insert (nunca perde o registro).
    fid = await MekkaRepository.finalize_trade(None, execution=_exec(oid="ORD-2"))
    assert fid is not None
    trades = await MekkaRepository.list_recent_trades(limit=10)
    assert any(t.order_id == "ORD-2" for t in trades)


@pytest.mark.asyncio
async def test_h6_reaper_marks_stale_pending_as_orphan(temp_db):
    from src.persistence.repository import MekkaRepository
    from src.persistence.db import get_session
    from src.persistence.models import TradeRecord

    pid = await MekkaRepository.save_pending_trade(
        signal_id=None, symbol="ETH", side="short", quantity=0.0, is_paper=False,
    )
    # Forçar timestamp antigo (simular crash mid-execução).
    async with get_session() as s:
        from sqlalchemy import select
        rec = (await s.execute(select(TradeRecord).where(TradeRecord.id == pid))).scalar_one()
        rec.timestamp = datetime.now(timezone.utc) - timedelta(hours=1)
        await s.commit()

    orphans = await MekkaRepository.reap_stale_pending_trades(max_age_seconds=600)
    assert any(o["id"] == pid for o in orphans)

    # Uma 2ª passada não re-reporta (já é ORPHAN, não PENDING).
    orphans2 = await MekkaRepository.reap_stale_pending_trades(max_age_seconds=600)
    assert not any(o["id"] == pid for o in orphans2)


@pytest.mark.asyncio
async def test_h6_fresh_pending_not_reaped(temp_db):
    from src.persistence.repository import MekkaRepository

    pid = await MekkaRepository.save_pending_trade(
        signal_id=None, symbol="SOL", side="long", quantity=0.0, is_paper=False,
    )
    orphans = await MekkaRepository.reap_stale_pending_trades(max_age_seconds=600)
    assert not any(o["id"] == pid for o in orphans)  # recém-criado → não órfão


# ===========================================================================
# H7 — atribuição por-trade
# ===========================================================================

@pytest.mark.asyncio
async def test_h7_attributes_realized_pnl_to_open_trade(temp_db):
    from src.persistence.repository import MekkaRepository

    # Abre um trade live FILLED com pnl_usd NULL.
    tid = await MekkaRepository.save_trade(execution=_exec(oid="OPEN-1"))

    attributed = await MekkaRepository.attribute_realized_pnl("BTC", 123.45)
    assert attributed == tid

    trades = await MekkaRepository.list_recent_trades(limit=10)
    row = [t for t in trades if t.id == tid][0]
    assert row.pnl_usd == pytest.approx(123.45)
    assert (row.raw or {}).get("metadata", {}).get("realized_pnl_usd") == pytest.approx(123.45)


@pytest.mark.asyncio
async def test_h7_no_open_trade_returns_none(temp_db):
    from src.persistence.repository import MekkaRepository

    assert await MekkaRepository.attribute_realized_pnl("DOGE", 10.0) is None
