"""
src/services/opportunity_scanner.py
=====================================
Story 145 — Opportunity Scanner (Pre-Scan Phase).

Antes de iniciar a análise completa (Layer 1 + Vision + Batman), NickFury
pode usar este scanner para calcular um `OpportunityScore` rápido por
símbolo e priorizar quais merecem análise profunda.

A fase de pré-scan é intencionalmente leve:
  - Usa apenas dados já disponíveis no MarketData / OHLCV básico
  - Sem chamadas LLM, sem sentiment, sem on-chain
  - Executa em paralelo para todos os símbolos configurados
  - Retorna uma lista ordenada (maior score = mais urgente)

Critérios de score (todos opcionais, degradam graciosamente):

  1. Volume spike:     se volume do último candle > N× média → bônus
  2. Momentum:        distância do preço ao EMA20 → bônus em tendência forte
  3. RSI extreme:     RSI < 30 (oversold) ou RSI > 70 (overbought) → bônus
  4. ATR activity:    ATR% > threshold → mercado em movimento → bônus
  5. Stale penalty:   símbolo com stale price ativo → penalidade
  6. Blacklist:       símbolo blacklistado → score 0 (excluído)

Configuração em settings:
  - opportunity_scan_enabled    (bool, default False)
  - opportunity_scan_top_n      (int, default 3) — top-N após ordenação
  - opportunity_scan_min_score  (float, default 0.0) — filtro de score mínimo
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class OpportunityScore:
    """Score de oportunidade para um símbolo."""
    symbol: str
    score: float                            # 0.0 – 1.0+
    reasons: list[str] = field(default_factory=list)
    skipped: bool = False                   # True se símbolo excluído do pré-scan
    skip_reason: str = ""


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

class OpportunityScorer:
    """
    Calcula scores de oportunidade a partir de dados de mercado básicos.

    Todos os cálculos são síncronos e O(candles) — sem I/O.
    NickFury alimenta este scorer com os dados já disponíveis (OHLCV +
    indicadores básicos do Superman).
    """

    # Pesos por critério (somam > 1.0 — scores podem ser > 1.0 em mercados extremos)
    _W_VOLUME_SPIKE = 0.30
    _W_MOMENTUM = 0.25
    _W_RSI_EXTREME = 0.20
    _W_ATR_ACTIVITY = 0.25

    def score(
        self,
        symbol: str,
        price: float = 0.0,
        rsi: Optional[float] = None,
        atr_pct: Optional[float] = None,
        ema20: Optional[float] = None,
        volume_ratio: Optional[float] = None,   # current_vol / avg_vol
        is_stale: bool = False,
        is_blacklisted: bool = False,
    ) -> OpportunityScore:
        """
        Calcula o OpportunityScore para um símbolo.

        Parâmetros
        ----------
        symbol          : símbolo (BTC, ETH, ...)
        price           : preço atual
        rsi             : RSI 14 (0-100)
        atr_pct         : ATR% = ATR/price (0.01 = 1%)
        ema20           : EMA 20 períodos
        volume_ratio    : volume atual / média (ex. 2.0 = 2× a média)
        is_stale        : True se StalePriceDetector está tripped
        is_blacklisted  : True se símbolo está no blacklist do Batman
        """
        if is_blacklisted:
            return OpportunityScore(
                symbol=symbol, score=0.0, skipped=True,
                skip_reason="blacklisted"
            )

        reasons: list[str] = []
        score = 0.0

        # 1. Volume spike
        if volume_ratio is not None and volume_ratio > 1.5:
            contribution = min((volume_ratio - 1.0) / 4.0, 1.0) * self._W_VOLUME_SPIKE
            score += contribution
            reasons.append(f"volume_spike={volume_ratio:.1f}x (+{contribution:.2f})")

        # 2. Momentum — distância percentual do preço ao EMA20
        if price > 0 and ema20 is not None and ema20 > 0:
            momentum_pct = abs(price - ema20) / ema20
            contribution = min(momentum_pct / 0.05, 1.0) * self._W_MOMENTUM
            score += contribution
            direction = "above" if price > ema20 else "below"
            reasons.append(f"ema_gap={momentum_pct:.2%} {direction} EMA20 (+{contribution:.2f})")

        # 3. RSI extreme (oversold < 30, overbought > 70)
        if rsi is not None:
            if rsi < 30:
                contribution = (30 - rsi) / 30.0 * self._W_RSI_EXTREME
                score += contribution
                reasons.append(f"rsi_oversold={rsi:.1f} (+{contribution:.2f})")
            elif rsi > 70:
                contribution = (rsi - 70) / 30.0 * self._W_RSI_EXTREME
                score += contribution
                reasons.append(f"rsi_overbought={rsi:.1f} (+{contribution:.2f})")

        # 4. ATR activity (mercado em movimento)
        if atr_pct is not None and atr_pct > 0:
            contribution = min(atr_pct / 0.03, 1.0) * self._W_ATR_ACTIVITY
            score += contribution
            reasons.append(f"atr_pct={atr_pct:.2%} (+{contribution:.2f})")

        # 5. Stale price penalty
        if is_stale:
            score *= 0.1
            reasons.append("stale_price_penalty (×0.1)")

        score = round(score, 4)

        return OpportunityScore(
            symbol=symbol,
            score=score,
            reasons=reasons,
        )


# ---------------------------------------------------------------------------
# Pre-scan result
# ---------------------------------------------------------------------------

@dataclass
class PreScanResult:
    """Resultado do pré-scan de oportunidades."""
    scores: list[OpportunityScore]              # todos os scores, ordenados DESC
    selected: list[str]                         # símbolos selecionados para análise profunda
    skipped: list[str]                          # símbolos excluídos (blacklist, stale, etc.)

    def summary(self) -> str:
        lines = [f"[OpportunityScanner] Pre-scan: {len(self.scores)} symbols"]
        for s in self.scores[:5]:
            flag = "⚡ SELECTED" if s.symbol in self.selected else ("⛔ SKIPPED" if s.skipped else "— skipped (low score)")
            lines.append(f"  {s.symbol}: {s.score:.3f} {flag}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scanner — used by NickFury
# ---------------------------------------------------------------------------

def run_pre_scan(
    symbols: list[str],
    market_data: dict,   # symbol → dict com keys: price, rsi, atr_pct, ema20, volume_ratio, is_stale, is_blacklisted
    top_n: int = 3,
    min_score: float = 0.0,
) -> PreScanResult:
    """
    Executa o pré-scan para todos os símbolos e retorna os top-N.

    Parâmetros
    ----------
    symbols     : lista de símbolos para escanear
    market_data : dict com dados básicos por símbolo (pode estar incompleto — degrada graciosamente)
    top_n       : máximo de símbolos para análise profunda
    min_score   : score mínimo para inclusão

    Retorna
    -------
    PreScanResult com scores ordenados e lista selected.
    """
    scorer = OpportunityScorer()
    scores: list[OpportunityScore] = []

    for sym in symbols:
        data = market_data.get(sym, {})
        try:
            opp = scorer.score(
                symbol=sym,
                price=data.get("price", 0.0),
                rsi=data.get("rsi"),
                atr_pct=data.get("atr_pct"),
                ema20=data.get("ema20"),
                volume_ratio=data.get("volume_ratio"),
                is_stale=bool(data.get("is_stale", False)),
                is_blacklisted=bool(data.get("is_blacklisted", False)),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[OpportunityScanner] {sym} score failed: {exc}")
            opp = OpportunityScore(symbol=sym, score=0.0, skipped=True, skip_reason=str(exc))
        scores.append(opp)

    # Sort: non-skipped first, then by score DESC
    scores.sort(key=lambda s: (s.skipped, -s.score))

    skipped = [s.symbol for s in scores if s.skipped]
    candidates = [s for s in scores if not s.skipped and s.score >= min_score]
    selected_scores = candidates[:top_n]
    selected = [s.symbol for s in selected_scores]

    # If no candidates pass the filter, fall back to all symbols (safety net)
    if not selected:
        logger.warning("[OpportunityScanner] No symbols passed pre-scan filter — using all symbols")
        selected = [sym for sym in symbols if sym not in skipped]

    return PreScanResult(scores=scores, selected=selected, skipped=skipped)
