"""
src/services/backtest_signal_loader.py
========================================
BacktestSignalLoader — Story 219 (Milestone 35: Backtesting Engine).

Carrega sinais históricos do SQLite e os converte em ``BacktestTrade``,
unificando dados da tabela ``signals`` com resultados reais de ``trades``
quando disponíveis.

Design
------
- Acessa o SQLite via MekkaRepository (async) — sem conexão direta.
- Retorna lista vazia se o DB não existe ou não tem dados (não lança exceção).
- Suporta filtro por símbolo, intervalo de datas e flag ``actionable_only``.
- Join lazy: tenta casar cada sinal com o trade correspondente via
  ``trade.signal_id`` ou heurística de timestamp + símbolo.
- Nunca lança exceção para o caller.

Uso
---
    loader = BacktestSignalLoader()
    trades = await loader.load(symbol="BTC", days=30)
    trades = await loader.load(symbol="*", start_date=dt(2026,1,1), end_date=dt(2026,5,18))
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from loguru import logger

from src.models.backtest import BacktestOutcome, BacktestTrade


class BacktestSignalLoader:
    """
    Carrega sinais históricos do SQLite e mapeia para ``BacktestTrade``.

    Args:
        actionable_only: Se True (padrão), exclui sinais HOLD.

    Example::

        loader = BacktestSignalLoader()
        trades = await loader.load(symbol="BTC", days=30)
        # → list[BacktestTrade] com real_pnl_usd preenchido quando disponível
    """

    def __init__(self, actionable_only: bool = True) -> None:
        self._actionable_only = actionable_only
        self._log = logger.bind(service="BacktestSignalLoader")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def load(
        self,
        symbol: str = "*",
        days: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        actionable_only: Optional[bool] = None,
    ) -> List[BacktestTrade]:
        """
        Carrega BacktestTrades do DB.

        Args:
            symbol: Símbolo específico (ex: ``"BTC"``) ou ``"*"`` para todos.
            days: Quantos dias atrás a partir de hoje (alternativa a start/end).
            start_date: Data inicial (UTC). Tem precedência sobre ``days``.
            end_date: Data final (UTC). Padrão: now().
            actionable_only: Override para o flag do construtor.

        Returns:
            Lista de BacktestTrade ordenada por timestamp crescente.
            Lista vazia se sem dados ou erro.
        """
        try:
            return await self._load_internal(
                symbol=symbol,
                days=days,
                start_date=start_date,
                end_date=end_date,
                actionable_only=actionable_only if actionable_only is not None else self._actionable_only,
            )
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"BacktestSignalLoader.load() error (suppressed): {exc}")
            return []

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _load_internal(
        self,
        symbol: str,
        days: Optional[int],
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        actionable_only: bool,
    ) -> List[BacktestTrade]:
        from src.persistence.repository import MekkaRepository  # lazy — evita circular

        # Resolver janela de datas
        now = datetime.now(timezone.utc)
        if end_date is None:
            end_date = now
        if start_date is None:
            if days is not None:
                start_date = now - timedelta(days=days)
            else:
                start_date = now - timedelta(days=90)  # padrão: 90 dias

        # Garantir timezone-aware
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)

        # Carregar sinais do DB
        raw_signals = await self._fetch_signals(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )

        if not raw_signals:
            self._log.info(
                f"BacktestSignalLoader: nenhum sinal encontrado "
                f"({symbol}, {start_date.date()} → {end_date.date()})"
            )
            return []

        # Carregar trades reais para o mesmo período
        real_trades_by_signal_id = await self._fetch_trades_by_signal_id(
            start_date=start_date,
            end_date=end_date,
        )

        # Converter para BacktestTrade
        result: List[BacktestTrade] = []
        for sig in raw_signals:
            action = (sig.get("action") or "HOLD").upper()
            if actionable_only and action == "HOLD":
                continue

            bt = BacktestTrade(
                timestamp=self._ensure_tz(sig.get("timestamp") or now),
                symbol=sig.get("symbol") or symbol,
                action=action if action in ("LONG", "SHORT", "HOLD") else "HOLD",  # type: ignore[arg-type]
                entry_price=float(sig.get("entry_price") or 0.0),
                stop_loss=float(sig.get("stop_loss") or 0.0),
                take_profit=float(sig.get("take_profit") or 0.0),
                size_pct=float(sig.get("size_pct") or 0.02),
                leverage=int(sig.get("leverage") or 1),
                confidence=float(sig.get("confidence") or 0.0),
                risk_reward=float(sig.get("risk_reward") or 0.0),
                reasoning=str(sig.get("reasoning") or ""),
                signal_id=sig.get("id"),
                outcome=BacktestOutcome.UNKNOWN,
            )

            # Tentar casar com trade real
            sig_id = sig.get("id")
            if sig_id and sig_id in real_trades_by_signal_id:
                trade = real_trades_by_signal_id[sig_id]
                pnl = float(trade.get("pnl_usd") or 0.0)
                bt = bt.model_copy(update={
                    "real_pnl_usd": pnl,
                    "pnl_usd": pnl,
                    "trade_id": trade.get("id"),
                    "is_real": True,
                    # Inferir outcome do PnL real
                    "outcome": BacktestOutcome.WIN if pnl > 0 else (
                        BacktestOutcome.LOSS if pnl < 0 else BacktestOutcome.UNKNOWN
                    ),
                })

            result.append(bt)

        result.sort(key=lambda t: t.timestamp)
        self._log.info(
            f"BacktestSignalLoader: {len(result)} sinais carregados "
            f"({symbol}, {start_date.date()} → {end_date.date()}), "
            f"{sum(1 for t in result if t.is_real)} com trade real"
        )
        return result

    async def _fetch_signals(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
    ) -> List[Dict]:
        """Lê da tabela signals via export_signals ou list_recent_signals."""
        try:
            from src.persistence.repository import MekkaRepository
            # Usar export_signals que retorna dicts planos
            all_signals = await MekkaRepository.export_signals(limit=10_000)
            filtered = []
            for s in all_signals:
                ts = self._ensure_tz(s.get("timestamp"))
                if ts is None:
                    continue
                if ts < start_date or ts > end_date:
                    continue
                if symbol != "*" and s.get("symbol", "").upper() != symbol.upper():
                    continue
                filtered.append(s)
            return filtered
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"_fetch_signals error (suppressed): {exc}")
            return []

    async def _fetch_trades_by_signal_id(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[int, Dict]:
        """Lê trades reais e indexa por signal_id."""
        try:
            from src.persistence.repository import MekkaRepository
            trades = await MekkaRepository.list_paper_filled_trades(limit=5_000)
            result: Dict[int, Dict] = {}
            for t in trades:
                ts = self._ensure_tz(getattr(t, "timestamp", None))
                if ts and (ts < start_date or ts > end_date):
                    continue
                sid = getattr(t, "signal_id", None)
                if sid:
                    result[sid] = {
                        "id": getattr(t, "id", None),
                        "pnl_usd": getattr(t, "pnl_usd", None),
                        "status": getattr(t, "status", None),
                        "signal_id": sid,
                    }
            return result
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"_fetch_trades_by_signal_id error (suppressed): {exc}")
            return {}

    @staticmethod
    def _ensure_tz(dt_val) -> Optional[datetime]:
        if dt_val is None:
            return None
        if isinstance(dt_val, str):
            try:
                from dateutil.parser import parse as _parse
                dt_val = _parse(dt_val)
            except Exception:
                return None
        if isinstance(dt_val, datetime):
            if dt_val.tzinfo is None:
                return dt_val.replace(tzinfo=timezone.utc)
            return dt_val
        return None
