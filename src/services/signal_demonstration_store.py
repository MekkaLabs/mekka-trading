"""
src/services/signal_demonstration_store.py
========================================
Story 190 — SignalDemonstrationStore: few-shot demos injetados no prompt Vision.

Inspirado no padrão SWE-agent Demonstrations:
  "Trajectories can be converted to demos using the sweagent traj-to-demo command,
   which saves them as readable yaml files in the demos/ directory, and can then
   be edited by hand. These demonstrations are injected as few-shot examples in
   the system prompt to guide the agent's behavior."

No SWE-agent, demonstrações são trajetórias reais de sucesso convertidas em YAML
e injetadas no system prompt — o modelo aprende por exemplo ao ver "aqui está como
um agente experiente resolveu um problema similar".

No Mekka, o equivalente é: quando Vision analisa BTC em regime VOLATILE,
recebe 1-2 exemplos de sinais bem-sucedidos anteriores em condições similares
(regime + símbolo) como few-shot context. Diferente do SignalOutcomeMemory (Story 186)
que foca em performance histórica, as Demonstrations focam em mostrar o
*formato e raciocínio* de um bom sinal — são templates educativos, não estatísticas.

Arquitetura
-----------
  Demonstration — um exemplo de sinal com contexto e reasoning
  SignalDemonstrationStore
    ├── add(symbol, regime, signal_json, reasoning, outcome_label)
    ├── get_similar(symbol, regime, top_n) → list[Demonstration]
    ├── get_prompt_block(symbol, regime) → str
    ├── load_from_file(path) — carrega demos de JSON (arquivo editável)
    └── summary() → dict

Uso em Vision.run()
-------------------
    from src.services.signal_demonstration_store import get_demonstration_store

    demo_block = get_demonstration_store().get_prompt_block(symbol, regime=_regime)
    if demo_block:
        prompt = prompt + "\\n\\n" + demo_block
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------

@dataclass
class Demonstration:
    """
    Exemplo de sinal bem-sucedido — equivalente a um demo YAML do SWE-agent.

    Fields:
      symbol        : símbolo do ativo
      regime        : regime de mercado (ex: "VOLATILE", "BULL")
      signal_json   : TradingSignal serializado como JSON string
      reasoning     : reasoning que levou ao sinal (texto livre)
      outcome_label : "WIN" | "LOSS" | "PENDING"
      source        : "auto" (gerado pelo pipeline) ou "manual" (analista)
    """
    symbol: str
    regime: str
    signal_json: str
    reasoning: str = ""
    outcome_label: str = "PENDING"  # "WIN", "LOSS", "PENDING"
    source: str = "auto"
    confidence: float = 0.0

    def matches(self, symbol: str, regime: str) -> bool:
        """True se este demo é relevante para o contexto dado."""
        sym_match = not symbol or self.symbol.upper() == symbol.upper()
        reg_match = not regime or self.regime.upper() == regime.upper()
        # Partial regime match (ex: "BULL" ↔ "STRONG_BULL")
        if not reg_match and regime:
            reg_match = self.regime.upper() in regime.upper() or regime.upper() in self.regime.upper()
        return sym_match and reg_match

    def to_prompt_block(self) -> str:
        """Formata como bloco few-shot para injeção no prompt."""
        outcome_emoji = {"WIN": "✅", "LOSS": "❌", "PENDING": "⏳"}.get(self.outcome_label, "")
        try:
            signal_dict = json.loads(self.signal_json)
            action = signal_dict.get("action", "?")
            conf = signal_dict.get("confidence", self.confidence)
            entry = signal_dict.get("entry_price", "?")
        except Exception:  # noqa: BLE001
            action, conf, entry = "?", self.confidence, "?"

        lines = [
            f"--- Example Signal ({self.symbol} | {self.regime}) {outcome_emoji} ---",
            f"Action: {action} | Confidence: {conf:.0%} | Entry: {entry}",
        ]
        if self.reasoning:
            lines.append(f"Reasoning: {self.reasoning[:300]}")
        lines.append("--- End Example ---")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "regime": self.regime,
            "outcome_label": self.outcome_label,
            "confidence": self.confidence,
            "source": self.source,
            "reasoning_preview": self.reasoning[:100] if self.reasoning else "",
        }


# ---------------------------------------------------------------------------
# SignalDemonstrationStore
# ---------------------------------------------------------------------------

class SignalDemonstrationStore:
    """
    Store de demonstrações few-shot para injeção no prompt Vision.

    Padrão SWE-agent Demonstrations: exemplos reais de sucesso injetados
    no system prompt para guiar o modelo por analogia. Aqui: sinais bem-
    sucedidos anteriores servem como templates de raciocínio para o Vision.
    """

    DEFAULT_DEMOS_FILE = "data/signal_demonstrations.json"

    def __init__(self, max_per_regime: int = 10) -> None:
        self._demos: Dict[str, List[Demonstration]] = {}  # key: "SYMBOL:REGIME"
        self._max_per_regime = max_per_regime
        self._total_added: int = 0
        self._file_loaded: bool = False

    def _key(self, symbol: str, regime: str) -> str:
        return f"{symbol.upper()}:{regime.upper()}"

    def add(
        self,
        symbol: str,
        regime: str,
        signal_json: str,
        reasoning: str = "",
        outcome_label: str = "PENDING",
        confidence: float = 0.0,
        source: str = "auto",
    ) -> Demonstration:
        """
        Adiciona uma demonstração ao store.

        Tipicamente chamado por NickFury quando um trade WIN é confirmado.

        Args:
            symbol: símbolo do ativo
            regime: regime de mercado
            signal_json: TradingSignal serializado
            reasoning: texto de raciocínio do Vision
            outcome_label: resultado ("WIN", "LOSS", "PENDING")
            confidence: confiança do sinal original
            source: "auto" ou "manual"
        """
        demo = Demonstration(
            symbol=symbol.upper(),
            regime=regime.upper(),
            signal_json=signal_json,
            reasoning=reasoning,
            outcome_label=outcome_label,
            confidence=confidence,
            source=source,
        )
        key = self._key(symbol, regime)
        if key not in self._demos:
            self._demos[key] = []

        self._demos[key].append(demo)
        self._total_added += 1

        # Mantém apenas os melhores (WIN primeiro, depois por confiança)
        if len(self._demos[key]) > self._max_per_regime:
            wins = [d for d in self._demos[key] if d.outcome_label == "WIN"]
            others = [d for d in self._demos[key] if d.outcome_label != "WIN"]
            wins.sort(key=lambda d: d.confidence, reverse=True)
            others.sort(key=lambda d: d.confidence, reverse=True)
            self._demos[key] = (wins + others)[:self._max_per_regime]

        logger.debug(f"[DemoStore] added demo {symbol} {regime} {outcome_label}")
        return demo

    def get_similar(
        self,
        symbol: str,
        regime: str,
        top_n: int = 2,
        prefer_wins: bool = True,
    ) -> List[Demonstration]:
        """
        Retorna top-N demonstrações mais relevantes para o contexto.

        Prioridade: WIN > PENDING > LOSS, depois por regime exact match.
        """
        # Carrega arquivo se não carregado ainda
        if not self._file_loaded:
            self._try_load_file()

        candidates: List[Demonstration] = []
        for demos in self._demos.values():
            for d in demos:
                if d.matches(symbol, regime):
                    candidates.append(d)

        if not candidates:
            return []

        if prefer_wins:
            order = {"WIN": 0, "PENDING": 1, "LOSS": 2}
            candidates.sort(key=lambda d: (order.get(d.outcome_label, 3), -d.confidence))
        else:
            candidates.sort(key=lambda d: -d.confidence)

        return candidates[:top_n]

    def get_prompt_block(
        self,
        symbol: str,
        regime: str = "UNKNOWN",
        top_n: int = 2,
    ) -> str:
        """
        Gera bloco few-shot para injeção no prompt Vision.

        Formato:
            === Signal Demonstrations (similar conditions) ===
            The following examples show successful signals in similar market conditions.
            Use them as references for format and reasoning quality.

            --- Example Signal (BTC | VOLATILE) ✅ ---
            Action: LONG | Confidence: 80% | Entry: 50000.0
            Reasoning: Strong momentum breakout above resistance...
            --- End Example ---

        Returns:
            String formatada, ou "" se não há demos.
        """
        demos = self.get_similar(symbol, regime, top_n=top_n, prefer_wins=True)
        if not demos:
            return ""

        lines = [
            "=== Signal Demonstrations (similar conditions) ===",
            "The following examples show high-quality signals in similar market conditions.",
            "Use them as references for reasoning format and signal structure.",
            "",
        ]
        for demo in demos:
            lines.append(demo.to_prompt_block())
            lines.append("")

        return "\n".join(lines).rstrip()

    def load_from_file(self, path: str = "") -> int:
        """
        Carrega demonstrações de um arquivo JSON.

        Formato esperado:
            [{"symbol": "BTC", "regime": "VOLATILE", "signal_json": "{...}",
              "reasoning": "...", "outcome_label": "WIN", "confidence": 0.80}]

        Returns:
            Número de demonstrações carregadas.
        """
        file_path = path or self.DEFAULT_DEMOS_FILE
        if not os.path.exists(file_path):
            return 0
        try:
            with open(file_path) as f:
                data = json.load(f)
            loaded = 0
            for item in data:
                self.add(
                    symbol=item.get("symbol", ""),
                    regime=item.get("regime", ""),
                    signal_json=item.get("signal_json", "{}"),
                    reasoning=item.get("reasoning", ""),
                    outcome_label=item.get("outcome_label", "PENDING"),
                    confidence=float(item.get("confidence", 0.0)),
                    source=item.get("source", "file"),
                )
                loaded += 1
            logger.info(f"[DemoStore] loaded {loaded} demos from {file_path}")
            return loaded
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[DemoStore] failed to load {file_path}: {exc}")
            return 0

    def _try_load_file(self) -> None:
        """Carrega o arquivo padrão na primeira chamada (lazy load)."""
        self._file_loaded = True
        self.load_from_file()

    def summary(self) -> dict:
        total = sum(len(v) for v in self._demos.values())
        wins = sum(
            sum(1 for d in v if d.outcome_label == "WIN")
            for v in self._demos.values()
        )
        return {
            "total_demos": total,
            "total_added": self._total_added,
            "wins": wins,
            "regime_keys": list(self._demos.keys()),
            "max_per_regime": self._max_per_regime,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_store: Optional[SignalDemonstrationStore] = None


def get_demonstration_store(max_per_regime: int = 10) -> SignalDemonstrationStore:
    """Retorna o singleton global do SignalDemonstrationStore."""
    global _store
    if _store is None:
        try:
            from src.config.settings import settings
            max_n = int(getattr(settings, "demo_store_max_per_regime", max_per_regime))
        except Exception:  # noqa: BLE001
            max_n = max_per_regime
        _store = SignalDemonstrationStore(max_per_regime=max_n)
    return _store


def reset_demonstration_store() -> None:
    """Reseta o singleton — para testes."""
    global _store
    _store = None
