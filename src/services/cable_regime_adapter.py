"""
src/services/cable_regime_adapter.py
======================================
Adapter Cable → Be Water Framework (REV-4 da auditoria 2026-05-29).

Antes: Cable produzia funding_rate/OI mas ninguém consumia. Black Panther
(Layer 1) também produzia funding_rate sem coordenação. Duplicação +
isolamento.

Agora: Adapter conecta Cable como SOURCE adicional de features pro
RegimeDetector E pro FundingArbitrageStrategy. Cable já tem 8h rolling
mean (mais robusto que ponto único do Black Panther).

Fluxo:
1. Cable já fetcha funding rate via derivatives_intel.fetch_funding_snapshot
2. Cable_regime_adapter.enrich_analysis_with_cable() pega último snapshot
   e injeta em analysis.onchain.funding_rate (se ausente ou mais antigo)
3. RegimeDetector detecta FUNDING_EXTREME quando |mean| > 0.0005
4. StrategySelector ativa FundingArbitrageStrategy automaticamente

Princípios:
- FAIL-SILENT: erros não afetam pipeline existente
- OPT-IN: gated por flag CABLE_REGIME_ADAPTER_ENABLED (default True quando
  Cable está enabled)
- READ-ONLY do Cable snapshot (não muta)
- NÃO sobrescreve funding_rate explicitamente preenchido por outro source
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger


def is_enabled() -> bool:
    """Default ativa se Cable estiver enabled. Pode desligar via flag."""
    cable_enabled = os.environ.get("CABLE_AGENT_ENABLED", "false").lower() in (
        "1", "true", "yes", "on"
    )
    if not cable_enabled:
        return False
    flag = os.environ.get("CABLE_REGIME_ADAPTER_ENABLED", "true").lower()
    return flag in ("1", "true", "yes", "on")


async def get_cable_snapshot() -> Optional[dict[str, Any]]:
    """
    Retorna último snapshot do Cable agent. None se Cable indisponível.
    Não força refetch — usa o que está em memória do agent.
    """
    try:
        from src.agents.cable import get_cable_agent
        agent = get_cable_agent()
        if agent is None:
            return None
        # Get reports buffer (last item is most recent)
        reports = list(getattr(agent, "_reports", []))
        if not reports:
            return None
        return reports[-1]
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[cable_regime_adapter] snapshot fetch failed: {exc}")
        return None


def extract_funding_for_symbol(
    cable_report: dict[str, Any], symbol: str,
) -> Optional[float]:
    """
    Extrai funding_mean do report Cable para o symbol dado.

    Cable usa formato BTCUSDT, sistema Mekka usa BTC.
    Tenta os 2 formatos.
    """
    snapshot = cable_report.get("snapshot") or cable_report
    data = snapshot.get("data") or {}
    if not data:
        return None

    # Tenta BTCUSDT primeiro (Cable native), depois BTC
    candidates = [f"{symbol}USDT", symbol]
    for cand in candidates:
        entry = data.get(cand)
        if not entry:
            continue
        funding = entry.get("funding") or {}
        mean = funding.get("mean")
        if mean is not None:
            try:
                return float(mean)
            except (TypeError, ValueError):
                continue
    return None


async def enrich_analysis_with_cable(
    analysis: Any, symbol: str,
) -> dict[str, Any]:
    """
    Tenta injetar funding_rate do Cable no MarketAnalysis.

    Args:
        analysis: MarketAnalysis (mutado se possível, senão apenas reportado)
        symbol: BTC, ETH, etc

    Returns:
        Dict com info de enrichment:
        {
          "applied": bool,
          "source": "cable" | "preserved" | "none",
          "funding_rate": float | None,
          "reason": str
        }
    """
    if not is_enabled():
        return {"applied": False, "source": "none", "funding_rate": None,
                "reason": "adapter disabled"}

    cable_report = await get_cable_snapshot()
    if not cable_report:
        return {"applied": False, "source": "none", "funding_rate": None,
                "reason": "no cable snapshot available"}

    cable_funding = extract_funding_for_symbol(cable_report, symbol)
    if cable_funding is None:
        return {"applied": False, "source": "none", "funding_rate": None,
                "reason": f"cable has no funding for {symbol}"}

    # Check current funding_rate from onchain
    current = None
    try:
        onchain = getattr(analysis, "onchain", None)
        if onchain is not None:
            current = getattr(onchain, "funding_rate", None)
    except Exception:  # noqa: BLE001
        pass

    # Preserve explicit non-None values (Black Panther wins if it produced)
    if current is not None and abs(current) > 1e-9:
        return {
            "applied": False, "source": "preserved",
            "funding_rate": current,
            "reason": f"black_panther already provided {current:.6f}",
            "cable_value": cable_funding,
        }

    # Review-fix (2026-06-01): NORMALIZAR a unidade. O funding do Cable vem do
    # Binance /fapi/v1/fundingRate, que é taxa de 8h. Black Panther (Hyperliquid)
    # produz taxa HORÁRIA. Os consumidores (Spider-Man EXTREME_FUNDING_THRESHOLD,
    # Vision) tratam onchain.funding_rate como HORÁRIO. Injetar o valor 8h cru
    # fazia o funding parecer ~8× maior → falso "funding extremo". Converte
    # 8h → horário para o campo ficar numa unidade única.
    cable_funding_hourly = cable_funding / 8.0

    # Inject cable value (já normalizado para horário)
    applied = False
    try:
        if hasattr(analysis, "onchain") and analysis.onchain is not None:
            try:
                analysis.onchain.funding_rate = cable_funding_hourly
                applied = True
            except Exception:  # noqa: BLE001
                # Pydantic immutable? Try model_copy
                try:
                    new_onchain = analysis.onchain.model_copy(
                        update={"funding_rate": cable_funding_hourly},
                    )
                    analysis.onchain = new_onchain
                    applied = True
                except Exception as exc_pyd:  # noqa: BLE001
                    logger.debug(
                        f"[cable_regime_adapter] inject failed (immutable): {exc_pyd}",
                    )
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[cable_regime_adapter] inject failed: {exc}")

    return {
        "applied": applied,
        "source": "cable" if applied else "none",
        "funding_rate": cable_funding_hourly,   # horário (normalizado)
        "funding_rate_8h": cable_funding,        # 8h cru (referência)
        "reason": (
            f"cable funding {cable_funding:.6f}/8h → {cable_funding_hourly:.6f}/h injected"
            if applied else "inject failed"
        ),
        "enriched_at": datetime.now(timezone.utc).isoformat(),
    }


def stats() -> dict[str, Any]:
    """Snapshot pro dashboard."""
    return {
        "enabled": is_enabled(),
        "cable_agent_enabled": os.environ.get(
            "CABLE_AGENT_ENABLED", "false",
        ).lower() in ("1", "true", "yes", "on"),
    }
