"""
src/agents/batman_scalp_gates.py
==================================
Scalp-specific gates para Batman. Módulo isolado e read-only — Batman
chama estas funções quando modo ativo é scalp.

Gates novos (numerados 3s, 3t para continuar a sequência 3b-3r de Batman):

  - **3s: gate_max_trades_per_hour** — limita trades/hora baseado no
    preset `max_trades_per_hour`. Defesa contra hyperactivity em scalp.

  - **3t: gate_max_position_age** — sentinel para Cyclops time-stop
    (Cyclops fecha, mas Batman alerta se uma posição já passou da idade
    máxima — útil em logs / dashboard).

Hard rules:
  - Funções puras (recebem dados, retornam GateResult).
  - Fail-silent: erro de leitura DB → ALLOW (não bloqueia trade por
    falha de infraestrutura).
  - Read-only: nenhuma escrita em DB ou exchange.
  - Sem efeito em outros modos: se `max_trades_per_hour` é None, ALLOW
    direto.

Hook em Batman (REQUER approval do operador para edit em arquivo protegido):
    if mode == "scalp":
        from src.agents.batman_scalp_gates import gate_max_trades_per_hour
        gate_result = gate_max_trades_per_hour(...)
        if not gate_result.allowed:
            return RejectResult(reason=gate_result.reason)
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("mekka.batman_scalp_gates")

_REPO = Path(__file__).resolve().parents[2]
_DB_PATH = _REPO / "data" / "mekka_trading.db"


@dataclass
class GateResult:
    """Resultado de um gate scalp. Compatível com pattern Batman."""

    gate_id: str            # "3s", "3t"
    allowed: bool
    reason: str = ""
    metadata: dict[str, Any] = None  # extras pro audit log

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


def gate_max_trades_per_hour(
    mode_params: dict[str, Any],
    db_path: Optional[Path] = None,
) -> GateResult:
    """
    Gate 3s — bloqueia trade se já atingimos `max_trades_per_hour` na
    última hora.

    Args:
        mode_params: dict de runtime_mode.get_params(). Lê `max_trades_per_hour`.
        db_path: opcional override pra testes (default: data/mekka_trading.db).

    Returns:
        GateResult com gate_id="3s". Allowed=True quando:
          - max_trades_per_hour é None ou 0 (não-scalp)
          - DB inacessível (fail-silent → permite, evita falsos bloqueios)
          - Contagem < max
    """
    cap = mode_params.get("max_trades_per_hour")
    if not cap or cap <= 0:
        return GateResult(gate_id="3s", allowed=True, reason="no scalp cap configured")

    path = db_path or _DB_PATH
    if not path.exists():
        logger.debug(f"[batman_scalp_gates.3s] DB ausente em {path} — ALLOW")
        return GateResult(gate_id="3s", allowed=True, reason="db unavailable")

    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        conn = sqlite3.connect(str(path))
        try:
            cur = conn.execute(
                "SELECT COUNT(*) FROM trades "
                "WHERE timestamp >= ? AND status NOT IN ('ERROR', 'REJECTED')",
                (cutoff,),
            )
            count = int(cur.fetchone()[0] or 0)
        finally:
            conn.close()
    except sqlite3.Error as exc:
        logger.warning(f"[batman_scalp_gates.3s] sqlite error: {exc} — ALLOW")
        return GateResult(gate_id="3s", allowed=True, reason=f"sqlite err: {exc}")

    if count >= cap:
        return GateResult(
            gate_id="3s",
            allowed=False,
            reason=f"max_trades_per_hour reached ({count}/{cap} em 1h)",
            metadata={"count_last_hour": count, "cap": cap},
        )
    return GateResult(
        gate_id="3s",
        allowed=True,
        reason=f"under cap ({count}/{cap} em 1h)",
        metadata={"count_last_hour": count, "cap": cap},
    )


def gate_max_position_age(
    mode_params: dict[str, Any],
    open_positions: list[dict[str, Any]],
) -> GateResult:
    """
    Gate 3t — sentinel: emite WARNING (não bloqueia) se alguma posição
    aberta ultrapassou `max_position_age_minutes`. Cyclops é quem fecha
    a posição; esse gate só registra que algo escapou do time-stop.

    Args:
        mode_params: dict de runtime_mode.get_params().
            Lê `max_position_age_minutes`.
        open_positions: lista de dicts com pelo menos chaves
            `symbol` e `opened_at` (datetime ISO ou datetime).

    Returns:
        GateResult com gate_id="3t". Allowed sempre True (sentinel não bloqueia).
        Metadata.stale_positions lista posições que excederam o limite.
    """
    cap_min = mode_params.get("max_position_age_minutes")
    if not cap_min or cap_min <= 0:
        return GateResult(gate_id="3t", allowed=True, reason="no scalp age cap")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=cap_min)
    stale: list[dict[str, Any]] = []

    for pos in open_positions:
        ts_raw = pos.get("opened_at") or pos.get("timestamp")
        if ts_raw is None:
            continue
        try:
            if isinstance(ts_raw, str):
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            else:
                ts = ts_raw
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError) as exc:
            logger.debug(f"[batman_scalp_gates.3t] ts parse fail: {exc}")
            continue

        if ts < cutoff:
            age_min = (now - ts).total_seconds() / 60.0
            stale.append({
                "symbol": pos.get("symbol", "?"),
                "age_minutes": round(age_min, 1),
                "cap_minutes": cap_min,
            })

    if stale:
        logger.warning(
            f"[batman_scalp_gates.3t] {len(stale)} posição(ões) excederam "
            f"max_position_age_minutes={cap_min}: {stale}"
        )
        return GateResult(
            gate_id="3t",
            allowed=True,  # sentinel — não bloqueia
            reason=f"{len(stale)} stale positions (Cyclops should close)",
            metadata={"stale_positions": stale},
        )
    return GateResult(
        gate_id="3t",
        allowed=True,
        reason=f"all positions under {cap_min}min",
    )


def evaluate_all_scalp_gates(
    mode_params: dict[str, Any],
    open_positions: Optional[list[dict[str, Any]]] = None,
    db_path: Optional[Path] = None,
) -> list[GateResult]:
    """
    Helper: roda todos os scalp gates e retorna a lista de resultados.
    Útil em Batman para iteração simples + audit log.
    """
    results: list[GateResult] = []
    results.append(gate_max_trades_per_hour(mode_params, db_path=db_path))
    results.append(gate_max_position_age(mode_params, open_positions or []))
    return results
