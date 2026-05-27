#!/usr/bin/env python3
"""
scripts/clear_orphan_stops.py
==============================
Diagnostica e (opcionalmente) cancela stop orders reduce-only na Binance
Futures para liberar a quota global do erro `-4045` ("Reach max stop
order limit").

A Binance Futures impõe limite de stop orders **POR CONTA** (não por
símbolo). Quando esse limite enche, qualquer SL/TP novo é rejeitado.

Uso
---
    # 1) Diagnóstico SEM cancelar (sempre rode primeiro)
    python3 scripts/clear_orphan_stops.py --dry-run

    # 2) Cancelar apenas stops de símbolos SEM posição (seguro)
    python3 scripts/clear_orphan_stops.py --cancel-orphans

    # 3) Cancelar TODOS os stops reduce-only (AGRESSIVO — pode deixar
    #    posições ativas sem SL temporariamente; o guardian recoloca)
    python3 scripts/clear_orphan_stops.py --cancel-all-stops

    # 4) Cancelar stops apenas de um símbolo específico
    python3 scripts/clear_orphan_stops.py --cancel-symbol ETH/USDT:USDT

Exit codes
----------
    0 - sucesso
    1 - erro de configuração
    2 - erro de I/O com a exchange
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


async def _get_exchange():
    """Obtem instância CCXT da Binance usando IronMan (mesma config do runtime)."""
    from src.agents.iron_man import IronMan
    from src.config.settings import settings

    if settings.active_exchange != "binance":
        print(f"ERROR: ACTIVE_EXCHANGE deve ser 'binance', atual={settings.active_exchange}")
        sys.exit(1)
    ir = IronMan()
    exchange = await ir._get_ccxt_exchange("binance")
    # Acknowledge CCXT warning sobre fetch_open_orders sem símbolo
    if hasattr(exchange, "options"):
        exchange.options["warnOnFetchOpenOrdersWithoutSymbol"] = False
    return exchange


def _is_reduce_only_stop(o: dict) -> bool:
    typ = str(o.get("type") or "").lower()
    info = o.get("info") or {}
    itype = str(info.get("type") or "").lower()
    is_algo = (
        "stop" in typ or "stop" in itype
        or "take_profit" in typ or "take_profit" in itype
    )
    if not is_algo:
        return False
    ro = o.get("reduceOnly")
    if ro is None:
        ro = info.get("reduceOnly") or info.get("reduce_only")
    return bool(ro)


async def _collect_state(exchange) -> tuple[list[dict], list[dict]]:
    """Retorna (positions_with_size, all_open_orders)."""
    try:
        positions = await exchange.fetch_positions()
    except Exception as exc:
        print(f"ERROR: fetch_positions falhou: {exc}")
        sys.exit(2)
    active = [p for p in positions if abs(float(p.get("contracts") or 0)) > 0]

    try:
        orders = await exchange.fetch_open_orders()
    except Exception as exc:
        print(f"ERROR: fetch_open_orders (global) falhou: {exc}")
        sys.exit(2)
    return active, orders or []


def _print_diagnosis(active, orders) -> tuple[set[str], list[dict], list[dict]]:
    """Print state + retorna (active_symbols, orphan_stops, all_stops)."""
    active_syms = {str(p.get("symbol") or "") for p in active}
    all_stops = [o for o in orders if _is_reduce_only_stop(o)]
    orphans = [o for o in all_stops if str(o.get("symbol") or "") not in active_syms]

    print("=" * 60)
    print("ESTADO DA CONTA (Binance Futures via CCXT)")
    print("=" * 60)
    print(f"  Posições ATIVAS: {len(active)}")
    for p in active:
        sym = p.get("symbol")
        contracts = p.get("contracts")
        side = p.get("side")
        pnl = p.get("unrealizedPnl")
        print(f"    · {sym:20s} side={side or '?':5s} qty={contracts} uPnL={pnl}")
    print()
    print(f"  Ordens abertas (total): {len(orders)}")
    print(f"  → reduce-only stops/TPs: {len(all_stops)}")
    print(f"  → ÓRFÃOS (sem posição ativa): {len(orphans)}")
    print()
    if all_stops:
        print(f"  Stops por símbolo:")
        by_sym: dict[str, int] = {}
        for o in all_stops:
            s = str(o.get("symbol") or "?")
            by_sym[s] = by_sym.get(s, 0) + 1
        for s, n in sorted(by_sym.items(), key=lambda x: -x[1]):
            mark = "✓" if s in active_syms else "ORFAN"
            print(f"    · {s:20s} {n} stops   [{mark}]")
    print("=" * 60)
    return active_syms, orphans, all_stops


async def _cancel(exchange, orders: list[dict]) -> int:
    cancelled = 0
    for o in orders:
        oid = o.get("id")
        sym = o.get("symbol")
        if not oid or not sym:
            continue
        try:
            await exchange.cancel_order(oid, sym)
            cancelled += 1
            print(f"  ✓ cancelado: {sym} order_id={oid}")
        except Exception as exc:
            print(f"  ✗ falha: {sym} order_id={oid} → {exc}")
    return cancelled


async def main() -> int:
    ap = argparse.ArgumentParser(description="Limpa stops reduce-only para liberar quota -4045")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true",
                   help="Apenas diagnóstico, não cancela nada (default)")
    g.add_argument("--cancel-orphans", action="store_true",
                   help="Cancela só stops de símbolos SEM posição ativa (seguro)")
    g.add_argument("--cancel-all-stops", action="store_true",
                   help="Cancela TODOS reduce-only stops (agressivo; guardian recoloca)")
    g.add_argument("--cancel-symbol", metavar="SYM", default=None,
                   help="Cancela stops apenas do símbolo informado (ex: 'BTC/USDT:USDT')")
    g.add_argument("--nuke", action="store_true",
                   help="MASS-CANCEL: usa cancel_all_orders por símbolo para limpar "
                        "stops 'fantasma' que não aparecem em fetch_open_orders "
                        "(bug conhecido da Binance Testnet). Símbolos: BTC, ETH, "
                        "SOL, BNB nas variações USDT-M. Não toca em posições.")
    args = ap.parse_args()

    exchange = await _get_exchange()
    try:
        active, orders = await _collect_state(exchange)
        active_syms, orphans, all_stops = _print_diagnosis(active, orders)

        if args.cancel_orphans:
            print(f"\n>>> Cancelando {len(orphans)} ÓRFÃOS...")
            n = await _cancel(exchange, orphans)
            print(f"\n>>> Total cancelado: {n}")
        elif args.cancel_all_stops:
            print(f"\n>>> ⚠️  Cancelando TODOS os {len(all_stops)} stops reduce-only "
                  f"(posições ativas ficarão SEM SL até guardian recolocar)...")
            n = await _cancel(exchange, all_stops)
            print(f"\n>>> Total cancelado: {n}")
        elif args.cancel_symbol:
            sym_filter = args.cancel_symbol
            target = [o for o in all_stops if str(o.get("symbol")) == sym_filter]
            print(f"\n>>> Cancelando {len(target)} stops de {sym_filter}...")
            n = await _cancel(exchange, target)
            print(f"\n>>> Total cancelado: {n}")
        elif args.nuke:
            # Mass-cancel por símbolo — usa cancel_all_orders que aciona
            # DELETE /fapi/v1/allOpenOrders?symbol=... na Binance.
            # Pega stops "fantasma" que não aparecem em fetch_open_orders.
            symbols = [
                "BTC/USDT:USDT", "ETH/USDT:USDT",
                "SOL/USDT:USDT", "BNB/USDT:USDT",
                "XRP/USDT:USDT", "DOGE/USDT:USDT",
            ]
            print(f"\n>>> ⚠️  NUKE: mass-cancel em {len(symbols)} símbolos comuns")
            print(">>> Não toca em POSIÇÕES, apenas em ordens pendentes.")
            print(">>> Stops legítimos de posições ativas serão recolocados pelo guardian.")
            print()
            total = 0
            for sym in symbols:
                try:
                    result = await exchange.cancel_all_orders(sym)
                    n = len(result) if isinstance(result, list) else 1
                    print(f"  ✓ {sym:25s} mass-cancel OK ({n} response items)")
                    total += n
                except Exception as exc:
                    msg = str(exc)
                    if "-2011" in msg or "Unknown order" in msg or "no order" in msg.lower():
                        print(f"  · {sym:25s} (sem ordens)")
                    else:
                        print(f"  ✗ {sym:25s} → {exc}")
            print(f"\n>>> Mass-cancel concluído. Itens limpos: {total}")
        else:
            print("\n(dry-run — nada cancelado.)")
            print("Opções de limpeza:")
            print("  --cancel-orphans     seguro, só stops sem posição")
            print("  --cancel-all-stops   cancela todos stops reduce-only visíveis")
            print("  --nuke               mass-cancel por símbolo (limpa fantasmas)")
    finally:
        try:
            await exchange.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
