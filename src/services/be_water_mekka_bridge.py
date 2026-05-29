"""
src/services/be_water_mekka_bridge.py
=======================================
Bridge entre Be Water Framework e o Mekka cycle (NickFury → ProfessorX).

Permite que o NickFury cycle EXISTENTE consulte o orchestrator
opcionalmente e injete a decisão de regime + estratégias selecionadas
no MarketAnalysis antes de chamar Vision.

Não substitui o flow atual (Superman/DoctorStrange/etc) — APENAS adiciona
contexto. Vision pode usar ou ignorar.

Feature flag: BE_WATER_FRAMEWORK_ENABLED (default false).

Princípios:
- Opt-in via flag
- Fail-silent (NickFury cycle NUNCA quebra)
- Read-only no MarketAnalysis
- Adiciona dois campos novos via metadata:
    analysis.bewater_regime: {regime, confidence, features}
    analysis.bewater_signals: [{strategy_name, action, confidence, ...}]
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger


def is_enabled() -> bool:
    """Feature flag. Default off — adoção incremental."""
    return os.environ.get("BE_WATER_FRAMEWORK_ENABLED", "false").lower() in (
        "1", "true", "yes", "on"
    )


async def enrich_analysis_with_bewater(
    symbol: str,
    analysis: Any,
    equity_usd: float,
    open_positions_count: int = 0,
) -> dict[str, Any]:
    """
    Chama o Be Water orchestrator e devolve dict com regime + signals
    pra anexar ao MarketAnalysis ou audit log.

    Fail-silent: erros retornam dict vazio. Mekka cycle pode ignorar.

    Returns:
        {} quando desabilitado/erro, senão:
        {
          "regime": {...},
          "signals": [{...}],
          "top_signal": {...} | None,
          "flat": bool,
          "rationale": str,
        }
    """
    if not is_enabled():
        return {}

    try:
        from src.services.be_water_orchestrator import decide
        decision = await decide(
            symbol=symbol,
            analysis=analysis,
            equity_usd=equity_usd,
            open_positions_count=open_positions_count,
        )
        result = {
            "regime": decision.regime.to_dict(),
            "signals": [s.to_dict() for s in decision.signals],
            "top_signal": decision.top_signal().to_dict() if decision.top_signal() else None,
            "flat": decision.flat,
            "rationale": decision.rationale,
            "metadata": decision.metadata,
            "enriched_at": datetime.now(timezone.utc).isoformat(),
        }

        # Vault write-back (regime changes + selections)
        try:
            from src.services import strategy_vault_writer as svw
            # Regime change tracking happens at NickFury level (precisa state)
            # Aqui só registra a seleção
            if decision.signals:
                selected = [
                    {
                        "strategy_name": s.strategy_name,
                        "fitness_score": s.metadata.get("fitness_score", 0),
                        "historical_score": s.metadata.get("historical_score", 0),
                        "allocated_pct": s.metadata.get("allocated_pct", 0),
                    }
                    for s in decision.signals
                ]
                svw.record_strategy_selection(
                    symbol=symbol,
                    regime=decision.regime.regime.value,
                    selected_strategies=selected,
                )
        except Exception as exc_vault:  # noqa: BLE001
            logger.debug(f"[be_water_bridge] vault write no-op: {exc_vault}")

        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[be_water_bridge] enrich failed: {exc}")
        return {}


# Module-level state: last_regime per symbol (pra detectar transições)
_last_regime: dict[str, str] = {}


async def detect_and_log_regime_change(
    symbol: str, analysis: Any,
) -> Optional[dict[str, Any]]:
    """
    Detecta regime e, se mudou desde a última detecção pra esse symbol,
    log mudança no vault. Sem state externo (persiste em memória).

    Returns:
        {"changed": bool, "from": str|None, "to": str, "confidence": float}
        ou None em erro.
    """
    if not is_enabled():
        return None
    try:
        from src.services.regime_detector import detect_regime
        new = detect_regime(analysis)
        last = _last_regime.get(symbol)
        new_label = new.regime.value
        changed = last != new_label
        if changed:
            try:
                from src.services import strategy_vault_writer as svw
                svw.record_regime_change(
                    symbol=symbol,
                    previous_regime=last,
                    new_regime=new_label,
                    confidence=new.confidence,
                    features=new.features,
                )
            except Exception:  # noqa: BLE001
                pass
            _last_regime[symbol] = new_label
        return {
            "changed": changed,
            "from": last,
            "to": new_label,
            "confidence": new.confidence,
        }
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[be_water_bridge] regime change check failed: {exc}")
        return None
