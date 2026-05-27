"""
src/prompt_engineering/adapter.py
==================================
Adaptação cross-provider de prompts (OpenAI ↔ Anthropic).

Reflete preferências documentadas de cada provider:
- **OpenAI/GPT**: prefere JSON estrito, schemas inline, instruções curtas
  em listas numeradas. `response_format=json_object` é o canônico.
- **Anthropic/Claude**: prefere XML tags semânticas, blocos `<example>`,
  estrutura hierárquica explícita.

Implementação é 100% determinística (regras de regex/string), sem chamadas
LLM. Garante reprodutibilidade e zero custo no CI.
"""

from __future__ import annotations

import re
from enum import Enum

from src.prompt_engineering.models import ExtractedPrompt


class Provider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


# Mapeamentos consolidados em uma única estrutura facilita manutenção.
# `Anthropic_section_tag` é a versão XML semântica que substitui o cabeçalho.
_SECTION_MAP: list[tuple[str, str]] = [
    # (cabeçalho original, tag XML semântica)
    ("ROLE",                  "role"),
    ("PURPOSE",               "purpose"),
    ("OUTPUT FORMAT",         "output_format"),
    ("METHOD",                "method"),
    ("PITFALLS",              "pitfalls"),
    ("ACCEPTANCE CRITERIA",   "acceptance_criteria"),
    ("EXAMPLES",              "examples"),
    ("HARD CONSTRAINTS",      "hard_constraints"),
    ("SYNTHESIS RULES",       "synthesis_rules"),
]


def adapt_to_anthropic(text: str) -> str:
    """
    Converte cabeçalhos textuais em tags XML.

    Antes:
        OUTPUT FORMAT
        ------
        Schema: { ... }

    Depois:
        <output_format>
        Schema: { ... }
        </output_format>
    """
    sections = _split_sections(text)
    out: list[str] = []
    if sections.get("_intro"):
        out.append(sections["_intro"].rstrip())

    for header_upper, tag in _SECTION_MAP:
        body = _find_section_body(sections, header_upper)
        if body:
            out.append(f"\n<{tag}>")
            out.append(body.rstrip())
            out.append(f"</{tag}>")
    return "\n".join(out).strip() + "\n"


def adapt_to_openai(text: str) -> str:
    """
    Compacta para o estilo OpenAI:
    - Remove tags XML semânticas (já vê schema sem isso).
    - Mantém cabeçalhos textuais simples.
    - Reforça `JSON object only` no fim.
    """
    # Remove tags XML que Anthropic adicionaria
    no_tags = re.sub(r"</?[a-z_]+(?:\s+name=\"[^\"]*\")?>", "", text)
    # Compacta múltiplas linhas em branco
    compact = re.sub(r"\n{3,}", "\n\n", no_tags).strip()
    # Reforça schema-strict se prompt menciona JSON, tem schema inline ({...}),
    # ou tem palavra "schema". Garante que o sinal de saída seja explícito.
    has_json_signal = (
        "json" in compact.lower()
        or "schema" in compact.lower()
        or re.search(r"\{[^}]*\}", compact) is not None
    )
    if has_json_signal and "Return ONLY" not in compact:
        compact += "\n\nReturn ONLY a single JSON object — no prose, no fences."
    return compact + "\n"


def adapt(prompt: ExtractedPrompt, target: Provider) -> str:
    """
    Adapta um ExtractedPrompt para o provider alvo.

    Retorna apenas o TEXTO adaptado — não muta o prompt original.
    """
    if target == Provider.ANTHROPIC:
        return adapt_to_anthropic(prompt.content)
    if target == Provider.OPENAI:
        return adapt_to_openai(prompt.content)
    raise ValueError(f"unsupported provider: {target}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_HEADER_RE = re.compile(
    # Cabeçalho começa em uppercase, pode conter qualquer caractere até o
    # final da linha (inclui parênteses com texto minúsculo), seguido de
    # linha de underline (--- ou ===). Lazy para não engolir blocos.
    r"^([A-Z][^\n]*?)\n[-=]{3,}\n",
    re.MULTILINE,
)


def _split_sections(text: str) -> dict[str, str]:
    """
    Quebra texto em seções pelos cabeçalhos `TITULO\\n----`.

    Retorna dict {header_upper: body}. Conteúdo antes do 1º cabeçalho
    fica em `_intro`.
    """
    sections: dict[str, str] = {}
    matches = list(_HEADER_RE.finditer(text))
    if not matches:
        sections["_intro"] = text
        return sections

    sections["_intro"] = text[: matches[0].start()].strip()

    for i, m in enumerate(matches):
        header = m.group(1).strip().upper()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[header] = text[start:end].strip()
    return sections


def _find_section_body(sections: dict[str, str], header_upper: str) -> str:
    """Busca tolerante: aceita 'OUTPUT FORMAT' e 'OUTPUT FORMAT (...)'."""
    for key, body in sections.items():
        if key.startswith(header_upper):
            return body
    return ""
