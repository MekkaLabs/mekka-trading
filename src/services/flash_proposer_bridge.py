"""
src/services/flash_proposer_bridge.py
========================================
Bridge que conecta `flash_is_proposer` (definido em runtime_mode presets) ao
runtime real do council.

Gap identificado pela auditoria 2026-05-28:
- Preset scalp declara `flash_is_proposer=True` em runtime_mode.py:154
- Mas NENHUM código de runtime lê essa flag
- Resultado: Flash continua sendo só advisory consumido por Vision via prompt;
  em scalp, ele deveria ter PESO DE PROPOSER (block trade se contradisser
  direção do Vision com confidence alta)

Este módulo expõe 2 helpers fail-silent:

- `is_flash_proposer_active()` — True quando modo ativo tem flag=True
- `flash_disagreement_severity(momentum, signal_action)` — quantifica
  conflito entre direção do Flash e ação proposta

Quem consome (a ser plugado em commits subsequentes):
- Batman: opcional — reject quando severity=HIGH em modo scalp
- Vision: opcional — clamp confidence quando severity≥MEDIUM em scalp

Hard rules:
- Fail-silent (qualquer exception retorna defaults seguros)
- Read-only no runtime_mode
- Sem side-effects (não escreve em DB, vault, audit)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from loguru import logger


class DisagreementSeverity(str, Enum):
    NONE = "NONE"        # mesma direção ou Flash indefinido
    LOW = "LOW"          # divergência sutil
    MEDIUM = "MEDIUM"    # divergência clara, confidence Flash média
    HIGH = "HIGH"        # divergência forte, confidence Flash alta


def is_flash_proposer_active() -> bool:
    """True quando o preset ativo tem flash_is_proposer=True. Fail-silent."""
    try:
        from src.config.runtime_mode import get_params
        params = get_params() or {}
        return bool(params.get("flash_is_proposer", False))
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[flash_bridge] is_flash_proposer_active fail: {exc}")
        return False


def _coerce_direction(value: Any) -> Optional[str]:
    """Normaliza direção (enum/str/None) para 'LONG' | 'SHORT' | None."""
    if value is None:
        return None
    if hasattr(value, "value"):
        value = value.value
    if not isinstance(value, str):
        return None
    v = value.strip().upper()
    if v in ("LONG", "BUY", "UP"):
        return "LONG"
    if v in ("SHORT", "SELL", "DOWN"):
        return "SHORT"
    return None  # SIDEWAYS, NEUTRAL, etc → None (não conta como divergência)


def flash_disagreement_severity(
    momentum: Optional[Any],
    signal_action: Any,
    confidence_threshold_medium: float = 0.6,
    confidence_threshold_high: float = 0.8,
) -> DisagreementSeverity:
    """
    Quantifica conflito entre direção do Flash momentum e ação proposta
    pelo Vision/signal final.

    Args:
        momentum: MomentumSignal ou compatível (atributos `direction`,
            `confidence`). None ou inválido → NONE.
        signal_action: TradeAction ou str ("LONG"/"SHORT"/"HOLD").
        confidence_threshold_medium: cap inferior para escalar para MEDIUM.
        confidence_threshold_high: cap inferior para HIGH.

    Returns:
        DisagreementSeverity. NONE quando não há conflito ou dados insuficientes.

    Fail-silent: qualquer exception → NONE.
    """
    try:
        if momentum is None:
            return DisagreementSeverity.NONE

        flash_dir = _coerce_direction(getattr(momentum, "direction", None))
        signal_dir = _coerce_direction(signal_action)

        if flash_dir is None or signal_dir is None:
            return DisagreementSeverity.NONE
        if flash_dir == signal_dir:
            return DisagreementSeverity.NONE

        # Divergência. Calibra pela confidence do Flash.
        flash_conf = float(getattr(momentum, "confidence", 0.0) or 0.0)
        if flash_conf >= confidence_threshold_high:
            return DisagreementSeverity.HIGH
        if flash_conf >= confidence_threshold_medium:
            return DisagreementSeverity.MEDIUM
        return DisagreementSeverity.LOW
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[flash_bridge] severity calc fail: {exc}")
        return DisagreementSeverity.NONE


def should_block_for_disagreement(
    momentum: Optional[Any],
    signal_action: Any,
    *,
    severity_to_block: DisagreementSeverity = DisagreementSeverity.HIGH,
) -> tuple[bool, str]:
    """
    Decisão de alto nível: deve bloquear trade por disagreement?

    Só bloqueia quando:
      1. is_flash_proposer_active() == True (modo scalp ou similar)
      2. severity ≥ severity_to_block (default HIGH)

    Returns:
        (should_block, reason). reason é string explicativa pro audit log.
    """
    if not is_flash_proposer_active():
        return False, "flash not proposer in current mode"

    sev = flash_disagreement_severity(momentum, signal_action)
    sev_order = {
        DisagreementSeverity.NONE: 0,
        DisagreementSeverity.LOW: 1,
        DisagreementSeverity.MEDIUM: 2,
        DisagreementSeverity.HIGH: 3,
    }
    if sev_order[sev] >= sev_order[severity_to_block]:
        flash_dir = _coerce_direction(getattr(momentum, "direction", None))
        signal_dir = _coerce_direction(signal_action)
        flash_conf = float(getattr(momentum, "confidence", 0.0) or 0.0)
        return True, (
            f"flash_proposer disagreement: flash={flash_dir} "
            f"(conf={flash_conf:.2f}) vs signal={signal_dir} "
            f"severity={sev.value}"
        )
    return False, f"severity {sev.value} below threshold {severity_to_block.value}"
