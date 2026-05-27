"""
src/services/implementer/layers/recipe.py
===========================================
Camada 3 — RecipeImplementer (fallback universal).

Quando deterministic + LLM falham (ou estão desabilitados), o RecipeImplementer
escreve um arquivo ``docs/improvement-queue/recipes/IMP-xxxxxx-recipe.md`` com:

  - Resumo do brief
  - Passos sugeridos para o humano/Claude Code executar
  - Arquivos prováveis afetados
  - Checklist de validação

NÃO modifica código de produção — apenas gera documentação executável.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.services.implementer.base import ImplementerResult, ImplementerStatus

_REPO = Path(__file__).resolve().parents[4]
_RECIPES_DIR = _REPO / "docs" / "improvement-queue" / "recipes"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_slug(s: str, maxlen: int = 50) -> str:
    s = re.sub(r"[^\w\s\-]", "", s or "")
    s = re.sub(r"\s+", "-", s).strip().lower()
    return s[:maxlen] or "imp"


def _suggest_files(brief: dict[str, Any]) -> list[str]:
    """Extrai paths plausíveis mencionados em evidence/description."""
    text = " ".join(str(brief.get(k, "")) for k in
                    ("title", "description", "evidence"))
    # Acha src/foo/bar.py, tests/foo.py, docs/foo.md, etc.
    paths = re.findall(r"`?((?:src|tests|docs|scripts)/[\w/.\-]+\.(?:py|md|js|jsx|css|html|yml|yaml|toml))`?", text)
    # Dedup preservando ordem
    seen, out = set(), []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out[:8]


def _render(brief: dict[str, Any]) -> str:
    rec_id = brief.get("rec_id") or brief.get("id") or "?"
    title = brief.get("title", "(sem título)")
    area = brief.get("area", "?")
    impact = brief.get("impact", "?")
    description = (brief.get("description") or "").strip() or "_(sem descrição)_"
    evidence = (brief.get("evidence") or "").strip() or "_(sem evidência)_"
    rationale = (brief.get("rationale") or "").strip() or "_(sem rationale)_"
    files = _suggest_files(brief)

    files_block = (
        "\n".join(f"- `{f}`" for f in files) if files else "- _(nenhum detectado)_"
    )

    return f"""---
rec_id: "{rec_id}"
type: implementation-recipe
area: {area}
impact: {impact}
generated_at: {_now_iso()}
auto_generated: true
---

# Recipe IMP-{rec_id} — {title}

> Esta IMP não casou com nenhum padrão automático do DeterministicImplementer
> e o LLMImplementer não foi acionado (desabilitado ou cap atingido). Este
> arquivo descreve os passos sugeridos para implementação manual (humano ou
> Claude Code).

## Contexto

- **Área:** `{area}`
- **Impacto:** `{impact}`

## Descrição

{description}

## Por que importa

{rationale}

## Evidência

{evidence}

## Arquivos prováveis afetados

{files_block}

## Passos sugeridos

1. Ler o brief original em `docs/improvement-queue/IMP-{rec_id}.md`.
2. Confirmar escopo e blast radius (≤5 arquivos, ≤500 linhas recomendado).
3. Criar branch local: `git checkout -b imp/IMP-{rec_id}`
4. Implementar mudanças nos arquivos listados acima.
5. Rodar validação:
   ```bash
   ruff check src/
   mypy src/  # se aplicável
   pytest tests/ -q
   ```
6. Commit com tag IMP no subject:
   ```bash
   git commit -m "[IMP-{rec_id}] {title}"
   ```
7. Atualizar `dev_state` para `pr_open` via dashboard ou rodar
   `python3 scripts/sync_imp_commits.py`.
8. Bridge automaticamente:
   - tira snapshot Sage DEPOIS
   - cria nota de review em `30 - Resources/Reviews/` no vault canônico

## Checklist de validação

- [ ] Mudança implementada conforme descrição
- [ ] Mitigações do Galactus endereçadas (ver brief)
- [ ] Testes adicionados/atualizados; `ruff` e `mypy` passam
- [ ] Validado em paper/testnet antes de qualquer impacto em produção
- [ ] Commit subject contém `[IMP-{rec_id}]`

## Notas relacionadas

- Brief original: [[IMP-{rec_id}]]
- [[Departamento de Melhoria Contínua]]
- [[Beast]]
"""


def write_recipe(brief: dict[str, Any], result: ImplementerResult) -> str:
    """
    Escreve recipe.md e atualiza ``result``. Retorna o path absoluto criado.
    Marca ``result.status = RECIPE_ONLY``.
    """
    rec_id = brief.get("rec_id") or brief.get("id") or "unknown"
    title = brief.get("title", "")
    fname = f"IMP-{rec_id}-{_safe_slug(title)}-recipe.md"
    try:
        _RECIPES_DIR.mkdir(parents=True, exist_ok=True)
        target = _RECIPES_DIR / fname
        target.write_text(_render(brief), encoding="utf-8")
        result.status = ImplementerStatus.RECIPE_ONLY
        result.layer_used = "recipe"
        try:
            result.recipe_path = str(target.relative_to(_REPO))
        except ValueError:
            # _RECIPES_DIR foi monkeypatched pra fora do repo (test scenarios)
            result.recipe_path = str(target)
        result.reason = "no deterministic pattern + LLM disabled/blocked"
        logger.info(f"[recipe] IMP-{rec_id} → {target.name}")
        return str(target)
    except OSError as exc:
        logger.warning(f"[recipe] write failed for IMP-{rec_id}: {exc}")
        result.status = ImplementerStatus.FAILED
        result.reason = f"recipe write failed: {exc}"
        return ""
