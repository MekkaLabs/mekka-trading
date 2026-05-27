"""
src/services/implementer/cost.py
==================================
Cost tracking + daily cap para o LLMImplementer.

Persistência em ``data/implementer_costs.json``. Não pretende ser
contabilidade fina — apenas gate pra impedir runaway accidental.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from loguru import logger

_REPO = Path(__file__).resolve().parents[3]
_COST_FILE = _REPO / "data" / "implementer_costs.json"

# Caps configuráveis via env
DEFAULT_DAILY_USD_CAP = float(os.environ.get("IMPLEMENTER_DAILY_USD_CAP", "5.00"))
DEFAULT_MONTHLY_USD_CAP = float(os.environ.get("IMPLEMENTER_MONTHLY_USD_CAP", "50.00"))


# Preços estimados (USD por 1M tokens). Atualizar conforme tabela Anthropic.
_PRICE_TABLE = {
    "claude-sonnet-4-5":         {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-6":         {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-7":         {"input": 3.00, "output": 15.00},
    "claude-opus-4-7":           {"input": 15.00, "output": 75.00},
    "claude-haiku-4-5":          {"input": 0.80, "output": 4.00},
    "gpt-4o":                    {"input": 2.50, "output": 10.00},
    "gpt-4o-mini":               {"input": 0.15, "output": 0.60},
    "gpt-5":                     {"input": 2.50, "output": 10.00},
    "gpt-5-mini":                {"input": 0.15, "output": 0.60},
}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _today() -> str:
    return date.today().isoformat()


def _load() -> dict:
    if not _COST_FILE.exists():
        return {"events": [], "totals_by_day": {}, "totals_by_month": {}}
    try:
        return json.loads(_COST_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"events": [], "totals_by_day": {}, "totals_by_month": {}}


def _save(data: dict) -> bool:
    try:
        _COST_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _COST_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, _COST_FILE)
        return True
    except OSError as exc:
        logger.debug(f"[implementer.cost] save failed: {exc}")
        return False


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimativa best-effort baseada em ``_PRICE_TABLE``."""
    prices = _PRICE_TABLE.get(model.lower())
    if not prices:
        # Fallback conservador: Sonnet pricing
        prices = _PRICE_TABLE["claude-sonnet-4-7"]
    in_cost = (input_tokens / 1_000_000) * prices["input"]
    out_cost = (output_tokens / 1_000_000) * prices["output"]
    return round(in_cost + out_cost, 4)


def record_event(
    *,
    rec_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    usd: Optional[float] = None,
) -> dict:
    """Persiste um evento de uso LLM. Retorna totals após o registro."""
    if usd is None:
        usd = estimate_cost_usd(model, input_tokens, output_tokens)
    today = _today()
    month = today[:7]
    data = _load()
    data["events"].append({
        "ts": _now_iso(),
        "rec_id": rec_id,
        "model": model,
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "usd": float(usd),
    })
    data["totals_by_day"][today] = round(
        data["totals_by_day"].get(today, 0.0) + usd, 4
    )
    data["totals_by_month"][month] = round(
        data["totals_by_month"].get(month, 0.0) + usd, 4
    )
    # Manter histórico bounded — últimos 500 events
    data["events"] = data["events"][-500:]
    _save(data)
    return {
        "today_usd": data["totals_by_day"][today],
        "month_usd": data["totals_by_month"][month],
        "this_event_usd": usd,
    }


def is_under_cap() -> tuple[bool, str]:
    """
    Returns (ok, reason). ``ok=False`` quando atingiu cap diário ou mensal.
    """
    today = _today()
    month = today[:7]
    data = _load()
    today_total = data["totals_by_day"].get(today, 0.0)
    month_total = data["totals_by_month"].get(month, 0.0)
    if today_total >= DEFAULT_DAILY_USD_CAP:
        return False, (
            f"daily cap reached: ${today_total:.2f} / ${DEFAULT_DAILY_USD_CAP:.2f}"
        )
    if month_total >= DEFAULT_MONTHLY_USD_CAP:
        return False, (
            f"monthly cap reached: ${month_total:.2f} / ${DEFAULT_MONTHLY_USD_CAP:.2f}"
        )
    return True, "ok"


def summary() -> dict:
    """Snapshot dos totais para o dashboard."""
    today = _today()
    month = today[:7]
    data = _load()
    return {
        "today_usd": data["totals_by_day"].get(today, 0.0),
        "month_usd": data["totals_by_month"].get(month, 0.0),
        "daily_cap_usd": DEFAULT_DAILY_USD_CAP,
        "monthly_cap_usd": DEFAULT_MONTHLY_USD_CAP,
        "total_events": len(data["events"]),
        "last_event_ts": (data["events"][-1]["ts"] if data["events"] else None),
    }
