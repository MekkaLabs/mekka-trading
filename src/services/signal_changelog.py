"""
src/services/signal_changelog.py
===================================
Story 162 — SignalChangeLog: Structured Signal Diff + Auto-Commit Format.

Inspirado em:
  aider/coders/editblock_coder.py — SEARCH/REPLACE structured edit blocks
  aider/commands.py — auto-commit com mensagem descritiva gerada automaticamente

  "Aider auto-commits each change with a descriptive commit message that
   summarizes what was changed and why."

  "The SEARCH/REPLACE format makes it explicit what changed: the model must
   produce both the original and the replacement, making diffs unambiguous."

  "Every edit is tracked — the agent can explain what it changed and why
   through the commit message structure."

Adaptação para Mekka Trading:
  TradingSignal não tem histórico de mudanças entre ciclos.
  Quando Vision reavalia um símbolo no próximo ciclo, não há registro
  de "o que mudou desde o ciclo anterior".

  SignalChangeLog resolve isso:
  1. `diff(prev, curr)` — compara dois TradingSignals campo a campo
     e gera um ChangeRecord com CHANGED/ADDED/SAME fields
  2. `commit_message(signal, cycle_id)` — gera mensagem de commit
     estilo git inspirada no Aider auto-commit
  3. `format_for_audit(signal)` — one-liner para CycleEventLog
  4. `to_search_replace(field, old, new)` — formato SEARCH/REPLACE
     do Aider para diffs legíveis pelo LLM

Problema resolvido:
  - Não há rastreamento de "o que mudou no signal do BTC entre ciclos"
  - Não há mensagem descritiva de commit para cada decisão de trading
  - LLM Vision não tem contexto estruturado de "o ciclo anterior tinha X, agora Y"

Design:
  FieldChange — uma mudança específica em um campo do signal
  ChangeRecord — conjunto de mudanças entre dois signals
  SignalChangeLog — classe utilitária (métodos estáticos)
  get_signal_changelog() — singleton (histórico em memória)

Uso:
    from src.services.signal_changelog import SignalChangeLog, get_signal_changelog

    # Comparar signals
    record = SignalChangeLog.diff(prev_signal, curr_signal)
    print(record.commit_message())  # "feat(BTC): LONG→SHORT, conf 0.65→0.72, entry 50k→49.8k"

    # Salvar para histórico
    log = get_signal_changelog()
    log.record("BTC", prev_signal, curr_signal)
    recent = log.get_recent("BTC", n=5)
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Campos do TradingSignal para comparação
# ---------------------------------------------------------------------------

_SIGNAL_FIELDS: tuple[str, ...] = (
    "action", "confidence", "entry_price", "stop_loss", "take_profit",
    "size_pct", "leverage", "reasoning",
)

_NUMERIC_FIELDS: frozenset[str] = frozenset({
    "confidence", "entry_price", "stop_loss", "take_profit", "size_pct", "leverage",
})

_FORMAT_MAP: dict[str, str] = {
    "confidence": "{:.2f}",
    "entry_price": "${:,.0f}",
    "stop_loss": "${:,.0f}",
    "take_profit": "${:,.0f}",
    "size_pct": "{:.1%}",
    "leverage": "{:.0f}x",
}


def _fmt(field_name: str, value: Any) -> str:
    """Formata um valor de campo do signal para exibição."""
    try:
        fmt = _FORMAT_MAP.get(field_name)
        if fmt and value is not None:
            return fmt.format(float(value))
        if hasattr(value, "value"):  # Enum
            return str(value.value)
        return str(value)[:80]
    except Exception:  # noqa: BLE001
        return str(value)[:80]


# ---------------------------------------------------------------------------
# FieldChange e ChangeRecord
# ---------------------------------------------------------------------------

@dataclass
class FieldChange:
    """
    Mudança em um campo específico do TradingSignal.

    Inspirado no SEARCH/REPLACE block do Aider — explícito sobre
    o que mudou (old) e o que é agora (new).
    """
    field_name: str
    old_value: Any
    new_value: Any
    is_numeric: bool = False

    @property
    def delta(self) -> Optional[float]:
        """Delta numérico (para campos numéricos)."""
        try:
            if self.is_numeric:
                return float(self.new_value) - float(self.old_value)
        except Exception:  # noqa: BLE001
            pass
        return None

    @property
    def delta_pct(self) -> Optional[float]:
        """Delta percentual relativo ao valor anterior."""
        try:
            if self.is_numeric and float(self.old_value) != 0:
                return (float(self.new_value) - float(self.old_value)) / abs(float(self.old_value))
        except Exception:  # noqa: BLE001
            pass
        return None

    def to_search_replace(self) -> str:
        """
        Formato SEARCH/REPLACE do Aider — legível pelo LLM.

        Aider: "The SEARCH/REPLACE format makes it explicit what changed."

        Exemplo:
          <<<CHANGED action>>>
          LONG
          ===
          SHORT
          >>>
        """
        try:
            return (
                f"<<<CHANGED {self.field_name}>>>\n"
                f"{_fmt(self.field_name, self.old_value)}\n"
                f"===\n"
                f"{_fmt(self.field_name, self.new_value)}\n"
                f">>>"
            )
        except Exception:  # noqa: BLE001
            return f"<<<CHANGED {self.field_name}>>>"

    def to_compact(self) -> str:
        """Compacto para commit message: `action LONG→SHORT`"""
        try:
            old_s = _fmt(self.field_name, self.old_value)
            new_s = _fmt(self.field_name, self.new_value)
            return f"{self.field_name} {old_s}→{new_s}"
        except Exception:  # noqa: BLE001
            return self.field_name


@dataclass
class ChangeRecord:
    """
    Registro de mudanças entre dois TradingSignals consecutivos.

    Análogo ao git diff gerado pelo Aider após cada edição.
    """
    symbol: str
    changes: list[FieldChange] = field(default_factory=list)
    unchanged_fields: list[str] = field(default_factory=list)
    prev_cycle_id: str = ""
    curr_cycle_id: str = ""

    @property
    def has_action_change(self) -> bool:
        return any(c.field_name == "action" for c in self.changes)

    @property
    def changed_fields(self) -> list[str]:
        return [c.field_name for c in self.changes]

    @property
    def is_unchanged(self) -> bool:
        return len(self.changes) == 0

    def commit_message(self) -> str:
        """
        Gera mensagem de commit estilo Aider/git.

        Aider: "Aider auto-commits each change with a descriptive
        commit message that summarizes what was changed."

        Formato:
          feat(BTC): LONG→SHORT, conf 0.65→0.72, entry $50k→$49.8k
          feat(ETH): HOLD→LONG, +confidence 0.55, +entry $3200
          chore(SOL): no change (HOLD, conf=0.40)
        """
        try:
            if self.is_unchanged:
                return f"chore({self.symbol}): no signal change"

            parts = [c.to_compact() for c in self.changes[:4]]  # max 4 campos no título
            summary = ", ".join(parts)
            extra = f" +{len(self.changes) - 4} more" if len(self.changes) > 4 else ""
            return f"feat({self.symbol}): {summary}{extra}"
        except Exception:  # noqa: BLE001
            return f"feat({self.symbol}): signal updated"

    def to_search_replace_block(self) -> str:
        """
        Bloco completo SEARCH/REPLACE do Aider para todos os campos mudados.

        Legível pelo LLM para entender o que exatamente mudou no signal.
        """
        try:
            if not self.changes:
                return f"# {self.symbol}: no changes"
            blocks = [f"# Signal diff: {self.symbol}"]
            for ch in self.changes:
                blocks.append(ch.to_search_replace())
            return "\n\n".join(blocks)
        except Exception:  # noqa: BLE001
            return f"# {self.symbol}: diff unavailable"

    def to_audit_line(self) -> str:
        """
        One-liner compacto para CycleEventLog.

        Exemplo: "BTC: 3 changes [action, confidence, entry_price]"
        """
        try:
            if self.is_unchanged:
                return f"{self.symbol}: unchanged"
            fields = ", ".join(self.changed_fields[:5])
            return f"{self.symbol}: {len(self.changes)} changes [{fields}]"
        except Exception:  # noqa: BLE001
            return f"{self.symbol}: diff error"

    def to_dict(self) -> dict[str, Any]:
        """Serialização para EventBus payload."""
        try:
            return {
                "symbol": self.symbol,
                "total_changes": len(self.changes),
                "changed_fields": self.changed_fields,
                "unchanged_fields": self.unchanged_fields,
                "commit_message": self.commit_message(),
                "prev_cycle_id": self.prev_cycle_id,
                "curr_cycle_id": self.curr_cycle_id,
                "changes": [
                    {
                        "field": c.field_name,
                        "old": _fmt(c.field_name, c.old_value),
                        "new": _fmt(c.field_name, c.new_value),
                        "delta": c.delta,
                        "delta_pct": round(c.delta_pct, 4) if c.delta_pct is not None else None,
                    }
                    for c in self.changes
                ],
            }
        except Exception:  # noqa: BLE001
            return {"symbol": self.symbol, "error": "serialization_failed"}


# ---------------------------------------------------------------------------
# SignalChangeLog — utilitário + histórico em memória
# ---------------------------------------------------------------------------

class SignalChangeLog:
    """
    Compara TradingSignals consecutivos e mantém histórico de diffs.

    Inspirado em aider/commands.py auto-commit pattern:
    - Cada mudança de signal gera um ChangeRecord (análogo a um commit)
    - Histórico rolling por símbolo (max 50 records por símbolo)
    - diff() é estático — pode ser usado sem instância
    - Fail-silent em todos os paths

    Uso standalone (sem instância):
        record = SignalChangeLog.diff(prev, curr)

    Uso com histórico:
        log = get_signal_changelog()
        log.record("BTC", prev_signal, curr_signal)
        recent = log.get_recent("BTC", n=3)
    """

    _MAX_HISTORY_PER_SYMBOL = 50

    def __init__(self) -> None:
        self._history: dict[str, deque[ChangeRecord]] = defaultdict(
            lambda: deque(maxlen=self._MAX_HISTORY_PER_SYMBOL)
        )
        self._total_diffs: int = 0
        self._total_changes: int = 0

    # ------------------------------------------------------------------
    # Diff (estático — sem estado)
    # ------------------------------------------------------------------

    @staticmethod
    def diff(
        prev: Any,
        curr: Any,
        prev_cycle_id: str = "",
        curr_cycle_id: str = "",
    ) -> ChangeRecord:
        """
        Compara dois TradingSignals e retorna ChangeRecord.

        Inspirado no SEARCH/REPLACE do Aider — explícito sobre
        o que mudou, sem ambiguidade.

        Funciona com qualquer objeto que tenha os atributos do TradingSignal
        (duck-typing — aceita mocks, dataclasses, Pydantic models).

        Args:
            prev: signal anterior (ou None para "novo signal")
            curr: signal atual
            prev_cycle_id: ID do ciclo anterior (para rastreabilidade)
            curr_cycle_id: ID do ciclo atual

        Returns:
            ChangeRecord com todas as mudanças detectadas.
        """
        try:
            symbol = getattr(curr, "symbol", "UNKNOWN")
            record = ChangeRecord(
                symbol=symbol,
                prev_cycle_id=prev_cycle_id,
                curr_cycle_id=curr_cycle_id,
            )

            if prev is None:
                # Primeiro signal para este símbolo — marcar todos como "new"
                for fname in _SIGNAL_FIELDS:
                    curr_val = getattr(curr, fname, None)
                    if curr_val is not None:
                        record.changes.append(FieldChange(
                            field_name=fname,
                            old_value=None,
                            new_value=curr_val,
                            is_numeric=fname in _NUMERIC_FIELDS,
                        ))
                return record

            for fname in _SIGNAL_FIELDS:
                prev_val = getattr(prev, fname, None)
                curr_val = getattr(curr, fname, None)

                # Converter Enum para comparação
                if hasattr(prev_val, "value"):
                    prev_val = prev_val.value
                if hasattr(curr_val, "value"):
                    curr_val = curr_val.value

                # Comparar (com tolerância para floats)
                changed = False
                if fname in _NUMERIC_FIELDS:
                    try:
                        changed = abs(float(prev_val or 0) - float(curr_val or 0)) > 1e-9
                    except (TypeError, ValueError):
                        changed = prev_val != curr_val
                else:
                    changed = str(prev_val) != str(curr_val)

                if changed:
                    record.changes.append(FieldChange(
                        field_name=fname,
                        old_value=prev_val,
                        new_value=curr_val,
                        is_numeric=fname in _NUMERIC_FIELDS,
                    ))
                else:
                    record.unchanged_fields.append(fname)

            return record
        except Exception:  # noqa: BLE001
            symbol = getattr(curr, "symbol", "UNKNOWN") if curr else "UNKNOWN"
            return ChangeRecord(symbol=symbol)

    @staticmethod
    def format_for_audit(signal: Any, cycle_id: str = "") -> str:
        """
        One-liner compacto para CycleEventLog.emit().

        Exemplo:
          "BTC/LONG/conf=0.75/entry=$50000/sl=$48000/tp=$55000/rr=2.5"
        """
        try:
            action = getattr(signal, "action", "?")
            if hasattr(action, "value"):
                action = action.value
            symbol = getattr(signal, "symbol", "?")
            conf = getattr(signal, "confidence", 0)
            entry = getattr(signal, "entry_price", 0)
            sl = getattr(signal, "stop_loss", 0)
            tp = getattr(signal, "take_profit", 0)

            # Calcular R:R
            try:
                risk = abs(float(entry) - float(sl))
                reward = abs(float(tp) - float(entry))
                rr = f"rr={reward/risk:.1f}" if risk > 0 else "rr=?"
            except Exception:  # noqa: BLE001
                rr = "rr=?"

            cycle_suffix = f"/{cycle_id}" if cycle_id else ""
            return (
                f"{symbol}/{action}/conf={conf:.2f}/"
                f"entry=${entry:,.0f}/sl=${sl:,.0f}/tp=${tp:,.0f}/{rr}"
                f"{cycle_suffix}"
            )
        except Exception:  # noqa: BLE001
            return f"{getattr(signal, 'symbol', '?')}/format_error"

    @staticmethod
    def commit_message_from_signal(signal: Any, cycle_id: str = "") -> str:
        """
        Gera mensagem de commit estilo Aider para um signal sem previous.

        Aider: "Automatically generates a descriptive commit message."

        Exemplo:
          "feat(BTC/LONG): conf=0.75, entry=$50k, tp=$55k (rr=2.5) [cycle=abc123]"
        """
        try:
            action = getattr(signal, "action", "?")
            if hasattr(action, "value"):
                action = action.value
            symbol = getattr(signal, "symbol", "?")
            conf = getattr(signal, "confidence", 0)
            entry = getattr(signal, "entry_price", 0)
            tp = getattr(signal, "take_profit", 0)

            try:
                risk = abs(float(getattr(signal, "entry_price", 0)) - float(getattr(signal, "stop_loss", 0)))
                reward = abs(float(tp) - float(entry))
                rr = f"rr={reward/risk:.1f}" if risk > 0 else ""
            except Exception:  # noqa: BLE001
                rr = ""

            cycle_tag = f" [cycle={cycle_id[:8]}]" if cycle_id else ""
            rr_tag = f", {rr}" if rr else ""
            return (
                f"feat({symbol}/{action}): conf={conf:.2f}, "
                f"entry=${entry:,.0f}, tp=${tp:,.0f}{rr_tag}{cycle_tag}"
            )
        except Exception:  # noqa: BLE001
            return f"feat({getattr(signal, 'symbol', '?')}): signal emitted"

    # ------------------------------------------------------------------
    # Histórico em memória
    # ------------------------------------------------------------------

    def record(
        self,
        symbol: str,
        prev: Any,
        curr: Any,
        prev_cycle_id: str = "",
        curr_cycle_id: str = "",
    ) -> ChangeRecord:
        """
        Compara e armazena ChangeRecord no histórico.

        Rolling window: max 50 records por símbolo.
        """
        try:
            rec = self.diff(prev, curr, prev_cycle_id, curr_cycle_id)
            self._history[symbol].append(rec)
            self._total_diffs += 1
            self._total_changes += len(rec.changes)
            return rec
        except Exception:  # noqa: BLE001
            return ChangeRecord(symbol=symbol)

    def get_recent(self, symbol: str, n: int = 5) -> list[ChangeRecord]:
        """Retorna os N records mais recentes para um símbolo."""
        try:
            hist = self._history.get(symbol, deque())
            items = list(hist)
            return items[-n:] if len(items) > n else items
        except Exception:  # noqa: BLE001
            return []

    def get_last_change(self, symbol: str) -> Optional[ChangeRecord]:
        """Último ChangeRecord de um símbolo."""
        try:
            hist = self._history.get(symbol, deque())
            return hist[-1] if hist else None
        except Exception:  # noqa: BLE001
            return None

    def get_action_flips(self, symbol: str) -> list[ChangeRecord]:
        """
        Retorna todos os records onde action mudou (LONG→SHORT, HOLD→LONG, etc.).

        Útil para detectar instabilidade — "o Vision está flippando muito?".
        Inspirado em: Aider detecta edits redundantes que revertem mudanças anteriores.
        """
        try:
            return [r for r in self._history.get(symbol, []) if r.has_action_change]
        except Exception:  # noqa: BLE001
            return []

    def summary(self) -> dict[str, Any]:
        """Resumo para GET /api/signal-changelog."""
        try:
            symbols_tracked = list(self._history.keys())
            flip_counts = {
                sym: len(self.get_action_flips(sym))
                for sym in symbols_tracked
            }
            return {
                "total_diffs": self._total_diffs,
                "total_field_changes": self._total_changes,
                "symbols_tracked": symbols_tracked,
                "action_flips_by_symbol": flip_counts,
                "max_history_per_symbol": self._MAX_HISTORY_PER_SYMBOL,
            }
        except Exception:  # noqa: BLE001
            return {"error": "summary_failed"}


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: Optional[SignalChangeLog] = None


def get_signal_changelog() -> SignalChangeLog:
    """Retorna o SignalChangeLog singleton."""
    global _instance
    if _instance is None:
        _instance = SignalChangeLog()
    return _instance


def reset_signal_changelog() -> None:
    """Reset singleton — usado em testes."""
    global _instance
    _instance = None
