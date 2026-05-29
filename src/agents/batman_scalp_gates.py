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


def _atr_dynamic_cap_bonus(atr_pct: Optional[float]) -> int:
    """SCALP-2 (2026-05-29) — bônus dinâmico de cap baseado em ATR.

    Intuição: quando volatilidade é alta (ATR pct elevado), o sinal por candle
    fica mais forte e há mais oportunidade legítima — manter cap fixo de 6/h
    desperdiça setups. Quando volatilidade está baixa, manter o cap apertado.

    Fórmula: bonus = floor(atr_pct / 0.001) clamped em [0, 6]
      - ATR 0.1% → 0 bonus (cap base 6)
      - ATR 0.3% → 3 bonus (cap 9)
      - ATR 0.6%+ → 6 bonus (cap 12 — saturado)

    Args:
        atr_pct: ATR como fraction (0.001 = 0.1%). None → 0 bonus.

    Returns:
        int >= 0, máximo 6.
    """
    if atr_pct is None:
        return 0
    try:
        bonus = int(float(atr_pct) // 0.001)
    except (TypeError, ValueError):
        return 0
    return max(0, min(6, bonus))


def gate_max_trades_per_hour(
    mode_params: dict[str, Any],
    db_path: Optional[Path] = None,
    atr_pct: Optional[float] = None,
) -> GateResult:
    """
    Gate 3s — bloqueia trade se já atingimos `max_trades_per_hour` na
    última hora.

    SCALP-2 (2026-05-29): cap dinâmico baseado em ATR. Quando ATR está alto,
    o cap aumenta proporcionalmente — não desperdiça setups em mercado
    volátil. `atr_pct` é opcional (None → cap estático).

    Args:
        mode_params: dict de runtime_mode.get_params(). Lê `max_trades_per_hour`.
        db_path: opcional override pra testes (default: data/mekka_trading.db).
        atr_pct: ATR como fraction (ex: 0.003 = 0.3%). None mantém comportamento
            estático original.

    Returns:
        GateResult com gate_id="3s". Allowed=True quando:
          - max_trades_per_hour é None ou 0 (não-scalp)
          - DB inacessível (fail-silent → permite, evita falsos bloqueios)
          - Contagem < cap (cap = base + atr_bonus)
    """
    cap_base = mode_params.get("max_trades_per_hour")
    if not cap_base or cap_base <= 0:
        return GateResult(gate_id="3s", allowed=True, reason="no scalp cap configured")

    # SCALP-2: aplica bônus ATR no cap efetivo
    atr_bonus = _atr_dynamic_cap_bonus(atr_pct)
    cap = cap_base + atr_bonus

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

    meta = {
        "count_last_hour": count,
        "cap": cap,
        "cap_base": cap_base,
        "atr_bonus": atr_bonus,
        "atr_pct": atr_pct,
    }
    if count >= cap:
        return GateResult(
            gate_id="3s",
            allowed=False,
            reason=(
                f"max_trades_per_hour reached ({count}/{cap} em 1h "
                f"— base={cap_base} +atr_bonus={atr_bonus})"
            ),
            metadata=meta,
        )
    return GateResult(
        gate_id="3s",
        allowed=True,
        reason=f"under cap ({count}/{cap} em 1h)",
        metadata=meta,
    )


def gate_max_position_age(
    mode_params: dict[str, Any],
    open_positions: list[dict[str, Any]],
    hard_cap_multiplier: float = 1.5,
) -> GateResult:
    """
    Gate 3t — duas camadas (P1-5 fix da auditoria 2026-05-28):
      - Soft cap (`max_position_age_minutes`): WARNING + metadata, NÃO bloqueia
        novos trades. Cyclops é quem deveria fechar a posição.
      - Hard cap (`cap_min × hard_cap_multiplier`, default 1.5x): BLOQUEIA
        novos trades. Se posição ultrapassou o hard cap, Cyclops falhou e
        sistema está em estado degradado — não abrir novos trades.

    Args:
        mode_params: dict de runtime_mode.get_params().
            Lê `max_position_age_minutes`.
        open_positions: lista de dicts com pelo menos `symbol` e
            `opened_at` (datetime ISO ou datetime) / `timestamp`.
        hard_cap_multiplier: multiplicador do soft cap para definir hard
            cap (1.5 = 50% acima). Pode ser sobrescrito por
            `mode_params["max_position_age_hard_multiplier"]`.

    Returns:
        GateResult com gate_id="3t".
        - allowed=True quando todas posições < soft cap
        - allowed=True (sentinel WARNING) quando alguma entre soft e hard cap
        - allowed=False (BLOCKED) quando alguma >= hard cap
        Metadata.stale_positions e .hard_breach_positions detalham casos.
    """
    cap_min = mode_params.get("max_position_age_minutes")
    if not cap_min or cap_min <= 0:
        return GateResult(gate_id="3t", allowed=True, reason="no scalp age cap")
    hard_cap_multiplier = float(
        mode_params.get("max_position_age_hard_multiplier") or hard_cap_multiplier
    )
    hard_cap_min = cap_min * hard_cap_multiplier

    now = datetime.now(timezone.utc)
    soft_cutoff = now - timedelta(minutes=cap_min)
    hard_cutoff = now - timedelta(minutes=hard_cap_min)
    stale: list[dict[str, Any]] = []
    hard_breach: list[dict[str, Any]] = []

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

        if ts < hard_cutoff:
            # Ultrapassou hard cap — bloqueia
            age_min = (now - ts).total_seconds() / 60.0
            hard_breach.append({
                "symbol": pos.get("symbol", "?"),
                "age_minutes": round(age_min, 1),
                "hard_cap_minutes": round(hard_cap_min, 1),
            })
        elif ts < soft_cutoff:
            # Entre soft e hard — warning
            age_min = (now - ts).total_seconds() / 60.0
            stale.append({
                "symbol": pos.get("symbol", "?"),
                "age_minutes": round(age_min, 1),
                "cap_minutes": cap_min,
            })

    if hard_breach:
        logger.error(
            f"[batman_scalp_gates.3t] HARD CAP BREACH — {len(hard_breach)} "
            f"posição(ões) acima de {hard_cap_min:.0f}min (Cyclops falhou): "
            f"{hard_breach}. Bloqueando novos trades."
        )
        return GateResult(
            gate_id="3t",
            allowed=False,  # P1-5 fix: hard cap bloqueia
            reason=(
                f"{len(hard_breach)} positions exceeded hard cap "
                f"({hard_cap_min:.0f}min) — Cyclops failed to close"
            ),
            metadata={
                "hard_breach_positions": hard_breach,
                "stale_positions": stale,
            },
        )
    if stale:
        logger.warning(
            f"[batman_scalp_gates.3t] {len(stale)} posição(ões) excederam "
            f"soft cap max_position_age_minutes={cap_min}: {stale}"
        )
        return GateResult(
            gate_id="3t",
            allowed=True,  # sentinel — não bloqueia até hard cap
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
