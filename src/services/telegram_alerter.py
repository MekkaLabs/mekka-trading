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

    # Títulos amigáveis (PT, para leigo) por código de evento. Eventos sem
    # entrada caem no fallback: código com "_"→espaço em Title Case.
    _FRIENDLY_TITLES = {
        "SIGNAL_FLIP": "Mudança de direção",
        "RISK_KILL_SWITCH": "Trading pausado (trava de segurança)",
        "KILL_SWITCH_EVENT": "Trava de segurança",
        "KILL_SWITCH_ENGAGED": "Trading pausado",
        "KILL_SWITCH_RELEASED": "Trading liberado",
        "DRAWDOWN_ALERT": "Alerta de perda no dia",
        "DAILY_LOSS_LIMIT": "Limite de perda diária atingido",
        "EXEC_ERROR": "Erro ao executar ordem",
        "CYCLE_ERROR": "Erro no ciclo de análise",
        "STALE_FEED": "Dados de mercado atrasados",
        "STALE_PRICE": "Preço desatualizado",
        "ANOMALY": "Anomalia de mercado",
        "ANOMALY_DETECTED": "Anomalia de mercado",
        "LIQUIDATION_RISK": "Risco de liquidação",
        "SYSTEM_STATE": "Estado do sistema",
        "TRADE_APPROVAL_REJECTED": "Trade recusado",
        "IMPROVEMENT_PROPOSED": "Nova sugestão de melhoria",
    }

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
        """Formata um alerta genérico de forma CURTA e para LEIGO:

            ⚠️ Mudança de direção — ETH
            A IA inverteu de compra para venda no ETH.
            🧪 testnet · PAPER

        Sem jargão de código (evento bruto/agente), sem diffs. Mantém um
        rodapé compacto de ambiente para o operador saber rede/modo.
        """
        sym = f" — {symbol}" if symbol else ""
        _sev_emoji = {
            "DEBUG": "🔍",
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "ERROR": "🔴",
            "CRITICAL": "🚨",
        }
        icon = _sev_emoji.get(severity.upper(), "•")
        title = TelegramAlerter._FRIENDLY_TITLES.get(
            event.upper(), event.replace("_", " ").title()
        )
        lines = [f"{icon} {title}{sym}"]
        if message:
            # Curto: o limite do Telegram é 4096, mas para leigo cortamos cedo.
            trimmed = message if len(message) < 280 else message[:280] + "…"
            lines.append(trimmed)
        if payload:
            # Só pares simples (chave=valor); ignora objetos aninhados/listas.
            flat = {k: v for k, v in payload.items() if not isinstance(v, (dict, list))}
            if flat:
                kv = " · ".join(f"{k}={v}" for k, v in flat.items())
                if len(kv) > 180:
                    kv = kv[:180] + "…"
                lines.append(kv)
        net = str(settings.hyperliquid_network)
        net_icon = "🟢" if net.lower().startswith("main") else "🧪"
        lines.append(f"{net_icon} {net} · {settings.mode_label}")
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

        # Formato compacto e leigo (2026-06-01): o essencial em ~6 linhas.
        _conf_line = f"Confiança {signal.confidence * 100:.0f}%"
        if rr_str != "n/d":
            _conf_line += f"  ·  R/R {rr_str}"
        if _duration_str:
            _conf_line += f"  ·  ⏱ {_duration_str}"

        lines = [
            f"🚀 *Trade aberto — {execution.symbol}*  {tag}",
            f"{side_emoji}  ·  {signal.size_pct * 100:.1f}% da banca  ·  {signal.leverage}x",
            f"Entrada ${execution.avg_price:,.4f}  (${execution.notional_usd:,.0f})",
            f"🎯 Alvo ${signal.take_profit:,.4f} (+{tp_dist_str})  ·  🛑 Stop ${signal.stop_loss:,.4f} (-{sl_dist_str})",
            _conf_line,
        ]

        # Ajustes aplicados pelo risk manager — só aparece se houve.
        try:
            _breached = (execution.metadata or {}).get("breached_limits") or []
            if _breached:
                lines.append(f"⚠️ Ajustes: {', '.join(str(b) for b in _breached[:3])}")
        except Exception:  # noqa: BLE001
            pass  # fail-open — nunca interrompe o alerta

        # Explicação leiga (o "porquê" em uma frase).
        if _layman:
            lines.append(f"💡 _{_layman}_")

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

        _result_word = "no lucro 🟢" if pnl_usd >= 0 else "no prejuízo 🔴"
        _dir_pt = "compra" if side_upper == "LONG" else "venda"
        lines = [
            f"{trigger_emoji} *Posição fechada — {symbol}*",
            f"Resultado: {pnl_emoji} ${pnl_usd:+,.2f}  ({pnl_pct:+.2f}%) — {_result_word}",
            f"{_dir_pt.capitalize()}: entrada ${avg_entry:,.4f} → saída ${close_price:,.4f}",
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
            f"✂️ *Lucro parcial — {symbol}*",
            f"Fechou metade no 1º alvo: {pnl_emoji} ${pnl_usd:+,.2f} ({pnl_pct:+.2f}%)",
            f"🏹 O resto corre sem risco (stop movido para o ponto de entrada).",
            f"Próximo alvo: ${tp2_trigger:,.4f}",
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

        # Emoji + frase leiga por ação (em vez do código técnico).
        _actions = {
            "TIGHTEN_STOP":    ("🔒", "Apertou o stop para proteger"),
            "TRAIL_STOP":      ("📈", "Subiu o stop seguindo o lucro"),
            "SCALE_OUT":       ("✂️", "Realizou lucro parcial"),
            "CLOSE":           ("🔴", "Fechou a posição"),
            "EMERGENCY_CLOSE": ("🚨", "Fechou em emergência"),
        }
        action_emoji, action_phrase = _actions.get(action_upper, ("⚡", action_upper))
        pnl_emoji = "🟢" if unrealized_pnl_usd >= 0 else "🔴"

        # PnL % from entry
        cost_basis = entry_price * size if size and entry_price else 0.0
        pnl_pct = unrealized_pnl_usd / cost_basis * 100 if cost_basis else 0.0

        lines = [
            f"{action_emoji} *{symbol} — {action_phrase}*",
            f"PnL atual: {pnl_emoji} ${unrealized_pnl_usd:+,.2f} ({pnl_pct:+.2f}%)",
        ]
        if new_sl is not None:
            lines.append(f"Novo stop: ${new_sl:,.4f}")
        if reason:
            _r = reason if len(reason) < 140 else reason[:140] + "…"
            lines.append(f"💡 _{_r}_")

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

        lines = [
            f"🚨 *Trading pausado automaticamente* {tag}",
            f"Perda no dia chegou a {intraday_drawdown_pct:.2f}% — {positions_count} posição(ões) aberta(s).",
            "⛔ Nenhum trade novo até amanhã (UTC).",
        ]
        if notes:
            short_notes = notes if len(notes) < 160 else notes[:160] + "…"
            lines.append(f"💡 _{short_notes}_")
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

        lines = [
            f"🚨 *Trading pausado — perda no dia* 🚨",
            f"Caiu {drawdown_pct:.2f}% hoje (limite: {threshold_pct:.1f}%).",
            f"Perda: ${peak_equity - current_equity:,.2f}  ·  Saldo: ${current_equity:,.2f}",
            "⚠️ Nenhum trade novo até amanhã (UTC).",
        ]
        text = "\n".join(lines)
        try:
            return await self._post(text, parse_mode="Markdown")
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"drawdown_alert failed (suppressed): {exc}")
            return False

    async def improvement_proposed(self, rec: object) -> bool:
        """Send one pending improvement-council proposal to Telegram so the
        operator can approve/reject it from there (/aprovar <id>). Mirrors the
        dashboard's Central de Melhorias. Accepts a CouncilRecommendation or a
        dict. Never throws.
        """
        if not settings.telegram_enabled:
            return False

        def _g(obj, key, default=""):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        rid = _g(rec, "id") or _g(rec, "rec_id") or "?"
        title = _g(rec, "title", "(sem título)")
        area = _g(rec, "area", "")
        domain = _g(rec, "domain", "")
        priority = _g(rec, "priority", "")
        impact = str(_g(rec, "impact", "")).upper()
        pm = _g(rec, "premortem", {}) or {}
        verdict = _g(pm, "verdict", "") or _g(rec, "premortem_verdict", "")
        hunger = _g(pm, "hunger", "") or _g(rec, "premortem_hunger", "")
        rationale = _g(rec, "rationale", "")

        lines = [
            "🛠️ *Conselho de Melhorias — nova proposta*",
            "",
            f"*{title}*",
            f"ID: `{rid}`",
        ]
        meta = " · ".join([x for x in [domain, area, priority, impact] if x])
        if meta:
            lines.append(meta)
        if verdict:
            lines.append(f"Galactus: {verdict}" + (f" (fome {hunger})" if hunger != "" else ""))
        if rationale:
            lines.append("")
            lines.append(str(rationale)[:280])
        lines += [
            "",
            "Use os botões abaixo ou comandos /aprovar / /reprovar.",
            "(Também é possível decidir na Central de Melhorias do dashboard.)",
        ]
        text = "\n".join(lines)
        # Inline keyboard — operador aprova/reprova com 1 clique
        reply_markup = {
            "inline_keyboard": [[
                {"text": "✅ Aprovar", "callback_data": f"improve_approve:{rid}"},
                {"text": "❌ Reprovar", "callback_data": f"improve_reject:{rid}"},
            ]]
        }
        try:
            return await self._post(text, parse_mode="Markdown", reply_markup=reply_markup)
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"improvement_proposed failed (suppressed): {exc}")
            return False

    async def system_state(self, *, state: str, detail: str = "") -> bool:
        """Notify the operator that the runtime was turned on/off/rebooted.
        Bypasses the severity filter (always delivered). Never throws.
        """
        if not settings.telegram_enabled:
            return False
        emoji = {"running": "🟢", "stopped": "🔴", "rebooted": "🔄"}.get(state, "⚪")
        label = {"running": "LIGADO", "stopped": "DESLIGADO", "rebooted": "REINICIADO"}.get(state, state.upper())
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [f"{emoji} *Sistema {label}*"]
        if detail:
            lines.append(detail)
        lines.append(f"Modo: {settings.mode_label} · {now}")
        try:
            return await self._post("\n".join(lines), parse_mode="Markdown")
        except Exception as exc:  # noqa: BLE001
            self._log.warning(f"system_state failed (suppressed): {exc}")
            return False

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    async def _post(
        self,
        text: str,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[dict] = None,
    ) -> bool:
        """POST to Telegram sendMessage. Lazy aiohttp import.

        Args:
          reply_markup: opcional. Quando fornecido, envia inline keyboard
            (ex.: {"inline_keyboard": [[{"text": "Aprovar", "callback_data": "..."}]]}).
        """
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
        if reply_markup:
            body["reply_markup"] = reply_markup
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
