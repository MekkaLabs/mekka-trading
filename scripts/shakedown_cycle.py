"""
scripts/shakedown_cycle.py
==========================
Shakedown SEGURO de um ciclo completo do pipeline.

Roda UM run_main_cycle() ponta-a-ponta para detectar bugs de integração que
os testes unitários não pegam, com ZERO efeito colateral:

  - paper_trading forçado True  → nenhuma ordem real (IronMan simula)
  - operation_mode = automatic  → sem gate de aprovação humano (não trava 120s)
  - Telegram neutralizado       → nenhum alerta/mensagem enviada
  - timeout global              → nunca pendura

Imprime, por símbolo: o que cada camada produziu, is_safe_to_trade, a decisão
do Vision, o veredito do Batman e se houve execução (simulada). Qualquer
exceção é capturada e reportada.

Uso:
    python scripts/shakedown_cycle.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import traceback
from pathlib import Path

# Garante que o repo root esteja no path (permite rodar como script direto).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Força ambiente seguro ANTES de importar settings/agentes.
os.environ["MENTOR_AUTO_APPLY_ENABLED"] = "false"
os.environ["IMPLEMENTER_WORKER_ENABLED"] = "false"


async def _main() -> int:
    from src.config import operation_mode as om
    from src.config.settings import settings

    # 1) Força paper (nenhuma ordem real chega à corretora)
    try:
        object.__setattr__(settings, "paper_trading", True)
    except Exception:
        settings.paper_trading = True  # type: ignore[misc]

    # 2) Modo automatic em memória (sem gate humano, sem persistir em disco)
    om._reset_for_tests()
    om._current_mode = "automatic"  # type: ignore[attr-defined]
    om._loaded = True               # type: ignore[attr-defined]

    print("=" * 64)
    print("SHAKEDOWN — ciclo único (paper forçado, automatic, sem Telegram)")
    print("=" * 64)
    print(f"  paper_trading      : {settings.paper_trading}")
    print(f"  operation_mode     : {om.get_operation_mode()}")
    print(f"  requires_approval  : {om.requires_trade_approval()}")
    print(f"  active_exchange    : {getattr(settings, 'active_exchange', '?')}")
    print(f"  trading_assets     : {getattr(settings, 'trading_assets', '?')}")
    print("-" * 64)

    from src.agents.nick_fury import NickFury

    fury = NickFury()

    # 3) Neutraliza qualquer envio de Telegram (alerter vira no-op)
    try:
        tg = getattr(fury, "_telegram", None)
        if tg is not None:
            async def _noop(*a, **k):  # noqa: ANN001
                return True
            for meth in ("alert", "send", "push", "ping"):
                if hasattr(tg, meth):
                    setattr(tg, meth, _noop)
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] não consegui neutralizar Telegram: {exc}")

    await fury.initialize()
    try:
        reports = await asyncio.wait_for(fury.run_main_cycle(), timeout=120.0)
    except asyncio.TimeoutError:
        print("\n❌ TIMEOUT — o ciclo não completou em 120s (possível pendura de rede/API).")
        return 2
    finally:
        try:
            await fury.shutdown()
        except Exception:  # noqa: BLE001
            pass

    print("\n" + "=" * 64)
    print(f"RESULTADO — {len(reports or [])} report(s)")
    print("=" * 64)
    for r in reports or []:
        sig = getattr(r, "signal", None)
        appr = getattr(r, "approval", None)
        execu = getattr(r, "execution", None)
        action = getattr(getattr(sig, "action", None), "value", "—")
        conf = getattr(sig, "confidence", None)
        execu_ok = getattr(execu, "status", None)
        print(f"\n● {getattr(r, 'symbol', '?')}")
        print(f"   Vision    : {action}"
              + (f" (conf={conf:.2f})" if isinstance(conf, (int, float)) else ""))
        if appr is not None:
            print(f"   Batman    : executable={getattr(appr, 'is_executable', '?')} "
                  f"size={getattr(appr, 'adjusted_size_pct', '?')} "
                  f"lev={getattr(appr, 'adjusted_leverage', '?')}")
            reasons = getattr(appr, "reasons", None)
            if reasons:
                print(f"   Reasons   : {', '.join(map(str, reasons))[:200]}")
        if execu is not None:
            print(f"   IronMan   : status={getattr(execu_ok, 'value', execu_ok)} (simulado)")
    print("\n✅ Ciclo completou sem exceção fatal.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(_main()))
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:  # noqa: BLE001
        print("\n❌ EXCEÇÃO FATAL no shakedown:")
        traceback.print_exc()
        sys.exit(1)
