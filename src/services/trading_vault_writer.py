"""
src/services/trading_vault_writer.py
======================================
Write-back dos agentes de trading (Mentor, Cyclops, Vision) no vault canônico.

Cada agente tem sua própria sub-API (opt-in), sua flag de ambiente, seu
arquivo destino:

  Mentor    → `20 - Areas/Trading/Calibrações/YYYY-MM-DD-mentor.md`
              quando `confidence >= 0.7` AND `can_auto_apply=True`
  Cyclops   → `60 - Daily/YYYY-MM-DD-trades.md`
              quando `close_position(pnl_usd != None)`
  Vision    → `20 - Areas/Trading/Decisões/YYYY-MM-DD-vision-{symbol}.md`
              quando confidence >= 0.8 E uma decisão crítica (BUY/SELL forte)

Princípios (iguais ao prometheus_vault_writer):
  - Opt-in via flag dedicada por agente
  - Throttle 10/hora por agente
  - Fail-silent
  - Boundary: só escreve em `60 - Daily/` ou `20 - Areas/Trading/...`
  - Sem secrets
"""

from __future__ import annotations

import json
import os
import time
from collections import deque
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

_DEFAULT_VAULT_PATH = Path.home() / "Documents" / "mekka-trading-obsidian"
_DAILY_SUBDIR = "60 - Daily"
_TRADING_AREA = "20 - Areas/Trading"
_MENTOR_SUBDIR = f"{_TRADING_AREA}/Calibrações"
_VISION_SUBDIR = f"{_TRADING_AREA}/Decisões"

_ALLOWED_PREFIXES = (_DAILY_SUBDIR, _TRADING_AREA)


# ---------------------------------------------------------------------------
# Flags + paths
# ---------------------------------------------------------------------------


def _flag(name: str) -> bool:
    return os.environ.get(name, "false").lower() in ("1", "true", "yes", "on")


def is_mentor_enabled() -> bool:
    return _flag("MENTOR_VAULT_WRITER_ENABLED")


def is_cyclops_enabled() -> bool:
    return _flag("CYCLOPS_VAULT_WRITER_ENABLED")


def is_vision_enabled() -> bool:
    return _flag("VISION_VAULT_WRITER_ENABLED")


def get_vault_path() -> Path:
    raw = os.environ.get("MEKKA_VAULT_PATH")
    return Path(raw).expanduser() if raw else _DEFAULT_VAULT_PATH


# ---------------------------------------------------------------------------
# Throttle por agente
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


_mentor_throttle = _Throttle(int(os.environ.get("MENTOR_VAULT_WRITES_PER_HOUR", "10")))
_cyclops_throttle = _Throttle(int(os.environ.get("CYCLOPS_VAULT_WRITES_PER_HOUR", "20")))
_vision_throttle = _Throttle(int(os.environ.get("VISION_VAULT_WRITES_PER_HOUR", "20")))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _today() -> str:
    return date.today().isoformat()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _is_within_allowed(target: Path, vault: Path) -> bool:
    try:
        rel = target.relative_to(vault).as_posix()
    except ValueError:
        return False
    return any(rel.startswith(p + "/") or rel == p for p in _ALLOWED_PREFIXES)


def _atomic_append(target: Path, block: str) -> Optional[Path]:
    try:
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(existing + block, encoding="utf-8")
        os.replace(tmp, target)
        return target
    except OSError as exc:
        logger.debug(f"[trading_vault_writer] atomic_append failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# Mentor — write calibration suggestions
# ---------------------------------------------------------------------------


def record_mentor_suggestion(suggestion: dict[str, Any]) -> Optional[Path]:
    """
    Escreve uma sugestão do Mentor (Charles Xavier) que passou pelos critérios:
      - confidence >= 0.7
      - can_auto_apply == True

    Append em `20 - Areas/Trading/Calibrações/YYYY-MM-DD-mentor.md`.
    """
    if not is_mentor_enabled():
        return None
    if not _mentor_throttle.allow():
        return None
    confidence = float(suggestion.get("confidence") or 0.0)
    can_auto = bool(suggestion.get("can_auto_apply", False))
    if confidence < 0.7 or not can_auto:
        return None

    vault = get_vault_path()
    if not vault.exists():
        return None
    target_dir = vault / _MENTOR_SUBDIR
    target = target_dir / f"{_today()}-mentor.md"
    if not _is_within_allowed(target, vault):
        return None
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            header = f"""---
title: "Calibrações do Mentor — {_today()}"
type: mentor-calibrations
tags: [mentor, calibration, trading, second-brain]
date: {_today()}
auto_generated: true
---

# Calibrações do Mentor (Charles Xavier) — {_today()}

> Sugestões de ajuste de parâmetros geradas automaticamente pelo Mentor
> quando atingem `confidence >= 0.7` e `can_auto_apply=True`.
> Política: revisar antes de aplicar; este é um diário, não comando.

"""
            target.write_text(header, encoding="utf-8")
    except OSError as exc:
        logger.debug(f"[mentor_writer] header failed: {exc}")
        return None

    # Sanitiza — nada de secret keys
    safe_keys = {"target", "current_value", "suggested_value", "reason",
                 "confidence", "n_samples", "metric", "symbol", "scope"}
    safe = {k: v for k, v in suggestion.items() if k in safe_keys}
    block = f"""
### {_now_iso()} — sugestão `{safe.get('target', '?')}`

- **Métrica:** `{safe.get('metric', '?')}` · **Escopo:** `{safe.get('scope', '?')}`
- **Atual:** `{safe.get('current_value', '?')}` → **Sugerido:** `{safe.get('suggested_value', '?')}`
- **Confiança:** {safe.get('confidence', 0):.2f} · **Amostras:** {safe.get('n_samples', '?')}
- **Razão:** {safe.get('reason', '_(sem razão)_')}

"""
    return _atomic_append(target, block)


# ---------------------------------------------------------------------------
# Cyclops — write trade outcomes
# ---------------------------------------------------------------------------


def record_cyclops_close(close_event: dict[str, Any]) -> Optional[Path]:
    """
    Registra resultado de close_position do Cyclops (Scott Summers).
    Append em `60 - Daily/YYYY-MM-DD-trades.md`.

    Espera: ``{symbol, side, pnl_usd, holding_hours, reason}``.
    """
    if not is_cyclops_enabled():
        return None
    if not _cyclops_throttle.allow():
        return None
    pnl = close_event.get("pnl_usd")
    if pnl is None:
        return None

    vault = get_vault_path()
    if not vault.exists():
        return None
    target = vault / _DAILY_SUBDIR / f"{_today()}-trades.md"
    if not _is_within_allowed(target, vault):
        return None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            header = f"""---
title: "Trades fechados — {_today()}"
type: daily-trades
tags: [trades, cyclops, daily, second-brain]
date: {_today()}
auto_generated: true
---

# Trades fechados — {_today()}

> Append automático pelo Cyclops quando um `close_position` retorna
> `pnl_usd != None`. Cada linha é um trade. Vault-only, não volta ao repo.

| Hora | Symbol | Side | PnL (USD) | Hold (h) | Reason |
|---|---|---|---|---|---|
"""
            target.write_text(header, encoding="utf-8")
    except OSError as exc:
        logger.debug(f"[cyclops_writer] header failed: {exc}")
        return None

    symbol = str(close_event.get("symbol", "?"))[:10]
    side = str(close_event.get("side", "?"))[:6]
    pnl_str = f"{float(pnl):+.2f}" if pnl is not None else "?"
    hold = close_event.get("holding_hours")
    hold_str = f"{float(hold):.1f}" if hold is not None else "?"
    reason = str(close_event.get("reason", ""))[:80].replace("|", "/")
    line = (
        f"| {datetime.now().strftime('%H:%M:%S')} | {symbol} | {side} | "
        f"{pnl_str} | {hold_str} | {reason} |\n"
    )
    return _atomic_append(target, line)


# ---------------------------------------------------------------------------
# Vision — write high-conviction decisions
# ---------------------------------------------------------------------------


def record_vision_decision(decision: dict[str, Any]) -> Optional[Path]:
    """
    Registra uma decisão do Vision com `confidence >= 0.8`.
    Cria/append em `20 - Areas/Trading/Decisões/YYYY-MM-DD-vision-{SYMBOL}.md`.
    """
    if not is_vision_enabled():
        return None
    if not _vision_throttle.allow():
        return None
    confidence = float(decision.get("confidence") or 0.0)
    action = str(decision.get("action") or "").upper()
    if confidence < 0.8 or action not in ("BUY", "SELL", "LONG", "SHORT"):
        return None

    symbol = str(decision.get("symbol", "")).upper()[:10] or "GENERAL"
    vault = get_vault_path()
    if not vault.exists():
        return None
    target_dir = vault / _VISION_SUBDIR
    target = target_dir / f"{_today()}-vision-{symbol}.md"
    if not _is_within_allowed(target, vault):
        return None
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            header = f"""---
title: "Decisões do Vision — {symbol} — {_today()}"
type: vision-decisions
tags: [vision, decisions, trading, {symbol.lower()}, second-brain]
date: {_today()}
symbol: {symbol}
auto_generated: true
---

# Decisões do Vision — {symbol} — {_today()}

> Append automático pelo Vision para decisões com `confidence >= 0.8`.
> Cada bloco abaixo é uma decisão crítica do dia.

"""
            target.write_text(header, encoding="utf-8")
    except OSError as exc:
        logger.debug(f"[vision_writer] header failed: {exc}")
        return None

    rationale = str(decision.get("rationale", ""))[:1500]
    block = f"""
## {_now_iso()} — {action} {symbol}

- **Confiança:** {confidence:.2f}
- **Preço:** `{decision.get('price', '?')}` · **Size:** `{decision.get('size_pct', '?')}`
- **Cycle:** `{decision.get('cycle_id', '?')}`

### Rationale

{rationale or '_(sem rationale)_'}

---
"""
    return _atomic_append(target, block)


# ---------------------------------------------------------------------------
# Stats — agregado pro dashboard
# ---------------------------------------------------------------------------


def stats() -> dict[str, Any]:
    return {
        "mentor": {
            "enabled": is_mentor_enabled(),
            "writes_window": len(_mentor_throttle._events),
            "cap_per_hour": _mentor_throttle.max,
        },
        "cyclops": {
            "enabled": is_cyclops_enabled(),
            "writes_window": len(_cyclops_throttle._events),
            "cap_per_hour": _cyclops_throttle.max,
        },
        "vision": {
            "enabled": is_vision_enabled(),
            "writes_window": len(_vision_throttle._events),
            "cap_per_hour": _vision_throttle.max,
        },
        "vault_path": str(get_vault_path()),
        "vault_available": get_vault_path().exists(),
    }
