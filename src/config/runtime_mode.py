"""
src/config/runtime_mode.py
==========================
Runtime Trading Mode — hot-reload sem reiniciar o sistema.

Três presets definem o comportamento global do sistema:
  conservative — posições menores, menos leverage, só BTC, ritmo lento
  balanced     — configuração padrão recomendada (default)
  aggressive   — posições maiores, mais ativos, ritmo rápido

O modo é persistido em data/runtime_mode.json e lido a cada ciclo pelos
agentes. A troca entra em vigor no próximo ciclo, sem reinício.

Uso
---
    from src.config.runtime_mode import get_mode, set_mode, get_params

    params = get_params()          # dict com os valores ativos
    set_mode("aggressive")         # persiste e atualiza singleton
    get_mode()                     # → "aggressive"
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Campos opcionais (no-op em modos swing, ativos em scalp). Documentados aqui
# pra qualquer agente que ler PRESETS saber o contrato:
#
#   max_trades_per_hour: int | None        # Batman gate (None = sem cap horário)
#   max_position_age_minutes: int | None   # Cyclops time-stop (None = sem limite)
#   scalp_primary_timeframe: str | None    # Superman tf override (None = settings)
#   scalp_confirmation_timeframe: str | None
#   main_loop_interval_seconds: int | None # NickFury loop (None = settings)
#   flash_is_proposer: bool                # Flash entra no MarketAnalysis
#   min_atr_pct_for_entry: float | None    # Batman gate (vol mínima)
# ---------------------------------------------------------------------------

PRESETS: dict[str, dict[str, Any]] = {
    "conservative": {
        "label": "🛡️ Conservador",
        "description": "Posições pequenas, leverage baixo, só BTC, ritmo lento.",
        "max_position_size_pct": 0.005,   # 0.5%
        "max_leverage": 2,
        "max_leverage_high_regime": 1,
        "max_leverage_extreme_regime": 1,
        "max_daily_drawdown_pct": 0.05,   # 5%
        "max_trades_per_day": 3,
        "trading_assets": ["BTC"],
        "min_risk_reward_ratio": 2.0,
        # Story 050 — VisionCritic threshold: lower = critic fires more easily (fewer trades)
        "vision_critic_min_disagreement": 0.20,
        # Story 057 — Correlation gate: apply size penalty after N same-dir positions
        # and hard-reject after M. Conservative = tightest limits.
        "correlation_penalty_threshold": 1,   # 1st same-dir → 60% size reduction
        "correlation_reject_threshold": 2,    # 2nd same-dir → REJECT
        # Scalp fields — no-op em swing
        "max_trades_per_hour": None,
        "max_position_age_minutes": None,
        "scalp_primary_timeframe": None,
        "scalp_confirmation_timeframe": None,
        "main_loop_interval_seconds": None,
        "flash_is_proposer": False,
        "min_atr_pct_for_entry": None,
    },
    "balanced": {
        "label": "⚖️ Balanceado",
        "description": "Configuração padrão — bom equilíbrio entre risco e oportunidade.",
        "max_position_size_pct": 0.02,    # 2%
        "max_leverage": 5,
        "max_leverage_high_regime": 3,
        "max_leverage_extreme_regime": 2,
        "max_daily_drawdown_pct": 0.10,   # 10%
        "max_trades_per_day": 10,
        "trading_assets": ["BTC", "ETH", "SOL"],
        "min_risk_reward_ratio": 1.5,
        # Story 050 — VisionCritic threshold: matches current settings default
        "vision_critic_min_disagreement": 0.30,
        # Story 057 — Correlation gate
        "correlation_penalty_threshold": 1,   # 1st same-dir → 50% size reduction
        "correlation_reject_threshold": 2,    # 2nd same-dir → REJECT
        # Scalp fields — no-op em swing
        "max_trades_per_hour": None,
        "max_position_age_minutes": None,
        "scalp_primary_timeframe": None,
        "scalp_confirmation_timeframe": None,
        "main_loop_interval_seconds": None,
        "flash_is_proposer": False,
        "min_atr_pct_for_entry": None,
    },
    "aggressive": {
        "label": "⚡ Agressivo",
        "description": "Posições maiores, mais ativos, mais trades. Risco elevado.",
        "max_position_size_pct": 0.05,    # 5%
        "max_leverage": 10,
        "max_leverage_high_regime": 5,
        "max_leverage_extreme_regime": 3,
        "max_daily_drawdown_pct": 0.15,   # 15%
        "max_trades_per_day": 20,
        "trading_assets": ["BTC", "ETH", "SOL", "AVAX"],
        "min_risk_reward_ratio": 1.2,
        # Story 050 — VisionCritic threshold: higher = critic rarely overrides (more trades)
        "vision_critic_min_disagreement": 0.45,
        # Story 057 — Correlation gate: relaxed in aggressive mode
        "correlation_penalty_threshold": 2,   # 2nd same-dir → 40% size reduction
        "correlation_reject_threshold": 3,    # 3rd same-dir → REJECT
        # Scalp fields — no-op em swing
        "max_trades_per_hour": None,
        "max_position_age_minutes": None,
        "scalp_primary_timeframe": None,
        "scalp_confirmation_timeframe": None,
        "main_loop_interval_seconds": None,
        "flash_is_proposer": False,
        "min_atr_pct_for_entry": None,
    },
    "scalp": {
        "label": "⚡⚡ Scalp",
        "description": (
            "Intraday curto — timeframes pequenos (5m/1m), loop rápido (2min), "
            "max 6 trades/hora, time-stop 30min, Flash como proposer ativo. "
            "MVP recomendado em paper/testnet."
        ),
        # Risk caps — apertados (posição pequena, leverage baixo)
        "max_position_size_pct": 0.01,    # 1% (menor que aggressive)
        "max_leverage": 3,
        "max_leverage_high_regime": 2,
        "max_leverage_extreme_regime": 1,
        "max_daily_drawdown_pct": 0.04,   # 4% (mais apertado pq mais trades)
        "max_trades_per_day": 30,         # várias entradas/dia
        "trading_assets": ["BTC", "ETH"], # só os mais líquidos
        "min_risk_reward_ratio": 1.0,     # scalp aceita R:R 1:1 (alta freq compensa)
        # VisionCritic mais permissivo — modo permite mais trades
        "vision_critic_min_disagreement": 0.50,
        # Correlation: stricter (não quer N positions same-dir em scalp)
        "correlation_penalty_threshold": 1,
        "correlation_reject_threshold": 2,
        # Scalp-specific fields — ativos
        "max_trades_per_hour": 6,           # Batman cap horário
        "max_position_age_minutes": 30,     # Cyclops time-stop
        "scalp_primary_timeframe": "5m",
        "scalp_confirmation_timeframe": "1m",
        "main_loop_interval_seconds": 120,  # 2min loop (vs 4h em swing)
        "flash_is_proposer": True,          # Flash entra no MarketAnalysis
        "min_atr_pct_for_entry": 0.0015,    # 0.15% ATR mínimo — evita range morto
    },
}

VALID_MODES = list(PRESETS.keys())
DEFAULT_MODE = "balanced"

# Modos que devem ativar o scalp pipeline (timeframes curtos, Flash proposer).
# Future-proof: se criarmos scalp-aggressive ou scalp-conservative, basta
# adicionar aqui sem editar quem lê.
SCALP_MODES = frozenset({"scalp"})


def is_scalp_mode(mode: str | None = None) -> bool:
    """True quando o modo ativo (ou explícito) é uma variante scalp."""
    m = mode if mode is not None else _current_mode
    return m in SCALP_MODES

# ---------------------------------------------------------------------------
# Persistence path
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_MODE_FILE = _DATA_DIR / "runtime_mode.json"

# ---------------------------------------------------------------------------
# In-memory singleton (thread-safe)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_current_mode: str = DEFAULT_MODE
_loaded: bool = False


def _load_from_disk() -> None:
    """Read persisted mode from disk (called once at first access)."""
    global _current_mode, _loaded
    if _MODE_FILE.exists():
        try:
            data = json.loads(_MODE_FILE.read_text())
            mode = data.get("mode", DEFAULT_MODE)
            if mode in VALID_MODES:
                _current_mode = mode
            else:
                _log.warning(f"[RuntimeMode] unknown mode '{mode}' in file — using {DEFAULT_MODE}")
        except Exception as exc:
            _log.warning(f"[RuntimeMode] could not read {_MODE_FILE}: {exc} — using {DEFAULT_MODE}")
    _loaded = True


def _ensure_loaded() -> None:
    global _loaded
    if not _loaded:
        with _lock:
            if not _loaded:
                _load_from_disk()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_mode() -> str:
    """Return current mode name (e.g. 'balanced')."""
    _ensure_loaded()
    return _current_mode


def get_params() -> dict[str, Any]:
    """Return full preset dict for the active mode."""
    _ensure_loaded()
    return dict(PRESETS[_current_mode])


def get_preset(mode: str) -> dict[str, Any]:
    """Return preset dict for a specific mode."""
    if mode not in PRESETS:
        raise ValueError(f"Unknown mode '{mode}'. Valid: {VALID_MODES}")
    return dict(PRESETS[mode])


def set_mode(mode: str) -> dict[str, Any]:
    """
    Change the active mode and persist to disk.

    Returns the new mode's preset dict.
    Raises ValueError for unknown modes.
    """
    global _current_mode
    if mode not in VALID_MODES:
        raise ValueError(f"Unknown mode '{mode}'. Valid: {VALID_MODES}")

    with _lock:
        _current_mode = mode
        _persist()

    _log.info(f"[RuntimeMode] mode changed → {mode} ({PRESETS[mode]['label']})")
    return dict(PRESETS[mode])


def _persist() -> None:
    """Write current mode to disk (called inside _lock)."""
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        _MODE_FILE.write_text(json.dumps({"mode": _current_mode}, indent=2))
    except Exception as exc:
        _log.error(f"[RuntimeMode] could not persist mode: {exc}")


def all_modes_summary() -> list[dict[str, Any]]:
    """Return list of all modes with key metadata — used by API and UI."""
    current = get_mode()
    return [
        {
            "id": mode_id,
            "label": preset["label"],
            "description": preset["description"],
            "active": mode_id == current,
            "params": {
                k: v for k, v in preset.items()
                if k not in ("label", "description")
            },
        }
        for mode_id, preset in PRESETS.items()
    ]
