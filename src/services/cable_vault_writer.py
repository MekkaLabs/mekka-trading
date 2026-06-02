"""
src/services/cable_vault_writer.py
====================================
REV-4 (auditoria 2026-05-29): persistência de insights do Cable no vault
canônico — preenchendo o gap de write-back identificado.

Registra:
- Insights diários do Cable em `60 - Daily/YYYY-MM-DD-cable-insights.md`
- Estado canônico do Cable em `20 - Areas/Trading/Cable Status.md`

Princípios (iguais aos outros vault writers):
- Opt-in via CABLE_VAULT_WRITER_ENABLED
- Throttle 12/hora (Cable já throttle 1/hora — margem extra)
- Fail-silent + atomic write
- Boundary: só escreve em paths permitidos
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
_DAILY_SUBDIR = "60 - Daily"
_TRADING_AREA = "20 - Areas/Trading"

MAX_WRITES_PER_HOUR = int(os.environ.get("CABLE_VAULT_WRITES_PER_HOUR", "12"))


def is_enabled() -> bool:
    return os.environ.get("CABLE_VAULT_WRITER_ENABLED", "false").lower() in (
        "1", "true", "yes", "on"
    )


def get_vault_path() -> Path:
    raw = os.environ.get("MEKKA_VAULT_PATH")
    return Path(raw).expanduser() if raw else _DEFAULT_VAULT


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
        logger.debug(f"[cable_vault_writer] atomic_append failed: {exc}")
        return None


def record_cable_report(report: dict[str, Any]) -> Optional[Path]:
    """
    Persiste um Cable report no vault. Append em arquivo diário.
    """
    if not is_enabled() or not _throttle.allow():
        return None

    vault = get_vault_path()
    if not vault.exists():
        return None
    target = vault / _DAILY_SUBDIR / f"{_today()}-cable-insights.md"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            header = f"""---
title: "Cable Insights — {_today()}"
type: daily-cable
tags: [cable, derivatives, funding-rate, second-brain]
date: {_today()}
auto_generated: true
---

# Cable Insights — {_today()}

> Snapshots periódicos do Cable agent (derivatives intel). Cada bloco é
> um cycle.end report — funding rate 8h rolling + open interest por símbolo.
> Insights textuais ajudam a calibrar thresholds de FUNDING_EXTREME.

"""
            target.write_text(header, encoding="utf-8")
    except OSError as exc:
        logger.debug(f"[cable_vault_writer] header failed: {exc}")
        return None

    # Sanitize — só campos seguros
    snapshot = report.get("snapshot", {}) or {}
    data = snapshot.get("data", {}) or {}
    insights = report.get("insights", []) or []

    blocks = []
    for sym, entry in data.items():
        funding = entry.get("funding", {}) or {}
        oi = entry.get("open_interest", {}) or {}
        mean = funding.get("mean")
        last = funding.get("last")
        oi_val = oi.get("value")
        sign_warn = ""
        if mean is not None:
            mean_pct = float(mean) * 100
            if abs(mean_pct) > 0.05:
                sign_warn = " 🔥 EXTREME" if abs(mean_pct) > 0.1 else " ⚠️ ELEVADO"
        blocks.append(
            f"- **{sym}**: funding 8h mean=`{mean}` last=`{last}`{sign_warn} | "
            f"OI=`{oi_val}`"
        )
    metrics_block = "\n".join(blocks) if blocks else "_(no data)_"

    insight_block = "\n".join(f"  > {i}" for i in insights) if insights else "_(no insights)_"

    block = f"""
### {_now_iso()}

**Métricas por símbolo:**

{metrics_block}

**Insights:**

{insight_block}

"""
    return _atomic_append(target, block)


def upsert_cable_status() -> Optional[Path]:
    """Cria/atualiza o estado canônico do Cable em 20-Areas."""
    if not is_enabled():
        return None
    vault = get_vault_path()
    if not vault.exists():
        return None
    target = vault / _TRADING_AREA / "Cable Status.md"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None

    try:
        from src.agents.cable import get_cable_agent
        agent = get_cable_agent()
        stats = (agent.get_status() if agent else {}) or {}
    except Exception:  # noqa: BLE001
        stats = {}

    content = f"""---
title: "Cable Status"
type: agent-status
tags: [cable, agent, derivatives, second-brain]
updated: {_today()}
auto_generated: true
---

# Cable Status

## Quem é

Cable é o agente especialista em **inteligência de derivativos** —
funding rates 8h rolling, open interest, basis. Read-only, sem ordens.

## Estado atual (snapshot)

```json
{json.dumps(stats, indent=2, default=str)[:1500]}
```

## Integração com Be Water Framework (REV-4)

Cable agora alimenta `analysis.onchain.funding_rate` quando Black Panther
não preencheu. Resultado: RegimeDetector pode detectar
`FUNDING_EXTREME` usando dados Cable; StrategySelector ativa
FundingArbitrageStrategy automaticamente.

Fluxo:
1. Cable fetcha funding via `derivatives_intel.fetch_funding_snapshot`
2. `cable_regime_adapter.enrich_analysis_with_cable()` injeta no analysis
3. RegimeDetector lê `analysis.onchain.funding_rate`
4. StrategySelector aloca pra FundingArbitrageStrategy se regime=extreme

## Observabilidade

- Dashboard: `/api/cable/snapshot`
- Vault daily: `60 - Daily/YYYY-MM-DD-cable-insights.md`
- Status: este arquivo (atualizado a cada upsert)

*Atualizado por `cable_vault_writer.upsert_cable_status()` em {_now_iso()}.*
"""
    try:
        target.write_text(content, encoding="utf-8")
        return target
    except OSError:
        return None


def stats() -> dict[str, Any]:
    return {
        "enabled": is_enabled(),
        "vault_path": str(get_vault_path()),
        "vault_available": get_vault_path().exists(),
        "writes_in_window": len(_throttle._events),
        "max_per_hour": _throttle.max,
    }
