"""
src/services/telegram_alerter.py
================================
Telegram push-only alerter (Story 035).

Stateless service that pushes critical Mekka audit events to a Telegram
chat via the Bot API. No long-polling, no inbound commands in v1 —
purely outbound notifications. Inbound `/status /pnl /pause /resume`
is reserved for Story 035b (separate process running aiogram or
python-telegram-bot).

Hard rules
----------
- **Never throws.** A network failure, rate-limit, or malformed token
  is logged and absorbed; the cycle that triggered the alert keeps
  running.
- **Toggle by env.** When `settings.telegram_enabled` is False (no
  bot token + chat id) the alerter short-circuits at `alert()`.
- **Filter by severity AND/OR event whitelist.**
- **Async-friendly**, uses `aiohttp` lazily.
- **No persistent state.** Each `alert()` call is independent — if
  Telegram is down we just drop. Audit log already has the event;
  Telegram is best-effort.

New methods (beyond generic `alert`):
- `ping()` — sends a startup/test ping with system info.
- `trade_opened()` — rich notification when a trade is FILLED/PAPER.

Severity ordering (most → least permissive):
    DEBUG < INFO < WARNING < ERROR < CRITICAL
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from loguru import logger

from src.config.settings import settings

if TYPE_CHECKING:
    from src.models.execution import ExecutionResult
    from src.models.signal import TradingSignal


_SEVERITY_ORDER = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _tg_url(token: str) -> str:
    return _TELEGRAM_API.format(token=token)


def _severity_at_least(severity: str, threshold: str) -> bool:
    """True when `severity` ≥ `threshold` per `_SEVERITY_ORDER`."""
    return _SEVERITY_ORDER.get(severity.upper(), 0) >= _SEVERITY_ORDER.get(
        threshold.upper(), 2
    )


class TelegramAlerter:
    """
    Stateless Telegram pusher.

    Usage:
        alerter = TelegramAlerter()
        await alerter.alert(
            event="RISK_KILL_SWITCH",
            severity="ERROR",
            agent="Batman",
            message="Kill switch engaged: ...",
            symbol="BTC",
            payload={"breaker": "exec_error"},
        )
    """

    def __init__(self) -> None:
        self._log = logger.bind(agent="TelegramAlerter")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def alert(
        self,
        *,
        event: str,
        severity: str = "INFO",
        agent: str = "Mekka",
        message: str = "",
        symbol: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> bool:
        """
        Push one alert. Returns True iff Telegram acknowledged.
        Returns False (without raising) on any disable/filter/network error.
        """
        if not settings.telegram_enabled:
            return False
        if not self._should_alert(event=event, severity=severity):
            return False

        text = self._format(
            event=event,
            severity=severity,
            agent=agent,
            message=message,
            symbol=symbol,
            payload=payload,
        )

        try:
            return await self._post(text)
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"telegram alert failed (suppressed): {exc}")
            return False

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------

    def _should_alert(self, *, event: str, severity: str) -> bool:
        """
        Two ways an alert is approved:
          1. Severity ≥ telegram_alert_min_severity, OR
          2. Event in `telegram_alert_events` whitelist.
        Either path is sufficient.
        """
        if _severity_at_least(severity, settings.telegram_alert_min_severity):
            return True
        whitelist = settings.telegram_alert_events
        if whitelist and event.upper() in whitelist:
            return True
        return False

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _format(
        *,
        event: str,
        severity: str,
        agent: str,
        message: str,
        symbol: Optional[str],
        payload: Optional[dict],
    ) -> str:
        sym = f" [{symbol}]" if symbol else ""
        env = f"rede={settings.hyperliquid_network} modo={settings.mode_label}"
        _severity_labels = {
            "DEBUG": "DEBUG",
            "INFO": "INFO",
            "WARNING": "⚠️ AVISO",
            "ERROR": "🔴 ERRO",
            "CRITICAL": "🚨 CRÍTICO",
        }
        sev_label = _severity_labels.get(severity.upper(), severity)
        lines = [
            f"{sev_label} · {event}{sym}",
            f"agente: {agent}",
        ]
        if message:
            # Truncar para caber no limite de 4096 chars do Telegram
            trimmed = message if len(message) < 600 else message[:600] + "…"
            lines.append(f"mensagem: {trimmed}")
        if payload:
            # Renderiza chave=valor compacto, ignora objetos aninhados
            flat = {k: v for k, v in payload.items() if not isinstance(v, (dict, list))}
            if flat:
                kv = " ".join(f"{k}={v}" for k, v in flat.items())
                if len(kv) > 400:
                    kv = kv[:400] + "…"
                lines.append(f"dados: {kv}")
        lines.append(f"env: {env}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # High-level helpers
    # ------------------------------------------------------------------

    async def ping(self, *, reason: str = "startup") -> bool:
        """
        Send a test/startup ping to confirm the bot is alive.

        Args:
            reason: Short label shown in the message (e.g. 'startup', 'test').
        """
        if not settings.telegram_enabled:
            return False
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        text = (
            f"🤖 *Mekka Trading — Bot Online*\n"
            f"Motivo : {reason}\n"
            f"Rede   : {settings.hyperliquid_network}\n"
            f"Modo   : {settings.mode_label}\n"
            f"Paper  : {'sim' if settings.paper_trading else '🔴 LIVE'}\n"
            f"Hora   : {now}\n\n"
            f"Sistema operacional. Comandos: /help"
        )
        try:
            return await self._post(text)
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"ping failed (suppressed): {exc}")
            return False

    async def trade_opened(
        self,
        *,
        execution: "ExecutionResult",
        signal: "TradingSignal",
    ) -> bool:
        """
        Notificação rica enviada sempre que um trade é FILLED ou PAPER.

        Inclui: símbolo, direção, tamanho, entrada, SL, TP, leverage, R/R,
        confiança, modo, tag paper/live, explicação leiga e estimativa de duração.
        Nunca lança exceção — falhas são logadas e absorvidas.
        """
        if not settings.telegram_enabled:
            return False

        from src.models.execution import ExecutionStatus  # lazy, avoids circular

        if execution.status not in (ExecutionStatus.FILLED, ExecutionStatus.PAPER):
            return False

        # [Story 094] Filtro de notional mínimo — ignora trades pequenos
        try:
            _min_notional = float(getattr(settings, "min_alert_notional_usd", 0.0))
            if execution.notional_usd < _min_notional:
                self._log.debug(
                    "trade_opened: notional $%.2f < min $%.2f — ignorando alerta",
                    execution.notional_usd,
                    _min_notional,
                )
                return False
        except Exception:  # noqa: BLE001
            pass  # fail-open

        tag = "📄 PAPER" if execution.is_paper else "🔴 LIVE"
        side_emoji = "🟢 COMPRA" if (execution.side or "").upper() == "LONG" else "🔴 VENDA"
        side_upper = (execution.side or "").upper()

        # Risco / retorno
        try:
            rr = signal.risk_reward_ratio  # type: ignore[attr-defined]
            rr_str = f"{rr:.2f}" if rr else "n/d"
        except Exception:
            rr_str = "n/d"

        # Distância SL %
        try:
            sl_dist = abs(signal.entry_price - signal.stop_loss) / signal.entry_price * 100
            sl_dist_str = f"{sl_dist:.2f}%"
        except Exception:
            sl_dist_str = "n/d"

        # Distância TP %
        try:
            tp_dist = abs(signal.take_profit - signal.entry_price) / signal.entry_price * 100
            tp_dist_str = f"{tp_dist:.2f}%"
        except Exception:
            tp_dist_str = "n/d"

        # ── Explicação leiga ─────────────────────────────────────────────
        # Traduz o reasoning técnico da Vision em linguagem simples
        try:
            _raw_reasoning = (signal.reasoning or "").strip()
            _layman = self._layman_explanation(
                reasoning=_raw_reasoning,
                side=side_upper,
                confidence=signal.confidence,
            )
        except Exception:  # noqa: BLE001
            _layman = ""

        # ── Estimativa de duração ────────────────────────────────────────
        # Baseada na distância SL/TP em % e alavancagem — heurística simples
        try:
            _duration_str = self._estimate_duration(
                sl_dist_pct=float(sl_dist_str.rstrip("%")) if sl_dist_str != "n/d" else None,
                tp_dist_pct=float(tp_dist_str.rstrip("%")) if tp_dist_str != "n/d" else None,
                leverage=signal.leverage,
            )
        except Exception:  # noqa: BLE001
            _duration_str = ""

        lines = [
            f"🚀 *Trade Aberto — {execution.symbol}*  {tag}",
            "",
            f"Direção   : {side_emoji}",
            f"Entrada   : ${execution.avg_price:,.4f}",
            f"Qtd       : {execution.quantity:.6f}  (${execution.notional_usd:,.2f})",
            f"Alavancagem: {signal.leverage}x",
            f"Tamanho   : {signal.size_pct * 100:.1f}% da equity",
            "",
            f"Stop Loss : ${signal.stop_loss:,.4f}  (-{sl_dist_str})",
            f"Alvo (TP) : ${signal.take_profit:,.4f}  (+{tp_dist_str})",
            f"Risco/Ret : {rr_str}",
            "",
            f"Confiança : {signal.confidence * 100:.0f}%",
            f"Modo      : {settings.mode_label}",
            f"Rede      : {settings.hyperliquid_network}",
        ]

        if execution.order_id:
            lines.append(f"Ordem ID  : {execution.order_id}")

        # [Story 097] Qualidade do sinal + limites violados
        try:
            _meta = execution.metadata or {}
            _sqs = _meta.get("signal_quality_score")
            _breached = _meta.get("breached_limits") or []
            if _sqs is not None:
                _sqs_bar = "█" * int(_sqs / 10) + "░" * (10 - int(_sqs / 10))
                lines.append("")
                lines.append(f"📊 *Qualidade*: {_sqs:.1f}/100  [{_sqs_bar}]")
            if _breached:
                _breached_str = ", ".join(str(b) for b in _breached[:5])
                lines.append(f"⚠️ *Ajustes*  : {_breached_str}")
        except Exception:  # noqa: BLE001
            pass  # fail-open — nunca interrompe o alerta

        # Duração estimada
        if _duration_str:
            lines.append("")
            lines.append(f"⏱ *Duração estimada*: {_duration_str}")

        # Explicação leiga
        if _layman:
            lines.append("")
            lines.append(f"💡 *Por que entrar agora?*")
            lines.append(f"_{_layman}_")

        text = "\n".join(lines)

        try:
            return await self._post(text, parse_mode="Markdown")
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"trade_opened: alerta falhou (suprimido): {exc}")
            return False

    # ------------------------------------------------------------------
    # Helpers de explicação e duração
    # ------------------------------------------------------------------

    @staticmethod
    def _layman_explanation(reasoning: str, side: str, confidence: float) -> str:
        """
        Converte o reasoning técnico da Vision em linguagem acessível para
        um usuário leigo entender o motivo de entrar na operação.
        """
        if not reasoning:
            dir_pt = "compra" if side == "LONG" else "venda"
            return (
                f"Os indicadores apontam para uma oportunidade de {dir_pt}. "
                f"A IA está com {confidence * 100:.0f}% de confiança nesse movimento."
            )

        # Extrai palavras-chave do reasoning e monta texto simples
        r = reasoning.lower()
        pieces: list[str] = []

        # Tendência
        if "uptrend" in r or "bullish" in r or "alta" in r:
            pieces.append("o mercado está em tendência de alta")
        elif "downtrend" in r or "bearish" in r or "baixa" in r:
            pieces.append("o mercado está em tendência de baixa")

        # RSI
        if "rsi" in r:
            if "oversold" in r or "sobrevendido" in r:
                pieces.append("o ativo está sobrevendido (barato demais)")
            elif "overbought" in r or "sobrecomprado" in r:
                pieces.append("o ativo está sobrecomprado (caro demais)")
            else:
                pieces.append("o indicador de força (RSI) apoia a operação")

        # Suporte/resistência
        if "support" in r or "suporte" in r:
            pieces.append("o preço está em uma região de suporte forte")
        if "resistance" in r or "resistência" in r or "resistencia" in r:
            pieces.append("o preço está próximo de uma resistência importante")

        # Volume / momentum
        if "volume" in r:
            pieces.append("o volume confirma o movimento")
        if "momentum" in r:
            pieces.append("há força (momentum) no movimento atual")

        # Funding / sentiment
        if "funding" in r:
            pieces.append("as taxas de financiamento favorecem a posição")
        if "sentiment" in r or "fear" in r or "greed" in r:
            pieces.append("o sentimento do mercado apoia a entrada")

        # Breakout
        if "breakout" in r or "break" in r:
            pieces.append("o preço rompeu um nível técnico importante")

        # Fallback genérico
        if not pieces:
            dir_pt = "compra" if side == "LONG" else "venda"
            return (
                f"Múltiplos indicadores técnicos alinham para uma operação de {dir_pt}. "
                f"Confiança da IA: {confidence * 100:.0f}%."
            )

        direction_pt = "comprar" if side == "LONG" else "vender"
        intro = f"A IA decidiu {direction_pt} porque "
        body = ", ".join(pieces[:3])  # máximo 3 pontos para não ficar longo
        suffix = f". Confiança: {confidence * 100:.0f}%."
        return intro + body + suffix

    @staticmethod
    def _estimate_duration(
        sl_dist_pct: Optional[float],
        tp_dist_pct: Optional[float],
        leverage: int,
    ) -> str:
        """
        Estima a duração da operação com base na distância SL/TP e alavancagem.

        Heurística simples:
        - Distância pequena + alavancagem alta → scalp (minutos a 1h)
        - Distância média                      → swing curto (2–8h)
        - Distância grande + baixa alavancagem → swing longo (1–3 dias)
        """
        if sl_dist_pct is None and tp_dist_pct is None:
            return ""

        # Distância média entre SL e TP como referência
        dists = [d for d in [sl_dist_pct, tp_dist_pct] if d is not None]
        avg_dist = sum(dists) / len(dists)

        # Ajuste por alavancagem — mais alavancagem → movimentos menores são suficientes
        effective_dist = avg_dist / max(leverage, 1)

        if effective_dist < 0.3:
            return "Scalp — alguns minutos a 1 hora"
        elif effective_dist < 0.8:
            return "Curto prazo — 1 a 6 horas"
        elif effective_dist < 1.5:
            return "Médio prazo — 6 a 24 horas"
        else:
            return "Swing — 1 a 3 dias"

    async def position_closed(
        self,
        *,
        symbol: str,
        side: str,
        close_price: float,
        avg_entry: float,
        qty: float,
        trigger_reason: str,
        sl_trigger: Optional[float] = None,
        tp_trigger: Optional[float] = None,
    ) -> bool:
        """
        Rich notification when Cyclops closes a paper position via SL or TP.

        Includes: symbol, side, close price, entry, PnL realizado, trigger type.
        Never throws.
        """
        if not settings.telegram_enabled:
            return False

        is_sl = "SL" in trigger_reason.upper()
        is_tp = "TP" in trigger_reason.upper()
        trigger_emoji = "🛑 STOP LOSS" if is_sl else ("🎯 TAKE PROFIT" if is_tp else "⚡ TRIGGER")
        side_upper = side.upper()

        # Realized PnL
        if side_upper == "LONG":
            pnl_usd = (close_price - avg_entry) * qty
        else:
            pnl_usd = (avg_entry - close_price) * qty
        pnl_pct = (pnl_usd / (avg_entry * qty) * 100) if avg_entry * qty else 0.0
        pnl_emoji = "🟢" if pnl_usd >= 0 else "🔴"

        # SL/TP distances from entry
        sl_dist_str = ""
        if sl_trigger and avg_entry:
            d = abs(sl_trigger - avg_entry) / avg_entry * 100
            sl_dist_str = f"  (-{d:.2f}%)"
        tp_dist_str = ""
        if tp_trigger and avg_entry:
            d = abs(tp_trigger - avg_entry) / avg_entry * 100
            tp_dist_str = f"  (+{d:.2f}%)"

        lines = [
            f"{trigger_emoji} *Posição Fechada — {symbol}*",
            "",
            f"Motivo    : {trigger_reason}",
            f"Direção   : {'🟢 LONG' if side_upper == 'LONG' else '🔴 SHORT'}",
            f"Entrada   : ${avg_entry:,.4f}",
            f"Fechamento: ${close_price:,.4f}",
            f"Qtd       : {qty:.6f}",
            "",
            f"PnL Real. : {pnl_emoji} ${pnl_usd:+,.2f}  ({pnl_pct:+.2f}%)",
        ]
        if sl_trigger:
            lines.append(f"SL nível  : ${sl_trigger:,.4f}{sl_dist_str}")
        if tp_trigger:
            lines.append(f"TP nível  : ${tp_trigger:,.4f}{tp_dist_str}")
        lines += [
            "",
            f"Modo      : {settings.mode_label}  (paper)",
        ]

        text = "\n".join(lines)
        try:
            return await self._post(text, parse_mode="Markdown")
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"position_closed alert failed (suppressed): {exc}")
            return False

    async def scale_out_alert(
        self,
        *,
        symbol: str,
        side: str,
        close_price: float,
        avg_entry: float,
        closed_qty: float,
        remaining_qty: float,
        tp1_trigger: float,
        tp2_trigger: float,
        new_sl: float,
        pnl_usd: float,
    ) -> bool:
        """
        Story 065 — Notification when Cyclops fires a partial TP (scale-out).

        Informs that 50 % of the position was closed at TP1 and the stop
        was moved to breakeven. Never throws.
        """
        if not settings.telegram_enabled:
            return False

        side_upper = side.upper()
        pnl_emoji = "🟢" if pnl_usd >= 0 else "🔴"
        pnl_pct = (pnl_usd / (avg_entry * closed_qty) * 100) if avg_entry * closed_qty else 0.0

        lines = [
            f"⚡ *Partial TP — Scale-out {symbol}*",
            "",
            f"Direção         : {'🟢 LONG' if side_upper == 'LONG' else '🔴 SHORT'}",
            f"Entrada (avg)   : ${avg_entry:,.4f}",
            f"Fechado em (TP1): ${close_price:,.4f}",
            f"Qtd fechada     : {closed_qty:.6f}  (50%)",
            f"Qtd restante    : {remaining_qty:.6f}  (50%)",
            "",
            f"PnL parcial     : {pnl_emoji} ${pnl_usd:+,.2f}  ({pnl_pct:+.2f}%)",
            "",
            f"Stop → breakeven: ${new_sl:,.4f}",
            f"TP2 alvo        : ${tp2_trigger:,.4f}",
            "",
            "🏹 Posição restante corre sem risco de perda.",
            f"Modo            : {settings.mode_label}  (paper)",
        ]
        text = "\n".join(lines)
        try:
            return await self._post(text, parse_mode="Markdown")
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"scale_out_alert failed (suppressed): {exc}")
            return False

    async def wolverine_action(
        self,
        *,
        action: str,
        symbol: str,
        side: str,
        entry_price: float,
        mark_price: float,
        size: float,
        unrealized_pnl_usd: float,
        reason: str,
        new_sl: Optional[float] = None,
        new_tp: Optional[float] = None,
        close_qty: Optional[float] = None,
        is_paper: bool = True,
    ) -> bool:
        """
        Rich notification when Wolverine takes action on a position.

        Covers: TIGHTEN_STOP, TRAIL_STOP, SCALE_OUT, CLOSE, EMERGENCY_CLOSE.
        Never throws.
        """
        if not settings.telegram_enabled:
            return False

        action_upper = action.upper()

        # Emoji + label per action
        _emojis = {
            "TIGHTEN_STOP":    "🔒",
            "TRAIL_STOP":      "📈",
            "SCALE_OUT":       "✂️",
            "CLOSE":           "🔴",
            "EMERGENCY_CLOSE": "🚨",
        }
        action_emoji = _emojis.get(action_upper, "⚡")
        tag = "📄 PAPER" if is_paper else "🔴 LIVE"
        side_emoji = "🟢 LONG" if side.upper() == "LONG" else "🔴 SHORT"
        pnl_emoji = "🟢" if unrealized_pnl_usd >= 0 else "🔴"

        # PnL % from entry
        cost_basis = entry_price * size if size and entry_price else 0.0
        pnl_pct = unrealized_pnl_usd / cost_basis * 100 if cost_basis else 0.0

        lines = [
            f"{action_emoji} *Wolverine — {action_upper}  [{symbol}]*  {tag}",
            "",
            f"Direção   : {side_emoji}",
            f"Entrada   : ${entry_price:,.4f}",
            f"Mark      : ${mark_price:,.4f}",
            f"PnL atual : {pnl_emoji} ${unrealized_pnl_usd:+,.2f}  ({pnl_pct:+.2f}%)",
        ]

        # SL/TP block (for stop-modification actions)
        if new_sl is not None:
            sl_dist = abs(new_sl - entry_price) / entry_price * 100
            sl_dir = "acima" if new_sl > entry_price else "abaixo"
            lines += [
                "",
                f"Novo SL   : ${new_sl:,.4f}  ({sl_dist:.2f}% {sl_dir} entrada)",
            ]
        if new_tp is not None:
            tp_dist = abs(new_tp - entry_price) / entry_price * 100
            lines.append(f"TP        : ${new_tp:,.4f}  ({tp_dist:.2f}%)")

        # Close / scale quantity
        if close_qty is not None:
            lines += [
                "",
                f"Qtd fech. : {close_qty:.6f}",
            ]

        lines += [
            "",
            f"Motivo    : _{reason}_",
            "",
            f"Modo      : {settings.mode_label}",
        ]

        text = "\n".join(lines)
        try:
            return await self._post(text, parse_mode="Markdown")
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"wolverine_action alert failed (suppressed): {exc}")
            return False

    async def wolverine_kill_switch(
        self,
        *,
        intraday_drawdown_pct: float,
        positions_count: int,
        notes: str = "",
        is_paper: bool = True,
    ) -> bool:
        """
        Critical alert when Wolverine engages the kill switch (intraday drawdown breach).
        Never throws.
        """
        if not settings.telegram_enabled:
            return False

        tag = "📄 PAPER" if is_paper else "🔴 LIVE"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        lines = [
            f"🚨 *KILL SWITCH ATIVADO*  {tag} 🚨",
            "",
            f"Drawdown  : {intraday_drawdown_pct:.2f}%",
            f"Posições  : {positions_count} abertas",
            "",
            "⛔ *Trading pausado automaticamente até amanhã (UTC).*",
        ]
        if notes:
            short_notes = notes if len(notes) < 400 else notes[:400] + "…"
            lines += ["", f"Detalhe: _{short_notes}_"]
        lines += [
            "",
            f"Modo      : {settings.mode_label}",
            f"Hora      : {now}",
        ]

        text = "\n".join(lines)
        try:
            return await self._post(text, parse_mode="Markdown")
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"wolverine_kill_switch alert failed (suppressed): {exc}")
            return False

    async def drawdown_alert(
        self,
        *,
        current_equity: float,
        peak_equity: float,
        drawdown_pct: float,
        threshold_pct: float,
    ) -> bool:
        """
        Critical alert when daily drawdown breaches `max_daily_drawdown_pct`.

        Fires at most once per UTC day (caller must enforce dedup).
        Never throws.
        """
        if not settings.telegram_enabled:
            return False

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"🚨 *ALERTA — Drawdown Crítico* 🚨",
            "",
            f"Drawdown  : {drawdown_pct:.2f}%  (limite: {threshold_pct:.1f}%)",
            f"Equity    : ${current_equity:,.2f}",
            f"Pico dia  : ${peak_equity:,.2f}",
            f"Perda     : ${peak_equity - current_equity:,.2f}",
            "",
            "⚠️ *Trading pausado automaticamente até amanhã (UTC).*",
            "",
            f"Modo      : {settings.mode_label}",
            f"Hora      : {now}",
        ]
        text = "\n".join(lines)
        try:
            return await self._post(text, parse_mode="Markdown")
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"drawdown_alert failed (suppressed): {exc}")
            return False

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    async def _post(self, text: str, parse_mode: Optional[str] = None) -> bool:
        """POST to Telegram sendMessage. Lazy aiohttp import."""
        import aiohttp  # noqa: WPS433

        url = _tg_url(settings.telegram_bot_token)
        timeout = aiohttp.ClientTimeout(total=settings.telegram_alert_timeout_seconds)
        body: dict = {
            "chat_id": settings.telegram_chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            body["parse_mode"] = parse_mode
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=body) as resp:
                if resp.status == 200:
                    return True
                # Read once for log clarity; don't propagate
                body_text = await resp.text()
                self._log.warning(
                    f"telegram returned HTTP {resp.status}: {body_text[:200]}"
                )
                if resp.status == 429:
                    # Telegram rate limit — back off briefly so callers
                    # don't hammer. We don't retry within this call (next
                    # alert in the cycle will re-evaluate).
                    await asyncio.sleep(min(settings.telegram_alert_timeout_seconds, 2.0))
                return False
