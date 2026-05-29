"""
src/services/symbol_validation.py
==================================
TRADE-2 (2026-05-29) — Validação de símbolos antes de mandar para Batman/IronMan.

ANTES: 4 endpoints (/api/trade/analyze, /execute, /manual, /manual-analyze)
aceitavam qualquer string como symbol. Batman e IronMan descartavam
silenciosamente trades inválidos — operador ficava esperando execução que
nunca acontecia.

DEPOIS: helper único `validate_trade_symbol()` checa contra:
  1. `settings.trading_assets` — lista canônica do operador (ex: BTC,ETH,SOL).
  2. Sanitização (UPPER, strip).
  3. Caracteres válidos (letras, números, hifen).

Retorna `(ok, normalized, reason)` — caller decide se rejeita 400 ou apenas
loga warning. Read-only, sem side-effect, sem I/O remoto.

Não toca em settings.py (PROTECTED). Não substitui o check de CCXT runtime
em IronMan (que valida contra mercado real) — é uma primeira camada barata.
"""

from __future__ import annotations

import re
from typing import Optional


# Caracteres permitidos: letras, números, hifen. Cobre BTC, ETH, HYPE,
# BNB1000, PEPE-USD, etc.
_VALID_RE = re.compile(r"^[A-Z][A-Z0-9-]{0,15}$")


def validate_trade_symbol(
    raw: Optional[str],
    allowed: Optional[list[str]] = None,
) -> tuple[bool, str, str]:
    """
    Valida um símbolo de trade. Idempotente, read-only.

    Args:
        raw: símbolo bruto (case-insensitive, pode vir com whitespace).
        allowed: lista de símbolos permitidos. Default = settings.trading_assets.
            Pass `[]` ou None para usar settings; pass uma lista explícita
            (ex: ["BTC", "ETH"]) para override em testes.

    Returns:
        (ok, normalized, reason):
          - ok=True quando símbolo é válido e está em allowed
          - normalized = uppercase stripped (ex: "btc " → "BTC")
          - reason = string explicativa (sempre populada)
    """
    if not raw or not isinstance(raw, str):
        return False, "", "symbol vazio ou inválido"

    normalized = raw.strip().upper()
    if not normalized:
        return False, "", "symbol vazio após strip"

    if not _VALID_RE.match(normalized):
        return False, normalized, (
            f"symbol {normalized!r} contém caracteres inválidos "
            "(use só A-Z, 0-9, hifen — primeira letra obrigatória)"
        )

    # Resolve allowed list
    if allowed is None or len(allowed) == 0:
        try:
            from src.config.settings import settings  # noqa: WPS433
            allowed = list(settings.trading_assets or [])
        except Exception:
            # Settings não carregam → permite (fail-open na validação)
            return True, normalized, "settings indisponível — fail-open"

    if not allowed:
        # Sem trading_assets configurado também é fail-open
        return True, normalized, "no trading_assets configured — fail-open"

    if normalized in allowed:
        return True, normalized, f"symbol {normalized} OK"

    # Tentativa de match flexível: "BTCUSDT" → "BTC", "ETH-USD" → "ETH"
    base = re.split(r"(USDT|USD|USDC|PERP|-)", normalized, maxsplit=1)[0]
    if base and base in allowed:
        return True, base, f"symbol {normalized} normalizado para {base}"

    return False, normalized, (
        f"symbol {normalized!r} não está em trading_assets "
        f"({', '.join(allowed[:5])}{'...' if len(allowed) > 5 else ''})"
    )
