"""
src/services/observation_feedback_loop.py
========================================
Story 191 — ObservationFeedbackLoop: feedback de correções re-injetado no Vision.

Inspirado no padrão SWE-agent ACI guardrails + linter observation:
  "SWE-agent integrates a code linter into the edit function, with select errors
   from the linter shown to the agent along with a snippet of the file contents
   before/after the error was introduced. The agent receives specific, concise
   feedback about a command's effects at every turn as part of its 'observation'."

No SWE-agent, depois de cada `edit` a observação inclui automaticamente:
  - Output do linter (ex: "line 42: missing colon")
  - Snippet do arquivo antes/depois do erro
  - O agente vê isso como contexto para o próximo turn e corrige

No Mekka, o equivalente é: quando AutoSignalLinter (Story 179) corrige o sinal,
o resumo das correções é formatado como "lint observation" e injetado no próximo
prompt do Vision para o mesmo símbolo. O Vision aprende dos seus próprios erros
geometria (SL/TP invertido, confiança inválida) em ciclos consecutivos.

Arquitetura
-----------
  LintObservation — registro de uma correção (campo, antes, depois, regra)
  ObservationFeedbackLoop
    ├── record_observation(symbol, lint_result)   — grava observações do lint
    ├── get_feedback_block(symbol) → str           — bloco formatado p/ prompt
    ├── clear(symbol)                              — limpa após incorporação
    └── summary() → dict

Uso em Vision.run() (após AutoSignalLinter no NickFury, antes do próximo ciclo)
Estratégia: NickFury grava a observação; Vision lê no próximo ciclo.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# LintObservation
# ---------------------------------------------------------------------------

@dataclass
class LintObservation:
    """
    Registro de uma correção aplicada pelo AutoSignalLinter.

    Equivalente ao snippet de linter mostrado ao agente no SWE-agent:
    "before/after the error was introduced".
    """
    symbol: str
    rule: str                  # ex: "confidence_clamp", "long_sl_tp_swap"
    field_name: str            # ex: "confidence", "stop_loss"
    before_value: str          # valor antes da correção
    after_value: str           # valor após a correção
    description: str           # descrição humana da correção
    cycle_id: str = ""
    timestamp: float = field(default_factory=time.monotonic)

    def to_prompt_line(self) -> str:
        """Linha compacta para feedback ao Vision."""
        return (
            f"  ⚠ {self.rule}: {self.field_name} "
            f"was {self.before_value} → corrected to {self.after_value}. "
            f"{self.description}"
        )

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "rule": self.rule,
            "field_name": self.field_name,
            "before_value": self.before_value,
            "after_value": self.after_value,
            "description": self.description,
            "cycle_id": self.cycle_id,
        }


# ---------------------------------------------------------------------------
# ObservationFeedbackLoop
# ---------------------------------------------------------------------------

class ObservationFeedbackLoop:
    """
    Loop de feedback de observações de lint para o Vision.

    Padrão SWE-agent ACI guardrails: o agente recebe feedback específico sobre
    erros de formatação/geometria no seu output como parte da próxima observação.
    Aqui: correções do AutoSignalLinter são mostradas ao Vision no ciclo seguinte.
    """

    def __init__(self, max_observations_per_symbol: int = 5) -> None:
        self._pending: Dict[str, List[LintObservation]] = {}
        self._max_per_symbol = max_observations_per_symbol
        self._total_recorded: int = 0
        self._total_consumed: int = 0

    def record_observation(
        self,
        symbol: str,
        rule: str,
        field_name: str,
        before_value: str,
        after_value: str,
        description: str = "",
        cycle_id: str = "",
    ) -> LintObservation:
        """
        Registra uma observação de correção para o símbolo.

        Args:
            symbol: símbolo do ativo
            rule: nome da regra do linter (ex: "confidence_clamp")
            field_name: campo corrigido
            before_value: valor original
            after_value: valor corrigido
            description: descrição da correção
            cycle_id: ID do ciclo onde ocorreu

        Returns:
            LintObservation criada.
        """
        sym = symbol.upper()
        if sym not in self._pending:
            self._pending[sym] = []

        obs = LintObservation(
            symbol=sym,
            rule=rule,
            field_name=field_name,
            before_value=str(before_value),
            after_value=str(after_value),
            description=description,
            cycle_id=cycle_id,
        )
        self._pending[sym].append(obs)
        self._total_recorded += 1

        # Mantém apenas as últimas N observações pendentes
        if len(self._pending[sym]) > self._max_per_symbol:
            self._pending[sym] = self._pending[sym][-self._max_per_symbol:]

        logger.debug(f"[ObsFeedback] recorded {sym} rule={rule} {field_name}: {before_value}→{after_value}")
        return obs

    def record_from_lint_result(
        self,
        symbol: str,
        lint_result: object,
        cycle_id: str = "",
    ) -> int:
        """
        Registra observações a partir de um LintResult do AutoSignalLinter.

        Args:
            symbol: símbolo do ativo
            lint_result: objeto LintResult (de auto_signal_linter.py)
            cycle_id: ID do ciclo

        Returns:
            Número de observações registradas.
        """
        count = 0
        try:
            fixes = getattr(lint_result, "fixes", [])
            for fix in fixes:
                rule = getattr(fix, "rule", "unknown")
                field_n = getattr(fix, "field", "unknown")
                # LintFix usa before/after (Story 179 auto_signal_linter.py)
                before = str(getattr(fix, "before", getattr(fix, "original_value", "?")))
                after = str(getattr(fix, "after", getattr(fix, "corrected_value", "?")))
                desc = getattr(fix, "description", getattr(fix, "rule", ""))
                self.record_observation(
                    symbol=symbol,
                    rule=rule,
                    field_name=field_n,
                    before_value=before,
                    after_value=after,
                    description=desc,
                    cycle_id=cycle_id,
                )
                count += 1
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[ObsFeedback] record_from_lint_result failed: {exc}")
        return count

    def get_feedback_block(self, symbol: str, consume: bool = False) -> str:
        """
        Gera bloco de feedback formatado para injeção no prompt Vision.

        Formato:
            === Lint Observations from Previous Cycle: BTC ===
            Your previous signal had geometry issues that were auto-corrected:
              ⚠ confidence_clamp: confidence was 1.25 → corrected to 1.0. ...
              ⚠ long_sl_tp_swap: stop_loss was 51000 → corrected to 49000. ...
            Avoid these geometry errors in your next signal.

        Args:
            symbol: símbolo do ativo
            consume: se True, limpa as observações após gerar o bloco

        Returns:
            String formatada, ou "" se não há observações.
        """
        sym = symbol.upper()
        observations = self._pending.get(sym, [])
        if not observations:
            return ""

        lines = [
            f"=== Lint Observations from Previous Cycle: {sym} ===",
            "Your previous signal had geometry issues that were auto-corrected:",
        ]
        for obs in observations:
            lines.append(obs.to_prompt_line())
        lines.append("Avoid these geometry errors in your next signal.")

        if consume:
            self.clear(symbol)
            self._total_consumed += len(observations)

        return "\n".join(lines)

    def has_pending(self, symbol: str) -> bool:
        """Retorna True se há observações pendentes para o símbolo."""
        return bool(self._pending.get(symbol.upper()))

    def clear(self, symbol: str) -> int:
        """Limpa observações pendentes de um símbolo. Retorna quantidade removida."""
        sym = symbol.upper()
        count = len(self._pending.get(sym, []))
        self._pending.pop(sym, None)
        return count

    def summary(self) -> dict:
        pending_total = sum(len(v) for v in self._pending.values())
        return {
            "symbols_with_pending": len(self._pending),
            "pending_total": pending_total,
            "total_recorded": self._total_recorded,
            "total_consumed": self._total_consumed,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_loop: Optional[ObservationFeedbackLoop] = None


def get_observation_feedback_loop() -> ObservationFeedbackLoop:
    """Retorna o singleton global do ObservationFeedbackLoop."""
    global _loop
    if _loop is None:
        _loop = ObservationFeedbackLoop()
    return _loop


def reset_observation_feedback_loop() -> None:
    """Reseta o singleton — para testes."""
    global _loop
    _loop = None
