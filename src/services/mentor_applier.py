"""
src/services/mentor_applier.py
===============================
INV-14 (2026-05-30) — Fecha o último loop de aprendizado: aplica
sugestões high-confidence do Mentor em runtime overrides automaticamente.

Loop completo final:
  1. Vision/Batman/IronMan operam com settings + overrides
  2. Trades fecham, Cyclops/janitor resolvem outcomes
  3. Mentor.run() analisa win-rate/rejeições/drawdown → ParameterSuggestion
  4. Mentor enfileira high_conf+can_auto_apply em data/improvement_inbox.json
  5. mentor_applier (este módulo) lê inbox, aplica em data/mentor_overrides.json
  6. Vision/Batman lêem mentor_overrides na próxima rodada → fechamento

Safety GATES (triplo):
  - opt-in via MENTOR_AUTO_APPLY_ENABLED=true (env, default OFF)
  - sugestão precisa can_auto_apply=True E confidence >= MIN_CONFIDENCE
  - direction='tighten' SEMPRE OK, direction='loosen' BLOQUEADO (nunca
    afrouxa risco sem operador)
  - bounded: cada parâmetro tem cap absoluto (min/max) hardcoded aqui

Idempotência: re-rodar o mesmo inbox não duplica overrides.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger

_REPO = Path(__file__).resolve().parents[2]
_INBOX_PATH = _REPO / "data" / "improvement_inbox.json"
_OVERRIDES_PATH = _REPO / "data" / "mentor_overrides.json"
_DB_PATH = _REPO / "data" / "mekka_trading.db"


# ---------------------------------------------------------------------------
# Safety: bounds e parâmetros permitidos pra auto-apply
# ---------------------------------------------------------------------------

# Apenas estes parâmetros podem ser auto-aplicados. Lista pequena +
# conservadora — em caso de dúvida, NÃO auto-aplica.
_ALLOWED_PARAMS: dict[str, dict[str, float]] = {
    "min_confidence": {"min": 0.50, "max": 0.95},
    "min_confidence_threshold": {"min": 0.50, "max": 0.95},
    "max_daily_drawdown_pct": {"min": 0.02, "max": 0.20},
    "max_position_size_pct": {"min": 0.005, "max": 0.05},
    "max_leverage": {"min": 1, "max": 10},
    "max_trades_per_hour": {"min": 1, "max": 12},
}

MIN_CONFIDENCE = 0.7


def is_enabled() -> bool:
    """Opt-in via env. Default OFF — operador escolhe quando ativar."""
    return os.environ.get("MENTOR_AUTO_APPLY_ENABLED", "false").lower() in (
        "1", "true", "yes", "on"
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _save_json(path: Path, data: Any) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True, default=str),
                       encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError as exc:
        logger.warning(f"[mentor_applier] save failed: {exc}")
        return False


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _emit_audit(applied: list[dict], skipped: list[dict]) -> None:
    """Emite MENTOR_APPLIED no audit_log. Fail-silent."""
    if not (applied or skipped):
        return
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        payload = json.dumps({
            "applied": applied,
            "skipped": skipped,
        }, default=str)
        conn.execute(
            "INSERT INTO audit_log (timestamp, agent, event, severity, message, payload) "
            "VALUES (datetime('now'), ?, ?, ?, ?, ?)",
            (
                "MentorApplier",
                "MENTOR_APPLIED",
                "INFO" if applied else "DEBUG",
                f"applied {len(applied)} settings ({len(skipped)} skipped)",
                payload,
            ),
        )
        conn.commit()
        conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[mentor_applier] audit emit failed: {exc}")


def get_overrides() -> dict[str, Any]:
    """Retorna overrides atuais (lê do disco). Default {} se não existe."""
    data = _load_json(_OVERRIDES_PATH, {})
    if not isinstance(data, dict):
        return {}
    return data


def get_override(param: str, default: Any = None) -> Any:
    """Conveniência: pega override de um parâmetro específico.

    Agentes consomem via:
        from src.services.mentor_applier import get_override
        threshold = get_override("min_confidence", settings.min_confidence)
    """
    overrides = get_overrides()
    entry = overrides.get(param)
    if entry is None:
        return default
    # entry é {"value": ..., "applied_at": "...", ...}
    if isinstance(entry, dict):
        return entry.get("value", default)
    return entry


def apply_inbox(dry_run: bool = False) -> dict[str, Any]:
    """
    Lê o inbox, filtra high-conf can_auto_apply, e grava em overrides.json.

    Args:
        dry_run: se True, não escreve. Retorna o que faria.

    Returns:
        dict {applied: [...], skipped: [...], dry_run, ts}
    """
    result: dict[str, Any] = {
        "applied": [],
        "skipped": [],
        "dry_run": dry_run,
        "ts": _now_iso(),
        "enabled": is_enabled(),
    }

    if not is_enabled() and not dry_run:
        result["skipped"].append({
            "reason": "disabled",
            "hint": "set MENTOR_AUTO_APPLY_ENABLED=true to enable",
        })
        return result

    inbox = _load_json(_INBOX_PATH, [])
    if not isinstance(inbox, list) or not inbox:
        return result

    current_overrides = get_overrides() if not dry_run else {}
    new_overrides = dict(current_overrides)
    processed_ids: set[str] = set()

    for entry in inbox:
        if not isinstance(entry, dict):
            continue
        if entry.get("source") != "mentor":
            continue
        param = (entry.get("parameter_name") or "").strip()
        suggested = entry.get("suggested_value")
        confidence = float(entry.get("confidence", 0.0) or 0.0)
        can_auto = bool(entry.get("can_auto_apply", False))
        direction = (entry.get("direction") or "").lower()

        # Idempotente: skip se já foi aplicado com o mesmo valor
        entry_id = f"{param}={suggested}"
        if entry_id in processed_ids:
            continue
        processed_ids.add(entry_id)

        # GATE 1: parâmetro permitido?
        if param not in _ALLOWED_PARAMS:
            result["skipped"].append({
                "param": param, "reason": "param_not_allowed_for_auto_apply",
            })
            continue
        # GATE 2: confidence + can_auto_apply
        if not can_auto:
            result["skipped"].append({
                "param": param, "reason": "can_auto_apply=False",
            })
            continue
        if confidence < MIN_CONFIDENCE:
            result["skipped"].append({
                "param": param, "reason": f"confidence_below_{MIN_CONFIDENCE}",
                "got": confidence,
            })
            continue
        # GATE 3: direction. 'loosen' SEMPRE bloqueado (nunca afrouxa risco
        # automaticamente).
        if direction == "loosen":
            result["skipped"].append({
                "param": param, "reason": "loosen_requires_manual_approval",
            })
            continue
        # Bounded
        try:
            value = float(suggested)
        except (TypeError, ValueError):
            result["skipped"].append({
                "param": param, "reason": "invalid_suggested_value",
                "got": suggested,
            })
            continue
        bounds = _ALLOWED_PARAMS[param]
        clamped = _clamp(value, bounds["min"], bounds["max"])
        if clamped != value:
            result["skipped"].append({
                "param": param, "reason": "out_of_bounds",
                "got": value, "bounds": bounds,
            })
            continue

        # Idempotência: skip se override existente é igual
        existing = current_overrides.get(param)
        existing_value = (
            existing.get("value") if isinstance(existing, dict) else existing
        )
        if existing_value == clamped:
            result["skipped"].append({
                "param": param, "reason": "already_applied",
                "value": clamped,
            })
            continue

        # APPLY
        new_overrides[param] = {
            "value": clamped,
            "applied_at": _now_iso(),
            "applied_by": "mentor_applier",
            "source_confidence": confidence,
            "direction": direction,
            "rationale": entry.get("reason") or entry.get("rationale", ""),
            "previous_value": existing_value,
        }
        result["applied"].append({
            "param": param, "value": clamped,
            "confidence": confidence,
            "direction": direction,
            "previous": existing_value,
        })

    if not dry_run and result["applied"]:
        _save_json(_OVERRIDES_PATH, new_overrides)

    if not dry_run:
        _emit_audit(result["applied"], result["skipped"])

    return result


def clear_overrides() -> dict[str, Any]:
    """Manual reset — apaga todos os overrides do Mentor. Audit-trail
    via MENTOR_OVERRIDES_CLEARED event."""
    current = get_overrides()
    if not current:
        return {"cleared": 0, "ts": _now_iso()}
    _save_json(_OVERRIDES_PATH, {})
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.execute(
            "INSERT INTO audit_log (timestamp, agent, event, severity, message, payload) "
            "VALUES (datetime('now'), ?, ?, ?, ?, ?)",
            (
                "MentorApplier",
                "MENTOR_OVERRIDES_CLEARED",
                "WARNING",
                f"cleared {len(current)} overrides manually",
                json.dumps(current, default=str),
            ),
        )
        conn.commit()
        conn.close()
    except Exception:  # noqa: BLE001
        pass
    return {"cleared": len(current), "ts": _now_iso()}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Mentor auto-applier")
    p.add_argument("--apply", action="store_true", help="Apply (default dry-run)")
    p.add_argument("--clear", action="store_true", help="Clear all overrides")
    p.add_argument("--status", action="store_true", help="Show current overrides")
    args = p.parse_args()

    if args.clear:
        r = clear_overrides()
        print(json.dumps(r, indent=2, default=str))
        return 0
    if args.status:
        print(json.dumps({
            "enabled": is_enabled(),
            "overrides": get_overrides(),
        }, indent=2, default=str))
        return 0

    result = apply_inbox(dry_run=not args.apply)
    print(json.dumps(result, indent=2, default=str))
    return 0 if not result.get("error") else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
