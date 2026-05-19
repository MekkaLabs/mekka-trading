"""
src/backtest/__main__.py
=========================
CLI de Backtesting — Story 223 (Milestone 35: Backtesting Engine).

Uso:
    python -m src.backtest run --symbol BTC --days 30
    python -m src.backtest run --symbol ETH --days 90 --initial-equity 5000
    python -m src.backtest run --symbol BTC --days 30 --seed 42 --output report.md
    python -m src.backtest run --symbol BTC --days 30 --all-signals

Opções:
    --symbol          Símbolo a backtestar (obrigatório). Ex: BTC, ETH, SOL
    --days            Janela histórica em dias (default: 30)
    --initial-equity  Capital inicial em USD (default: 10_000)
    --seed            Semente para reprodutibilidade (default: aleatório)
    --output          Caminho para salvar relatório .md (default: stdout)
    --all-signals     Inclui sinais HOLD/expirados (não apenas LONG/SHORT)
    --quiet           Exibe apenas o relatório, sem logs de progresso
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.backtest",
        description="Mekka Trading — Backtesting Engine CLI",
    )
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Executa backtest para um símbolo")
    run_p.add_argument("--symbol", required=True, help="Ex: BTC, ETH, SOL")
    run_p.add_argument("--days", type=int, default=30, help="Dias históricos (default: 30)")
    run_p.add_argument(
        "--initial-equity", type=float, default=10_000.0, dest="initial_equity",
        help="Capital inicial em USD (default: 10000)",
    )
    run_p.add_argument(
        "--seed", type=int, default=None,
        help="Semente para simulação reproduzível",
    )
    run_p.add_argument(
        "--output", type=str, default=None,
        help="Arquivo .md para salvar relatório (default: stdout)",
    )
    run_p.add_argument(
        "--all-signals", action="store_true", dest="all_signals",
        help="Inclui sinais HOLD (default: apenas LONG/SHORT)",
    )
    run_p.add_argument(
        "--quiet", action="store_true",
        help="Suprime logs de progresso",
    )

    return parser


async def _run(args: argparse.Namespace) -> int:
    """Executa o backtest e imprime/salva o relatório."""
    if not args.quiet:
        print(f"[Mekka Backtest] Iniciando: {args.symbol.upper()} | {args.days} dias | "
              f"equity=${args.initial_equity:,.0f}", file=sys.stderr)

    from src.services.backtest_runner import BacktestRunner

    runner = BacktestRunner(
        initial_equity=args.initial_equity,
        seed=args.seed,
        actionable_only=not args.all_signals,
    )

    try:
        summary = await runner.run(symbol=args.symbol, days=args.days)
    except Exception as exc:
        print(f"[ERRO] Falha no backtest: {exc}", file=sys.stderr)
        return 1

    report = BacktestRunner.render_report(summary)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        if not args.quiet:
            print(f"[Mekka Backtest] Relatório salvo em: {out_path}", file=sys.stderr)
    else:
        print(report)

    if not args.quiet:
        m = summary.metrics
        print(
            f"\n[Mekka Backtest] Concluído — "
            f"WR={m.win_rate:.1f}% | PF={m.profit_factor:.2f} | "
            f"Sharpe={m.sharpe_ratio:.2f} | MaxDD={m.max_drawdown_pct:.2f}% | "
            f"Retorno={summary.total_return_pct:+.2f}%",
            file=sys.stderr,
        )

    return 0


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "run":
        exit_code = asyncio.run(_run(args))
        sys.exit(exit_code)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
