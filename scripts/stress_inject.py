#!/usr/bin/env python3
"""
scripts/stress_inject.py
========================
Injetor de cenários de stress test para o sistema em paper-on-testnet.

Cada subcomando exercita um path crítico do sistema sem depender de o
mercado real produzir o evento. Para situações que exigem movimento de
preço genuíno (flash crash, pump), o script imprime instruções de como
provocar via UI ou aguardar — mas NUNCA tenta enviar ordens reais.

Uso geral
---------
    source .venv313/bin/activate
    python scripts/stress_inject.py <scenario> [opções]

Listar cenários disponíveis:
    python scripts/stress_inject.py --list

Hard rules
----------
- O script NÃO envia ordens reais nem em mainnet nem em testnet.
- Toda mutação de estado é local (audit log, kill switch file, DB).
- Cenários que exigem mercado real apenas instrumentam observação.
- Cada execução loga seu próprio evento de audit ("STRESS_TEST_INJECT").
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

# Garante que o projeto está no path quando rodado de qualquer lugar.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ============================================================
# Helpers
# ============================================================

def _info(msg: str) -> None:
    print(f"\033[36m[stress]\033[0m {msg}")


def _ok(msg: str) -> None:
    print(f"\033[32m[ ok ]\033[0m {msg}")


def _warn(msg: str) -> None:
    print(f"\033[33m[warn]\033[0m {msg}")


def _err(msg: str) -> None:
    print(f"\033[31m[fail]\033[0m {msg}", file=sys.stderr)


async def _log_inject_event(scenario: str, payload: dict) -> None:
    """Audit-log the injection itself so the operator can correlate
    a system reaction back to the stress test that triggered it.

    Best-effort: if the repo isn't initialised yet (fresh checkout)
    we skip silently rather than blocking the actual stress action.
    """
    try:
        from src.persistence.repository import MekkaRepository  # noqa: WPS433
        await MekkaRepository.initialize()
        await MekkaRepository.log_event(
            agent="stress_inject",
            event="STRESS_TEST_INJECT",
            payload={"scenario": scenario, **payload},
            severity="INFO",
        )
    except Exception as exc:  # noqa: BLE001
        _warn(f"audit log skipped: {exc}")


# ============================================================
# Scenario implementations
# ============================================================

async def scenario_kill_switch_engage(args: argparse.Namespace) -> int:
    """Aciona o kill switch como se Wolverine tivesse detectado drawdown crítico.

    Comportamento esperado:
      * is_kill_switch_active() retorna True imediatamente
      * Próximo ciclo NickFury entra em skip_reason="kill_switch"
      * Dashboard mostra estado kill no Live Risk Panel
      * Telegram dispara alerta crítico (se configurado)
      * /api/trade/execute responde com REJECTED se chamado
    """
    from src.agents.batman import engage_kill_switch, is_kill_switch_active
    reason = args.reason or "stress_test_manual_engage"
    engage_kill_switch(reason=reason, agent="stress_inject")
    if is_kill_switch_active():
        _ok(f"kill switch engaged: reason='{reason}'")
        await _log_inject_event("kill_switch_engage", {"reason": reason})
        _info("para liberar: python scripts/stress_inject.py kill-switch-release")
        return 0
    _err("engage_kill_switch foi chamado mas is_kill_switch_active continua False")
    return 1


async def scenario_kill_switch_release(args: argparse.Namespace) -> int:
    """Libera o kill switch — uso pós-cenário para retornar ao baseline."""
    from src.agents.batman import is_kill_switch_active, release_kill_switch
    if not is_kill_switch_active():
        _warn("kill switch já estava desligado")
        return 0
    release_kill_switch()
    if is_kill_switch_active():
        _err("release_kill_switch chamado mas estado não mudou")
        return 1
    _ok("kill switch released")
    await _log_inject_event("kill_switch_release", {})
    return 0


async def scenario_fake_signal(args: argparse.Namespace) -> int:
    """Injeta um sinal sintético no DB (LONG ou SHORT, com SL/TP).

    Comportamento esperado:
      * SignalRecord aparece em /api/signals em <1 ciclo do dashboard
      * Se /api/trade/execute for chamado pelo operador, Batman aprova
        (ou rejeita por gate). Cyclops começa a monitorar SL/TP.
    """
    from src.persistence.db import get_session  # noqa: WPS433
    from src.persistence.models import SignalRecord  # noqa: WPS433
    from src.persistence.repository import MekkaRepository  # noqa: WPS433

    side = args.side.upper()
    if side not in ("LONG", "SHORT"):
        _err(f"side inválido: {side}. Use --side long ou --side short")
        return 2
    symbol = args.symbol.upper()
    entry = float(args.entry)
    # SL/TP defaults: ~3% SL, ~7% TP no sentido da posição.
    if side == "LONG":
        sl = args.sl if args.sl else entry * 0.97
        tp = args.tp if args.tp else entry * 1.07
    else:
        sl = args.sl if args.sl else entry * 1.03
        tp = args.tp if args.tp else entry * 0.93

    await MekkaRepository.initialize()
    async with get_session() as session:
        sig = SignalRecord(
            timestamp=datetime.now(timezone.utc),
            symbol=symbol,
            action=side,
            confidence=float(args.confidence),
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            size_pct=float(args.size_pct),
            leverage=int(args.leverage),
            risk_reward=abs((tp - entry) / (entry - sl)) if entry != sl else 0.0,
            reasoning=f"[STRESS TEST] Sinal sintético {side} {symbol} injetado via stress_inject",
        )
        session.add(sig)
        await session.commit()
    _ok(
        f"sinal injetado: {side} {symbol} @ {entry:.2f} "
        f"(SL={sl:.2f}, TP={tp:.2f}, conf={args.confidence}, "
        f"size={args.size_pct*100:.1f}%, lev={args.leverage}x)"
    )
    await _log_inject_event("fake_signal", {
        "side": side, "symbol": symbol, "entry": entry, "sl": sl, "tp": tp,
        "confidence": args.confidence, "size_pct": args.size_pct,
        "leverage": args.leverage,
    })
    return 0


async def scenario_telegram_flood(args: argparse.Namespace) -> int:
    """Dispara N alertas Telegram em sequência para validar dedup window.

    Comportamento esperado:
      * Apenas 1 alerta é entregue se N ocorrem dentro da janela de dedup
        (configurada em settings — default 5 min).
      * Dedup store persiste o key em memory/alerts/.
      * Audit log registra N tentativas mas só 1 SENT.
    """
    try:
        from src.services.telegram_alerter import TelegramAlerter  # noqa: WPS433
    except ImportError as exc:
        _err(f"TelegramAlerter unavailable: {exc}")
        return 1

    n = int(args.count)
    alerter = TelegramAlerter()
    sent = 0
    for i in range(n):
        try:
            ok = await alerter.ping(reason=f"stress flood {i+1}/{n}")
            if ok:
                sent += 1
        except Exception as exc:  # noqa: BLE001
            _warn(f"ping {i+1} raised: {exc}")
        await asyncio.sleep(0.2)
    _ok(f"telegram flood: {sent}/{n} attempts returned ok (dedup may have filtered)")
    await _log_inject_event("telegram_flood", {"requested": n, "ok_count": sent})
    return 0


async def scenario_drawdown_alert(args: argparse.Namespace) -> int:
    """Dispara um alerta de drawdown manual via TelegramAlerter.

    Útil para validar que a mensagem de drawdown está formatada
    corretamente em pt-BR e que dedup por UTC-day funciona.
    """
    try:
        from src.services.telegram_alerter import TelegramAlerter  # noqa: WPS433
    except ImportError as exc:
        _err(f"TelegramAlerter unavailable: {exc}")
        return 1

    alerter = TelegramAlerter()
    pct = float(args.pct)
    eq_now = 9000.0
    eq_peak = 10000.0
    try:
        await alerter.drawdown_alert(
            current_equity=eq_now,
            peak_equity=eq_peak,
            drawdown_pct=pct,
            threshold_pct=10.0,
        )
        _ok(f"drawdown alert sent (pct={pct}%)")
    except Exception as exc:  # noqa: BLE001
        _err(f"drawdown alert failed: {exc}")
        return 1
    await _log_inject_event("drawdown_alert", {"pct": pct, "eq_now": eq_now})
    return 0


async def scenario_close_all_paper(args: argparse.Namespace) -> int:
    """Fecha todas posições paper abertas via POST /api/positions/close.

    Cenário operacional: o operador detecta um evento externo
    (notícia, hack, halt) e quer zerar exposição imediatamente.

    Comportamento esperado:
      * Para cada posição aberta, um trade de fechamento é inserido.
      * Audit log registra POSITION_CLOSED para cada uma.
      * Telegram pode disparar alerta agregado.
      * Painel positions zera em <2s.
    """
    import aiohttp  # noqa: WPS433
    from src.config.settings import settings  # noqa: WPS433
    from src.dashboard.positions_provider import _fetch_paper_positions  # noqa: WPS433

    base_url = f"http://{args.host}:{args.port}"
    pos = await _fetch_paper_positions()
    items = pos.get("items", [])
    if not items:
        _warn("nenhuma posição paper aberta para fechar")
        return 0

    closed = 0
    failed = 0
    async with aiohttp.ClientSession() as sess:
        for it in items:
            payload = {"symbol": it["symbol"], "side": it["side"], "qty": it["size"]}
            try:
                async with sess.post(
                    f"{base_url}/api/positions/close",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status < 400:
                        closed += 1
                        _ok(f"closed {it['side']} {it['symbol']} qty={it['size']}")
                    else:
                        failed += 1
                        body = await resp.text()
                        _warn(f"close failed {it['symbol']}: HTTP {resp.status} — {body[:100]}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                _warn(f"close failed {it['symbol']}: {exc}")
    _ok(f"close_all_paper: {closed} closed, {failed} failed")
    await _log_inject_event("close_all_paper", {"closed": closed, "failed": failed})
    return 0 if failed == 0 else 1


async def scenario_mode_switch(args: argparse.Namespace) -> int:
    """Troca o trading mode global (conservative/balanced/aggressive).

    Útil para validar que a troca:
      * Persiste em data/runtime_mode.json
      * Próximo ciclo Vision/Batman usa os novos parâmetros
      * Audit log registra MODE_CHANGED
      * UI atualiza o botão Modo Global em <30s (polling interval)
    """
    from src.config.runtime_mode import VALID_MODES, get_mode, set_mode, get_params  # noqa: WPS433
    target = args.mode.lower()
    if target not in VALID_MODES:
        _err(f"modo inválido: {target}. Use um de {VALID_MODES}")
        return 2
    prev = get_mode()
    if prev == target:
        _warn(f"modo já era '{target}', nada a fazer")
        return 0
    preset = set_mode(target)
    _ok(f"mode switched: {prev} → {target}")
    _info(f"params ativos: size_pct={preset.get('max_position_size_pct')}, "
          f"leverage={preset.get('max_leverage')}, assets={preset.get('trading_assets')}")
    await _log_inject_event("mode_switch", {"prev": prev, "target": target})
    return 0


async def scenario_skew_check(args: argparse.Namespace) -> int:
    """Probes the clock-skew check against the configured Bybit endpoint
    sem precisar passar pelo IronMan.

    NÃO altera o relógio (isso exige sudo). Mas reporta o skew real
    contra o servidor Bybit para o operador saber se NTP está OK.
    """
    try:
        import ccxt.async_support as ccxt  # noqa: WPS433
    except ImportError:
        _err("ccxt não instalado")
        return 1
    from src.config.settings import settings  # noqa: WPS433
    if settings.active_exchange != "bybit":
        _warn(f"ACTIVE_EXCHANGE={settings.active_exchange}; teste foca em Bybit")
    cfg = {
        "apiKey": settings.bybit_api_key or "_",
        "secret": settings.bybit_api_secret or "_",
        "options": {"defaultType": "swap"},
    }
    ex = ccxt.bybit(cfg)
    try:
        if settings.bybit_testnet:
            ex.set_sandbox_mode(True)
        server_ms = int(await ex.fetch_time())
    finally:
        await ex.close()
    local_ms = int(time.time() * 1000)
    skew = local_ms - server_ms
    if abs(skew) > 5000:
        _err(f"CLOCK SKEW CRÍTICO: {skew:+d}ms (limite ±5000ms) — fix NTP")
        _info("macOS:  sudo sntp -sS time.apple.com")
        _info("Linux:  sudo timedatectl set-ntp true")
    elif abs(skew) > 1000:
        _warn(f"clock skew alto: {skew:+d}ms — funcional, mas considere sync NTP")
    else:
        _ok(f"clock skew OK: {skew:+d}ms")
    await _log_inject_event("skew_check", {"skew_ms": skew})
    return 0


async def scenario_market_event_observe(args: argparse.Namespace) -> int:
    """Apenas marca um ponto no audit log para correlação com eventos
    de mercado externo (notícia, pump, dump).

    Use ANTES de iniciar a observação manual. Depois compare
    /api/audit?since=<este_evento> com o que o sistema reagiu.
    """
    label = args.label
    await _log_inject_event("market_event_observe_marker", {
        "label": label,
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    _ok(f"marker '{label}' gravado no audit log")
    _info("agora observe /api/audit, /api/signals, /api/positions, e os logs do servidor")
    _info(f"filtre depois por: STRESS_TEST_INJECT label={label}")
    return 0


# ============================================================
# Registry
# ============================================================

SCENARIOS: dict[str, tuple[str, Callable]] = {
    "kill-switch-engage": (
        "Aciona kill switch (simula crash de drawdown crítico)",
        scenario_kill_switch_engage,
    ),
    "kill-switch-release": (
        "Libera kill switch (volta ao baseline)",
        scenario_kill_switch_release,
    ),
    "fake-signal": (
        "Injeta sinal sintético LONG/SHORT no DB",
        scenario_fake_signal,
    ),
    "telegram-flood": (
        "Dispara N alertas Telegram para validar dedup window",
        scenario_telegram_flood,
    ),
    "drawdown-alert": (
        "Dispara alerta manual de drawdown",
        scenario_drawdown_alert,
    ),
    "close-all-paper": (
        "Fecha todas posições paper via /api/positions/close",
        scenario_close_all_paper,
    ),
    "mode-switch": (
        "Troca trading mode global (conservative/balanced/aggressive)",
        scenario_mode_switch,
    ),
    "skew-check": (
        "Mede clock skew real contra o servidor Bybit",
        scenario_skew_check,
    ),
    "market-event-marker": (
        "Grava marker no audit log para correlacionar com evento externo",
        scenario_market_event_observe,
    ),
}


def _list_scenarios() -> int:
    print("Cenários disponíveis:")
    for name, (desc, _fn) in SCENARIOS.items():
        print(f"  {name:30s}  {desc}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="stress_inject",
        description="Injetor de cenários de stress test para paper-on-testnet",
    )
    parser.add_argument("--list", action="store_true", help="Lista cenários e sai")
    sub = parser.add_subparsers(dest="scenario", metavar="SCENARIO")

    # Kill switch engage
    p_ke = sub.add_parser("kill-switch-engage", help="Aciona kill switch")
    p_ke.add_argument("--reason", default="", help="Motivo registrado no audit log")

    # Kill switch release
    sub.add_parser("kill-switch-release", help="Libera kill switch")

    # Fake signal
    p_fs = sub.add_parser("fake-signal", help="Injeta sinal sintético no DB")
    p_fs.add_argument("--side", default="long", choices=["long", "short"])
    p_fs.add_argument("--symbol", default="BTC")
    p_fs.add_argument("--entry", type=float, default=65000.0)
    # Argparse interpreta `%` em help; escapar com %% para evitar ValueError.
    p_fs.add_argument("--sl", type=float, default=0.0, help="0 = auto (entry +/- 3%%)")
    p_fs.add_argument("--tp", type=float, default=0.0, help="0 = auto (entry +/- 7%%)")
    p_fs.add_argument("--confidence", type=float, default=0.78)
    p_fs.add_argument("--size-pct", type=float, default=0.02, dest="size_pct")
    p_fs.add_argument("--leverage", type=int, default=3)

    # Telegram flood
    p_tf = sub.add_parser("telegram-flood", help="Flood de alertas Telegram")
    p_tf.add_argument("--count", type=int, default=5)

    # Drawdown alert
    p_da = sub.add_parser("drawdown-alert", help="Alerta de drawdown manual")
    p_da.add_argument("--pct", type=float, default=15.0)

    # Close all paper
    p_ca = sub.add_parser("close-all-paper", help="Fecha todas posições paper")
    p_ca.add_argument("--host", default="127.0.0.1")
    p_ca.add_argument("--port", type=int, default=8787)

    # Mode switch
    p_ms = sub.add_parser("mode-switch", help="Troca trading mode global")
    p_ms.add_argument("mode", choices=["conservative", "balanced", "aggressive"])

    # Skew check
    sub.add_parser("skew-check", help="Mede clock skew real contra Bybit")

    # Market event marker
    p_me = sub.add_parser("market-event-marker", help="Marca audit log antes de evento externo")
    p_me.add_argument("--label", default="external_event")

    args = parser.parse_args()
    if args.list:
        return _list_scenarios()
    if not args.scenario:
        parser.print_help()
        return 2
    if args.scenario not in SCENARIOS:
        _err(f"cenário desconhecido: {args.scenario}")
        return 2
    _, fn = SCENARIOS[args.scenario]
    return asyncio.run(fn(args))


if __name__ == "__main__":
    sys.exit(main())
