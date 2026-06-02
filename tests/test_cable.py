"""
tests/test_cable.py
====================
Cobertura do agente Cable (Derivatives Intel) e do service
derivatives_intel.

Foco em:
- Opt-in via env (CABLE_AGENT_ENABLED)
- Throttle
- Sanidade do snapshot (não vaza credenciais)
- Restrição read-only — agente não tem métodos de trade
- Isolamento — agentes de trade não importam Cable
- CSV import resiliente a formatos inválidos
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.agents.cable import (
    DEFAULT_SYMBOLS,
    Cable,
    _Throttle,
    get_cable_agent,
    is_agent_enabled,
)
from src.services.derivatives_intel import (
    FundingSnapshot,
    OpenInterestSnapshot,
    PersonalTradesSnapshot,
    _is_personal_auth_available,
    import_trades_csv,
)


# ---------------------------------------------------------------------------
# Opt-in
# ---------------------------------------------------------------------------


class TestOptIn:
    def test_default_disabled(self, monkeypatch) -> None:
        monkeypatch.delenv("CABLE_AGENT_ENABLED", raising=False)
        assert is_agent_enabled() is False
        assert get_cable_agent() is None

    def test_enabled_via_env(self, monkeypatch) -> None:
        monkeypatch.setenv("CABLE_AGENT_ENABLED", "true")
        import src.agents.cable as mod
        mod._instance = None
        agent = get_cable_agent()
        assert agent is not None
        assert isinstance(agent, Cable)

    def test_personal_auth_not_available_by_default(self, monkeypatch) -> None:
        monkeypatch.delenv("CABLE_BINANCE_API_KEY", raising=False)
        monkeypatch.delenv("CABLE_BINANCE_API_SECRET", raising=False)
        assert _is_personal_auth_available() is False


# ---------------------------------------------------------------------------
# Throttle
# ---------------------------------------------------------------------------


class TestThrottle:
    def test_blocks_after_max(self) -> None:
        t = _Throttle(max_events=2, window_s=3600.0)
        assert t.allow() is True
        assert t.allow() is True
        assert t.allow() is False


# ---------------------------------------------------------------------------
# Cable agent
# ---------------------------------------------------------------------------


class TestCableAgent:
    def test_snapshot_shape(self) -> None:
        a = Cable()
        s = a.snapshot()
        assert "subscribed" in s
        assert "stats" in s
        assert "throttle" in s
        assert "symbols_watched" in s
        assert "auth_available_personal_trades" in s
        assert "recent_reports" in s

    def test_no_trade_methods(self) -> None:
        """Cable é read-only — não pode ter create_order ou similar."""
        a = Cable()
        forbidden = ["create_order", "cancel_order", "place_order",
                     "execute_trade", "transfer", "withdraw"]
        for m in forbidden:
            assert not hasattr(a, m), f"Cable tem método proibido: {m}"

    def test_derive_insights_funding_positive(self) -> None:
        snap = {
            "data": {
                "BTCUSDT": {
                    "funding": {"mean": 0.001, "last": 0.001},
                    "open_interest": {"value": 100000},
                }
            }
        }
        insights = Cable._derive_insights(snap)
        assert any("longs pagando" in i.lower() for i in insights)

    def test_derive_insights_funding_negative(self) -> None:
        snap = {
            "data": {
                "ETHUSDT": {
                    "funding": {"mean": -0.001, "last": -0.0008},
                }
            }
        }
        insights = Cable._derive_insights(snap)
        assert any("shorts pagando" in i.lower() for i in insights)

    def test_derive_insights_empty(self) -> None:
        insights = Cable._derive_insights({"data": {}})
        assert len(insights) == 1
        assert "indisponíveis" in insights[0].lower() or "carregando" in insights[0].lower()

    @pytest.mark.asyncio
    async def test_run_returns_snapshot(self) -> None:
        a = Cable()
        result = await a._run()
        assert isinstance(result, dict)
        assert "subscribed" in result


# ---------------------------------------------------------------------------
# CSV import — segurança e resiliência
# ---------------------------------------------------------------------------


class TestCSVImport:
    def test_nonexistent_file_fails_silently(self, tmp_path: Path) -> None:
        result = import_trades_csv(str(tmp_path / "no.csv"))
        assert isinstance(result, PersonalTradesSnapshot)
        assert result.error is not None
        assert "file_not_found" in result.error

    def test_valid_csv_parses(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "trades.csv"
        csv_file.write_text(
            "Date(UTC),Symbol,Side,Quantity,Price,Realized Profit\n"
            "2026-05-26 10:00,BTCUSDT,BUY,0.01,68000,15.5\n"
            "2026-05-26 11:00,BTCUSDT,SELL,0.01,68500,-3.2\n"
            "2026-05-26 12:00,ETHUSDT,BUY,0.5,3500,42.1\n",
            encoding="utf-8",
        )
        result = import_trades_csv(str(csv_file))
        assert result.count == 3
        assert result.realized_pnl == pytest.approx(15.5 - 3.2 + 42.1)

    def test_csv_filter_by_symbol(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "trades.csv"
        csv_file.write_text(
            "Date(UTC),Symbol,Side,Quantity,Price,Realized Profit\n"
            "2026-05-26 10:00,BTCUSDT,BUY,0.01,68000,15.5\n"
            "2026-05-26 11:00,ETHUSDT,BUY,0.5,3500,42.1\n",
            encoding="utf-8",
        )
        result = import_trades_csv(str(csv_file), symbol="BTCUSDT")
        assert result.count == 1
        assert result.realized_pnl == pytest.approx(15.5)

    def test_csv_malformed_row_ignored(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "bad.csv"
        csv_file.write_text(
            "Date(UTC),Symbol,Side,Quantity,Price,Realized Profit\n"
            "row,BTCUSDT,BUY,0.01,68000,NOT_A_NUMBER\n"
            "2026-05-26,BTCUSDT,BUY,0.01,68000,10.0\n",
            encoding="utf-8",
        )
        result = import_trades_csv(str(csv_file))
        assert result.count == 1
        assert result.realized_pnl == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Service models (sanidade)
# ---------------------------------------------------------------------------


class TestModels:
    def test_funding_snapshot_defaults(self) -> None:
        f = FundingSnapshot(symbol="X")
        assert f.symbol == "X"
        assert f.rates == []
        assert f.error is None

    def test_oi_snapshot_defaults(self) -> None:
        o = OpenInterestSnapshot(symbol="Y")
        assert o.symbol == "Y"
        assert o.open_interest is None

    def test_personal_defaults(self) -> None:
        p = PersonalTradesSnapshot(symbol="Z")
        assert p.symbol == "Z"
        assert p.trades == []
        assert p.auth_available is False


# ---------------------------------------------------------------------------
# Isolamento — agentes de trade NÃO importam Cable
# ---------------------------------------------------------------------------


class TestIsolation:
    def test_trading_agents_dont_import_cable(self) -> None:
        """
        Cable é observer/analytics. Agentes Layer 1-3 (decisão/risco/exec)
        nunca devem importá-lo — invariante de não-acoplamento.
        """
        agents_dir = Path("src/agents")
        skip = {"cable.py", "__init__.py", "base.py", "llm_client.py", "prometheus.py"}
        for py in agents_dir.glob("*.py"):
            if py.name in skip:
                continue
            src = py.read_text(encoding="utf-8")
            assert "from src.agents.cable" not in src, (
                f"{py.name} importa cable — quebra isolamento read-only"
            )
            assert "import src.agents.cable" not in src
