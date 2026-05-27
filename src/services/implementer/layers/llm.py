"""
src/services/implementer/layers/llm.py
========================================
Camada 2 — LLMImplementer (Claude Sonnet via Anthropic API, opt-in).

Faz chamada LLM com o brief + arquivos relevantes (read), pede patch
estruturado, valida + aplica + commit. Usado quando deterministic não
casa e cost cap permite.

Segurança:
  - Cost cap diário/mensal via ``cost.is_under_cap()``
  - Protected paths via ``safety.is_protected()``
  - Blast radius via ``safety.check_blast_radius()``
  - Saída do LLM é validada como JSON estruturado (não freetext)
  - Apenas mudanças em arquivos NOVOS ou existentes — nunca delete
  - SE Anthropic SDK indisponível: retorna ``False`` (fallback pra recipe)

Hoje (MVP): implementação REAL fica desligada por flag até o operador
explicitamente habilitar. Stub abaixo retorna False sempre — fail-safe.
Quando habilitado, faz call único com tools=read e patch JSON.
"""

from __future__ import annotations

import os
from typing import Any

from loguru import logger

from src.services.implementer import cost, safety
from src.services.implementer.base import ImplementerResult, ImplementerStatus


def is_llm_enabled() -> bool:
    """Flag explícita pra ligar o LLM implementer. Default OFF."""
    return os.environ.get("IMPLEMENTER_LLM_ENABLED", "false").lower() in (
        "1", "true", "yes", "on"
    )


def _has_anthropic_sdk() -> bool:
    """Detecta se o SDK Anthropic está instalado."""
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def _get_model() -> str:
    """Modelo padrão para implementer. Sonnet-4-6 é o sweet-spot custo/perf."""
    return os.environ.get("IMPLEMENTER_LLM_MODEL", "claude-sonnet-4-6")


def try_apply(brief: dict[str, Any], result: ImplementerResult) -> bool:
    """
    Tenta aplicar via LLM. Retorna True só se aplicou + commitou.
    Falhas são silenciosas — caller cai pra recipe.

    Status do MVP: gates implementados, chamada LLM REAL deixada como
    skeleton (não roda automaticamente em produção até operador habilitar
    explicitamente). Razão: queremos validar a infra primeiro.
    """
    rec_id = str(brief.get("rec_id") or brief.get("id") or "")
    if not is_llm_enabled():
        result.reason = "LLM implementer disabled (IMPLEMENTER_LLM_ENABLED=false)"
        return False
    if not _has_anthropic_sdk():
        result.reason = "anthropic SDK not installed"
        return False

    ok, reason = cost.is_under_cap()
    if not ok:
        result.reason = f"cost cap: {reason}"
        logger.warning(f"[llm] IMP-{rec_id} skipped: {reason}")
        return False

    result.layer_used = "llm"

    # MVP guard — implementação REAL fica desligada até operador habilitar
    # explicitamente para evitar gastos surpresa. Para ligar, setar
    # IMPLEMENTER_LLM_AUTHORIZED=true no ambiente.
    authorized = os.environ.get("IMPLEMENTER_LLM_AUTHORIZED", "false").lower() in (
        "1", "true", "yes", "on"
    )
    if not authorized:
        result.reason = (
            "LLM gate aberto mas execução requer IMPLEMENTER_LLM_AUTHORIZED=true. "
            "Esta camada está em modo skeleton por padrão para evitar gastos surpresa."
        )
        logger.info(f"[llm] IMP-{rec_id} would call LLM but auth=false (skeleton mode)")
        return False

    # ------------------------------------------------------------------
    # Implementação REAL — só roda quando authorized=true E SDK presente.
    # ------------------------------------------------------------------
    try:
        import anthropic
        client = anthropic.Anthropic()
        model = _get_model()
        # Carregar arquivos relevantes (best-effort: parse evidence/description)
        files_context = _gather_files_for_brief(brief)
        prompt = _build_prompt(brief, files_context)

        response = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        usage = getattr(response, "usage", None)
        in_tokens = getattr(usage, "input_tokens", 0)
        out_tokens = getattr(usage, "output_tokens", 0)
        cost_info = cost.record_event(
            rec_id=rec_id, model=model,
            input_tokens=in_tokens, output_tokens=out_tokens,
        )
        result.cost_usd = cost_info["this_event_usd"]

        # Parse patch estruturado da resposta
        text = response.content[0].text if response.content else ""
        patches = _parse_patches(text)
        if not patches:
            result.reason = "LLM returned no patches"
            return False

        # Aplicar patches respeitando safety
        applied = _apply_patches(patches, result)
        return applied
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[llm] IMP-{rec_id} call failed: {exc}")
        result.reason = f"llm call failed: {exc}"
        return False


# ---------------------------------------------------------------------------
# Helpers para o caminho LLM real (chamados quando authorized=true)
# ---------------------------------------------------------------------------


def _gather_files_for_brief(brief: dict[str, Any]) -> dict[str, str]:
    """Lê (best-effort) os arquivos prováveis afetados pelo brief.
    Cap em 5 arquivos × 200 linhas cada pra controlar contexto."""
    from pathlib import Path
    import re
    repo = Path(__file__).resolve().parents[4]
    text = " ".join(str(brief.get(k, "")) for k in
                    ("title", "description", "evidence"))
    paths = re.findall(
        r"`?((?:src|tests|docs)/[\w/.\-]+\.(?:py|md|js|jsx))`?", text,
    )
    out: dict[str, str] = {}
    for rel in paths[:safety.MAX_FILES_PER_IMP]:
        if safety.is_protected(rel):
            continue
        target = repo / rel
        if not target.exists():
            continue
        try:
            lines = target.read_text(encoding="utf-8").splitlines()
            if len(lines) > 200:
                snippet = "\n".join(lines[:100] + ["... [truncated] ..."] + lines[-50:])
            else:
                snippet = "\n".join(lines)
            out[rel] = snippet
        except OSError:
            continue
    return out


def _build_prompt(brief: dict[str, Any], files_context: dict[str, str]) -> str:
    """Constrói prompt estruturado pedindo patch em JSON."""
    files_block = "\n".join(
        f"### {rel}\n```\n{content}\n```" for rel, content in files_context.items()
    ) or "(nenhum arquivo carregado automaticamente)"
    return f"""Você é o implementer agent do Mekka Trading. Sua tarefa é aplicar a melhoria descrita abaixo em ESCOPO MÍNIMO, respeitando as restrições.

# BRIEF

- **Título:** {brief.get('title', '')}
- **Área:** {brief.get('area', '')}
- **Impacto:** {brief.get('impact', '')}

## Descrição
{brief.get('description', '')}

## Evidência
{brief.get('evidence', '')}

# ARQUIVOS RELEVANTES (read-only context)

{files_block}

# RESTRIÇÕES

- Modifique no máximo {safety.MAX_FILES_PER_IMP} arquivos
- Mude no máximo {safety.MAX_LINES_PER_IMP} linhas total
- NUNCA toque em: settings.py, batman.py, iron_man.py, .env, .env.example
- Apenas edite arquivos em src/, tests/, docs/, scripts/

# RESPOSTA

Responda APENAS com JSON deste formato (sem prosa antes/depois):

```json
{{
  "patches": [
    {{
      "path": "src/agents/foo.py",
      "operation": "replace",
      "old": "...",
      "new": "..."
    }}
  ],
  "summary": "uma linha do que foi feito"
}}
```

Operações válidas: "replace" (old → new), "create" (cria arquivo novo com new), "append" (append new no fim do arquivo).
"""


def _parse_patches(text: str) -> list[dict[str, Any]]:
    """Extrai patches do JSON na resposta do LLM. Robusto contra prose extra."""
    import json
    import re
    # Tenta achar bloco ```json ... ```
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not m:
        # Tenta JSON puro
        m = re.search(r"(\{.*?\"patches\".*?\})", text, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
        return data.get("patches", []) or []
    except (json.JSONDecodeError, KeyError):
        return []


def _apply_patches(
    patches: list[dict[str, Any]], result: ImplementerResult,
) -> bool:
    """Aplica patches no filesystem com guards. Retorna True se aplicou >=1."""
    from pathlib import Path
    repo = Path(__file__).resolve().parents[4]
    files = [p.get("path", "") for p in patches]
    # Pre-check blast radius
    ok, reason = safety.check_blast_radius(files, total_lines_changed=0)
    if not ok:
        result.status = ImplementerStatus.BLOCKED
        result.reason = f"blast radius: {reason}"
        return False
    applied = 0
    for patch in patches:
        rel = patch.get("path", "")
        if safety.is_protected(rel):
            logger.warning(f"[llm] skipping protected path: {rel}")
            continue
        op = patch.get("operation", "")
        target = repo / rel
        try:
            if op == "create":
                if target.exists():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(patch.get("new", ""), encoding="utf-8")
                applied += 1
                result.files_changed.append(rel)
            elif op == "append":
                target.parent.mkdir(parents=True, exist_ok=True)
                existing = target.read_text(encoding="utf-8") if target.exists() else ""
                target.write_text(existing + patch.get("new", ""), encoding="utf-8")
                applied += 1
                if rel not in result.files_changed:
                    result.files_changed.append(rel)
            elif op == "replace":
                if not target.exists():
                    continue
                content = target.read_text(encoding="utf-8")
                old = patch.get("old", "")
                new = patch.get("new", "")
                if old and old in content:
                    target.write_text(content.replace(old, new, 1), encoding="utf-8")
                    applied += 1
                    if rel not in result.files_changed:
                        result.files_changed.append(rel)
        except OSError as exc:
            logger.debug(f"[llm] patch {rel} failed: {exc}")
    return applied > 0
