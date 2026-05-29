"""
src/services/strategy_vault_writer.py
=======================================
Write-back das decisões e evoluções das estratégias no vault canônico.

Registra automaticamente:
- Mudança de regime (RegimeDetector mudou label)
- Estratégias ativas em cada ciclo (StrategySelector)
- Trade outcomes por (strategy × regime)
- Promoção/aposentadoria de estratégias

Princípios (iguais aos outros vault writers):
- Opt-in via flag STRATEGY_VAULT_WRITER_ENABLED
- Throttle 12/hora (regime muda menos frequentemente)
- Fail-silent + atomic write
- Boundary: só escreve em `20 - Areas/Trading/Estratégias/`

Arquivos gerados:
- `20 - Areas/Trading/Estratégias/YYYY-MM-DD-regime-log.md` (regime changes)
- `20 - Areas/Trading/Estratégias/{StrategyName}.md` (perfil da estratégia)
- `60 - Daily/YYYY-MM-DD-strategy-trades.md` (trades agregados por estrat)
"""

from __future__ import annotations

import json
import os
import time
from collections import deque
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger

_DEFAULT_VAULT = Path.home() / "Documents" / "mekka-trading-obsidian"
_TRADING_AREA = "20 - Areas/Trading"
_STRATEGIES_SUBDIR = f"{_TRADING_AREA}/Estratégias"
_DAILY_SUBDIR = "60 - Daily"

MAX_WRITES_PER_HOUR = int(os.environ.get("STRATEGY_VAULT_WRITES_PER_HOUR", "12"))


# ---------------------------------------------------------------------------
# Flags + paths
# ---------------------------------------------------------------------------


def is_enabled() -> bool:
    return os.environ.get("STRATEGY_VAULT_WRITER_ENABLED", "false").lower() in (
        "1", "true", "yes", "on"
    )


def get_vault_path() -> Path:
    raw = os.environ.get("MEKKA_VAULT_PATH")
    return Path(raw).expanduser() if raw else _DEFAULT_VAULT


# ---------------------------------------------------------------------------
# Throttler
# ---------------------------------------------------------------------------


class _Throttle:
    def __init__(self, max_events: int, window_s: float = 3600.0) -> None:
        self.max = max_events
        self.window = window_s
        self._events: deque[float] = deque()

    def allow(self) -> bool:
        now = time.monotonic()
        while self._events and now - self._events[0] > self.window:
            self._events.popleft()
        if len(self._events) >= self.max:
            return False
        self._events.append(now)
        return True


_throttle = _Throttle(MAX_WRITES_PER_HOUR)


def _today() -> str:
    return date.today().isoformat()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_append(target: Path, block: str) -> Optional[Path]:
    try:
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(existing + block, encoding="utf-8")
        os.replace(tmp, target)
        return target
    except OSError as exc:
        logger.debug(f"[strategy_vault_writer] atomic_append failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# 1. Regime changes log
# ---------------------------------------------------------------------------


def record_regime_change(
    symbol: str,
    previous_regime: Optional[str],
    new_regime: str,
    confidence: float,
    features: Optional[dict[str, Any]] = None,
) -> Optional[Path]:
    """
    Registra mudança de regime detectado pelo RegimeDetector.
    Idempotent — só escreve quando o regime de fato mudou.
    """
    if not is_enabled():
        return None
    if previous_regime == new_regime:
        return None
    if not _throttle.allow():
        return None

    vault = get_vault_path()
    if not vault.exists():
        return None
    target = vault / _STRATEGIES_SUBDIR / f"{_today()}-regime-log.md"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            header = f"""---
title: "Regime Log — {_today()}"
type: regime-log
tags: [regime, market-state, strategy, second-brain]
date: {_today()}
auto_generated: true
---

# Regime Log — {_today()}

> Mudanças de regime de mercado detectadas pelo `RegimeDetector` durante
> o dia. Cada bloco abaixo é uma transição (de → para).

"""
            target.write_text(header, encoding="utf-8")
    except OSError as exc:
        logger.debug(f"[strategy_vault_writer] header failed: {exc}")
        return None

    safe_features = {}
    if features:
        for k, v in features.items():
            if isinstance(v, (int, float, str, bool)) or v is None:
                safe_features[k] = v

    block = f"""
## {_now_iso()} — {symbol}: {previous_regime or 'INIT'} → **{new_regime}**

- **Confidence:** {confidence:.2f}
- **Features:**
```json
{json.dumps(safe_features, indent=2, default=str)}
```

"""
    return _atomic_append(target, block)


# ---------------------------------------------------------------------------
# 2. Strategy selection per cycle
# ---------------------------------------------------------------------------


def record_strategy_selection(
    symbol: str,
    regime: str,
    selected_strategies: list[dict[str, Any]],
) -> Optional[Path]:
    """
    Registra quais estratégias foram selecionadas em um ciclo + alocação.
    Append no daily-strategy-decisions.md.
    """
    if not is_enabled():
        return None
    if not selected_strategies:
        return None
    if not _throttle.allow():
        return None

    vault = get_vault_path()
    if not vault.exists():
        return None
    target = vault / _DAILY_SUBDIR / f"{_today()}-strategy-decisions.md"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            header = f"""---
title: "Decisões de Estratégia — {_today()}"
type: strategy-decisions
tags: [strategy, selection, daily, second-brain]
date: {_today()}
auto_generated: true
---

# Decisões de Estratégia — {_today()}

> Estratégias selecionadas pelo `StrategySelector` por ciclo. Cada bloco
> é uma decisão de alocação baseada no regime detectado.

"""
            target.write_text(header, encoding="utf-8")
    except OSError as exc:
        logger.debug(f"[strategy_vault_writer] decisions header failed: {exc}")
        return None

    strats_lines = "\n".join(
        f"  - **{s.get('strategy_name', '?')}** "
        f"(fitness={s.get('fitness_score', 0):.2f}, "
        f"historical={s.get('historical_score', 0):.2f}, "
        f"alloc={s.get('allocated_pct', 0):.1%})"
        for s in selected_strategies[:5]
    )
    block = f"""
### {_now_iso()} — {symbol} | regime: `{regime}`

**Selecionadas ({len(selected_strategies)}):**

{strats_lines}

"""
    return _atomic_append(target, block)


# ---------------------------------------------------------------------------
# 3. Strategy profile (persistent file per strategy)
# ---------------------------------------------------------------------------


def upsert_strategy_profile(
    strategy_name: str,
    description: str,
    regime_fitness: dict[str, float],
    performance: Optional[dict[str, Any]] = None,
) -> Optional[Path]:
    """
    Cria/atualiza o perfil persistente da estratégia.
    Não usa throttle (escrita rara).
    """
    if not is_enabled():
        return None

    vault = get_vault_path()
    if not vault.exists():
        return None
    safe_name = strategy_name.replace("/", "-").replace("\\", "-")
    target = vault / _STRATEGIES_SUBDIR / f"{safe_name}.md"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None

    fitness_lines = "\n".join(
        f"  - `{regime}`: **{score:.2f}**"
        for regime, score in sorted(regime_fitness.items(), key=lambda x: -x[1])
    )

    perf_block = "_(sem trades suficientes ainda)_"
    if performance:
        perf_block = f"""
- **Trades totais:** {performance.get('n_trades', 0)}
- **Win rate:** {performance.get('win_rate', 0):.1%}
- **PnL total:** ${performance.get('total_pnl_usd', 0):+.2f}
- **Sharpe:** {performance.get('sharpe_ratio') or 'n/a'}
- **Max DD:** {performance.get('max_drawdown_pct', 0):.1%}
"""

    content = f"""---
title: "Estratégia — {strategy_name}"
type: strategy-profile
tags: [strategy, profile, second-brain]
strategy: {strategy_name}
updated: {_today()}
auto_generated: true
---

# Estratégia — {strategy_name}

## Descrição

{description or '_(sem descrição)_'}

## Regime Fitness (declarado)

{fitness_lines}

## Performance histórica

{perf_block}

## Notas do operador

> _(adicionar observações manuais aqui — não sobrescrito por auto-update)_

---

*Atualizado por `strategy_vault_writer.upsert_strategy_profile` em {_now_iso()}.*
"""
    try:
        # Preserva "Notas do operador" se existir versão prévia
        if target.exists():
            existing = target.read_text(encoding="utf-8")
            if "## Notas do operador" in existing:
                operator_notes = existing.split("## Notas do operador", 1)[1]
                operator_notes = operator_notes.split("---\n\n*Atualizado", 1)[0]
                content = content.replace(
                    "## Notas do operador\n\n> _(adicionar observações manuais aqui — não sobrescrito por auto-update)_\n\n---",
                    f"## Notas do operador{operator_notes}\n---",
                )
        target.write_text(content, encoding="utf-8")
        return target
    except OSError as exc:
        logger.debug(f"[strategy_vault_writer] profile write failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# 4. Strategy lifecycle events (promotion, retirement)
# ---------------------------------------------------------------------------


def record_lifecycle_event(
    strategy_name: str,
    event_type: str,  # "promoted", "retired", "paused", "resumed"
    reason: str,
    evidence: Optional[dict[str, Any]] = None,
) -> Optional[Path]:
    """
    Registra evento de ciclo de vida da estratégia no daily.
    Importante pra rastreabilidade da evolução do sistema.
    """
    if not is_enabled():
        return None
    if not _throttle.allow():
        return None

    vault = get_vault_path()
    if not vault.exists():
        return None
    target = vault / _STRATEGIES_SUBDIR / "Lifecycle Log.md"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            header = """---
title: "Strategy Lifecycle Log"
type: strategy-lifecycle
tags: [strategy, lifecycle, evolution, second-brain]
auto_generated: true
---

# Strategy Lifecycle Log

> Eventos de promoção, aposentadoria e mudança de status das estratégias
> do Be Water Framework. Toda mudança aparece aqui em ordem cronológica.

"""
            target.write_text(header, encoding="utf-8")
    except OSError:
        return None

    emoji = {
        "promoted": "📈",
        "retired": "🪦",
        "paused": "⏸️",
        "resumed": "▶️",
        "created": "🌱",
    }.get(event_type, "🔄")

    evidence_block = ""
    if evidence:
        evidence_block = "\n```json\n" + json.dumps(
            evidence, indent=2, default=str
        ) + "\n```\n"

    block = f"""
## {_now_iso()} — {emoji} {strategy_name}: {event_type.upper()}

**Razão:** {reason}
{evidence_block}
"""
    return _atomic_append(target, block)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def stats() -> dict[str, Any]:
    return {
        "enabled": is_enabled(),
        "vault_path": str(get_vault_path()),
        "vault_available": get_vault_path().exists(),
        "writes_in_window": len(_throttle._events),
        "max_per_hour": _throttle.max,
    }
