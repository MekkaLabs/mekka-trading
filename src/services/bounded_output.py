"""
src/services/bounded_output.py
================================
Story 157 — BoundedOutput: ACI Output Limiter.

Inspirado no sistema de output bounding do SWE-agent (SWE-agent/SWE-agent):

  "100-line windowed viewer + line-targeted edit + syntax-checked autosave
   roughly doubles SWE-Bench score versus raw bash."

  "if output length < 10,000 characters → full output; else → truncate"

  "search results limited to max 50 hits to prevent overwhelming the LM's
   context window"

  "last_n_observations drops all but the most recent N observations from
   the messages array, keeping actions and thoughts but blanking out the
   stdout of older steps"

Problema resolvido no Mekka Trading:
- Payloads de audit_log e CycleEventLog podem crescer indefinidamente
- LLM prompts do Vision podem incluir análises gigantescas sem truncação
- Respostas do dashboard podem retornar MB de dados para o frontend
- EventBus payloads com stack traces longas ocupam memória desnecessária

Design:
  BoundedOutput — classe utilitária com métodos estáticos (sem estado)
  truncate_str() — trunca string longa com marcador [...N chars omitted]
  truncate_list() — limita lista a N itens com contagem do total
  truncate_dict() — aplica recursivamente (profundidade configurável)
  truncate_output() — dispatcher: str/list/dict/any → truncado
  format_observation() — padrão SWE-agent: returncode + output (max 10k chars)

Uso típico:
    from src.services.bounded_output import BoundedOutput

    # Truncar texto de análise antes de incluir no prompt do Vision
    safe_analysis = BoundedOutput.truncate_str(raw_analysis, max_chars=4000)

    # Truncar lista de trades para o dashboard
    safe_trades = BoundedOutput.truncate_list(all_trades, max_items=50)

    # Truncar payload de evento para o EventBus
    safe_payload = BoundedOutput.truncate_dict(big_payload, max_chars=2000)

    # Formatar observação de execução (padrão SWE-agent)
    obs = BoundedOutput.format_observation(returncode=0, output=stdout_text)
"""

from __future__ import annotations

from typing import Any, Union

# Defaults alinhados com SWE-agent
_DEFAULT_MAX_CHARS = 10_000   # mini-SWE-agent: se < 10k → full, else truncate
_DEFAULT_MAX_ITEMS = 50       # SWE-agent: max 50 search results
_DEFAULT_MAX_DEPTH = 3        # recursão máxima no truncate_dict
_ELLIPSIS_SUFFIX = "... [{remaining} chars omitted]"
_LIST_SUFFIX = "... [{remaining} more items omitted, total={total}]"


class BoundedOutput:
    """
    Utilitário para truncar saídas longas antes de inseri-las em prompts LLM.

    Todos os métodos são estáticos — sem estado, sem instanciação necessária.
    Todos os métodos são fail-silent: nunca levantam exceção (retornam
    o valor original em caso de erro).

    Design inspirado no ACI (Agent-Computer Interface) do SWE-agent:
    - Saídas bounded = contexto do LLM previsível
    - Marcadores explícitos de truncação = o LLM sabe o que está faltando
    - Limites configuráveis = não quebramos comportamentos existentes
    """

    # ------------------------------------------------------------------
    # String truncation
    # ------------------------------------------------------------------

    @staticmethod
    def truncate_str(
        text: str,
        max_chars: int = _DEFAULT_MAX_CHARS,
        suffix_template: str = _ELLIPSIS_SUFFIX,
    ) -> str:
        """
        Trunca uma string se exceder max_chars.

        O sufixo indica quantos chars foram omitidos, seguindo a convenção
        do SWE-agent de ser explícito sobre o que foi cortado.

        Args:
            text: string a truncar
            max_chars: limite em caracteres (default 10.000 — padrão mini-SWE-agent)
            suffix_template: template do sufixo, com variável {remaining}

        Returns:
            String original se len <= max_chars, ou truncada com sufixo.
        """
        try:
            if len(text) <= max_chars:
                return text
            remaining = len(text) - max_chars
            suffix = suffix_template.format(remaining=remaining)
            return text[:max_chars] + suffix
        except Exception:  # noqa: BLE001
            return text  # fail-silent

    @staticmethod
    def truncate_str_head_tail(
        text: str,
        max_chars: int = _DEFAULT_MAX_CHARS,
        head_ratio: float = 0.6,
    ) -> str:
        """
        Trunca mantendo início e fim (head + tail) — útil para stack traces
        onde o início (exception type) e o fim (line number) são mais valiosos.

        head_ratio: proporção do max_chars alocada para o início (default 60%).
        """
        try:
            if len(text) <= max_chars:
                return text
            head_chars = int(max_chars * head_ratio)
            tail_chars = max_chars - head_chars
            omitted = len(text) - head_chars - tail_chars
            return (
                text[:head_chars]
                + f"\n... [{omitted} chars omitted] ...\n"
                + text[-tail_chars:]
            )
        except Exception:  # noqa: BLE001
            return text

    # ------------------------------------------------------------------
    # List truncation
    # ------------------------------------------------------------------

    @staticmethod
    def truncate_list(
        items: list,
        max_items: int = _DEFAULT_MAX_ITEMS,
    ) -> list:
        """
        Limita uma lista a max_items.

        Retorna a lista original se len <= max_items.
        Se truncada, adiciona string de summary como último elemento.

        Padrão SWE-agent: "max 50 search results; if more, agent is prompted
        to refine the query."
        """
        try:
            if len(items) <= max_items:
                return items
            remaining = len(items) - max_items
            return list(items[:max_items]) + [
                _LIST_SUFFIX.format(remaining=remaining, total=len(items))
            ]
        except Exception:  # noqa: BLE001
            return items

    # ------------------------------------------------------------------
    # Dict truncation
    # ------------------------------------------------------------------

    @staticmethod
    def truncate_dict(
        data: dict,
        max_chars: int = _DEFAULT_MAX_CHARS,
        max_items: int = _DEFAULT_MAX_ITEMS,
        depth: int = 0,
        max_depth: int = _DEFAULT_MAX_DEPTH,
    ) -> dict:
        """
        Aplica truncação recursiva a um dict.

        - Strings: truncadas a max_chars
        - Listas: limitadas a max_items
        - Dicts aninhados: recursão até max_depth

        Retorna um novo dict (não muta o original).
        """
        try:
            result = {}
            for key, value in data.items():
                if isinstance(value, str):
                    result[key] = BoundedOutput.truncate_str(value, max_chars)
                elif isinstance(value, list):
                    truncated = BoundedOutput.truncate_list(value, max_items)
                    result[key] = truncated
                elif isinstance(value, dict) and depth < max_depth:
                    result[key] = BoundedOutput.truncate_dict(
                        value, max_chars, max_items, depth + 1, max_depth
                    )
                else:
                    result[key] = value
            return result
        except Exception:  # noqa: BLE001
            return data

    # ------------------------------------------------------------------
    # Generic dispatcher
    # ------------------------------------------------------------------

    @staticmethod
    def truncate_output(
        data: Any,
        max_chars: int = _DEFAULT_MAX_CHARS,
        max_items: int = _DEFAULT_MAX_ITEMS,
    ) -> Any:
        """
        Dispatcher genérico: trunca qualquer tipo de dado.

        - str → truncate_str
        - list → truncate_list
        - dict → truncate_dict
        - outros → retorna como está

        Uso típico para payload de eventos antes de serializar para JSON.
        """
        try:
            if isinstance(data, str):
                return BoundedOutput.truncate_str(data, max_chars)
            if isinstance(data, list):
                return BoundedOutput.truncate_list(data, max_items)
            if isinstance(data, dict):
                return BoundedOutput.truncate_dict(data, max_chars, max_items)
            return data
        except Exception:  # noqa: BLE001
            return data

    # ------------------------------------------------------------------
    # SWE-agent observation format
    # ------------------------------------------------------------------

    @staticmethod
    def format_observation(
        returncode: int,
        output: str,
        max_chars: int = _DEFAULT_MAX_CHARS,
        command: str = "",
    ) -> str:
        """
        Formata uma observação no estilo SWE-agent mini.

        mini-SWE-agent:
          "if output length < 10,000 → returncode + output; else → truncate"

        Usado para formatar resultados de execução (IronMan paper trades,
        Wolverine recovery actions) antes de logar no audit trail.
        """
        try:
            bounded = BoundedOutput.truncate_str(output.strip(), max_chars)
            cmd_line = f"$ {command}\n" if command else ""
            return f"{cmd_line}[returncode={returncode}]\n{bounded}"
        except Exception:  # noqa: BLE001
            return str(output)

    # ------------------------------------------------------------------
    # LLM prompt helpers
    # ------------------------------------------------------------------

    @staticmethod
    def bound_prompt_section(
        title: str,
        content: str,
        max_chars: int = 4_000,
    ) -> str:
        """
        Formata uma seção de prompt LLM com título e conteúdo bounded.

        Padrão SWE-agent 100-line windowed viewer: conteúdo com limite
        explícito para prevenir context overflow em análises longas.

        Uso no Vision:
            prompt += BoundedOutput.bound_prompt_section(
                "Market Analysis", raw_analysis, max_chars=4000
            )
        """
        try:
            bounded = BoundedOutput.truncate_str(content, max_chars)
            separator = "-" * 40
            return f"\n{separator}\n## {title}\n{separator}\n{bounded}\n"
        except Exception:  # noqa: BLE001
            return f"\n## {title}\n{content}\n"

    @staticmethod
    def last_n_observations(
        observations: list[dict],
        n: int = 5,
        keep_keys: tuple[str, ...] = ("action", "thought", "event_type", "symbol"),
    ) -> list[dict]:
        """
        SWE-agent `last_n_observations` history processor.

        Mantém apenas as últimas N observações completas.
        Para observações mais antigas: mantém apenas as chaves `keep_keys`
        (actions e thoughts), descarta stdout/payload grande.

        Padrão SWE-agent: "drops all but the most recent N observations from
        the messages array, keeping actions and thoughts in place but
        blanking out the stdout of older steps"

        Args:
            observations: lista de dicts de observação/evento
            n: número de observações recentes a manter intactas
            keep_keys: chaves a preservar nas observações antigas

        Returns:
            Lista processada (não muta a original).
        """
        try:
            if len(observations) <= n:
                return observations

            old = observations[:-n]
            recent = observations[-n:]

            # Observações antigas: manter apenas keep_keys
            old_trimmed = [
                {k: v for k, v in obs.items() if k in keep_keys}
                for obs in old
            ]
            return old_trimmed + recent
        except Exception:  # noqa: BLE001
            return observations

    # ------------------------------------------------------------------
    # Summary helpers (convenience)
    # ------------------------------------------------------------------

    @staticmethod
    def safe_repr(value: Any, max_chars: int = 200) -> str:
        """
        Representação segura (truncada) de qualquer valor.

        Útil para logging e debug sem risco de flood.
        """
        try:
            raw = repr(value)
            return BoundedOutput.truncate_str(raw, max_chars)
        except Exception:  # noqa: BLE001
            return "<repr_error>"

    @staticmethod
    def count_tokens_approx(text: str) -> int:
        """
        Estimativa rápida de tokens (sem tiktoken).

        Heurística: ~4 chars por token (OpenAI GPT-4 média).
        Usada pelo ContextWindowTracker para alertas.
        """
        try:
            if not text:
                return 0
            return max(1, len(text) // 4)
        except Exception:  # noqa: BLE001
            return 0
