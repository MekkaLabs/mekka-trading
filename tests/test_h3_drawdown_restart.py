"""Regressão H3 (2026-06-01 audit) — drawdown sobrevive a um restart.

Bug: após um restart no meio do dia, o primeiro DailyPnLWriter.record_cycle
(com `_state is None`) re-semeava starting+peak com a equity JÁ rebaixada →
drawdown ≈ 0 → o gate de drawdown diário do Batman deixava de bloquear num dia
de perdas. Além disso o restore gravava em `_peak_equity` (atributo morto) e o
upsert nunca persistia `peak_equity_usd`.

Fix: record_cycle hidrata a baseline (starting+peak) do DB antes de semear, e
persiste peak_equity_usd no upsert. NickFury chama hydrate_from_db no boot.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.daily_pnl_writer import DailyPnLSnapshot, DailyPnLWriter


@pytest.fixture
def fake_repo():
    repo = MagicMock()
    repo.upsert_daily_pnl = AsyncMock(return_value=1)
    repo.log_event = AsyncMock(return_value=1)
    repo.get_today_daily_pnl_baseline = AsyncMock(return_value=None)
    with patch("src.services.daily_pnl_writer.MekkaRepository", repo):
        yield repo


@pytest.mark.asyncio
async def test_drawdown_survives_restart(fake_repo):
    """Após restart, a baseline persistida (start=10k, peak=10.5k) é restaurada,
    e o drawdown reflete a perda real — não reseta para 0."""
    # Simula que o DB já tem a baseline do dia (peak 10.5k antes do restart).
    fake_repo.get_today_daily_pnl_baseline = AsyncMock(return_value=(10_000.0, 10_500.0))

    # Writer NOVO (=_state None) simula o processo recém-reiniciado.
    writer = DailyPnLWriter()
    snap: DailyPnLSnapshot = await writer.record_cycle(
        equity_usd=9_500.0,   # equity já caiu para 9.5k
        trades_count_today=3,
    )

    # Drawdown real = (10500 - 9500) / 10500 ≈ 9.52% — NÃO 0.
    assert snap.drawdown_pct == pytest.approx((10_500 - 9_500) / 10_500, abs=1e-4)
    assert snap.drawdown_pct > 0.09
    # Baseline hidratada (não re-semeada com 9.5k).
    assert snap.starting_equity == pytest.approx(10_000.0)
    assert snap.peak_equity == pytest.approx(10_500.0)


@pytest.mark.asyncio
async def test_record_cycle_persists_peak_equity(fake_repo):
    """O upsert recebe peak_equity_usd (antes nunca era passado)."""
    writer = DailyPnLWriter()
    await writer.record_cycle(equity_usd=10_000.0, trades_count_today=0)
    _, kwargs = fake_repo.upsert_daily_pnl.await_args
    assert "peak_equity_usd" in kwargs
    assert kwargs["peak_equity_usd"] == pytest.approx(10_000.0)


@pytest.mark.asyncio
async def test_hydrate_never_lowers_peak(fake_repo):
    """hydrate_from_db nunca rebaixa um peak já maior em memória."""
    writer = DailyPnLWriter()
    # Constrói peak in-memory de 11k.
    await writer.record_cycle(equity_usd=11_000.0, trades_count_today=0)
    assert writer.current_state.peak_equity == pytest.approx(11_000.0)
    # DB tem peak menor (10.5k) — hydrate não pode rebaixar.
    fake_repo.get_today_daily_pnl_baseline = AsyncMock(return_value=(10_000.0, 10_500.0))
    await writer.hydrate_from_db()
    assert writer.current_state.peak_equity == pytest.approx(11_000.0)


@pytest.mark.asyncio
async def test_fresh_day_no_baseline_seeds_normally(fake_repo):
    """Dia genuinamente novo (sem linha no DB) semeia baseline = equity atual."""
    fake_repo.get_today_daily_pnl_baseline = AsyncMock(return_value=None)
    writer = DailyPnLWriter()
    snap = await writer.record_cycle(equity_usd=8_000.0, trades_count_today=0)
    assert snap.starting_equity == pytest.approx(8_000.0)
    assert snap.drawdown_pct == pytest.approx(0.0)
