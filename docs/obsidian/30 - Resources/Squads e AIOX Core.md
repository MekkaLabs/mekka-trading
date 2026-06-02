---
title: Squads e AIOX Core — inventário documentado
type: reference
status: ativo
tags: [aiox, squads, governance, mekka-trading]
created: 2026-05-26
updated: 2026-05-26
---

# Squads e AIOX Core — inventário documentado

> Investigação 2026-05-26 confirmou que o projeto **já tem** AIOX Core
> instalado e 13 squads disponíveis. Esta nota documenta o estado real
> para evitar reinvenção em sessões futuras.

## AIOX Core (framework instalado)

- **Localização:** `aiox-core/` (raiz do repo)
- **Tipo:** instalação completa SynkraAI AIOX v4
- **Sub-estrutura:** `bin/`, `docs/`, `packages/` (`aiox-install`, `aiox-pro-cli`), `squads/`, `tests/`, `.aiox-core/` interno (`cli`, `core`, `monitor`, `hooks`, `constitution.md`)
- **Como invocar:** via `aiox-core/bin/` ou scripts npm dentro de `aiox-core/package.json` — **não testado por esta sessão**
- **Posição:** referência arquitetural; runtime Python do Mekka não chama AIOX diretamente

## 13 squads em `squads/`

| Nome | Tema | Onde |
|---|---|---|
| `_example` | Template base | `squads/_example/` |
| `advisory-board` | Advisory / strategy | `squads/advisory-board/` |
| `brand-squad` | Branding | `squads/brand-squad/` |
| `c-level-squad` | C-level decision | `squads/c-level-squad/` |
| `claude-code-mastery` | Claude Code best practices | `squads/claude-code-mastery/` |
| `copy-squad` | Copywriting | `squads/copy-squad/` |
| `cybersecurity` | Pentest, AppSec, IR (15 agentes) | `squads/cybersecurity/` |
| `data-squad` | Data analytics | `squads/data-squad/` |
| `design-squad` | UX/UI design | `squads/design-squad/` |
| `hormozi-squad` | Offer/business design | `squads/hormozi-squad/` |
| `movement` | Movement building | `squads/movement/` |
| `storytelling` | Narrative | `squads/storytelling/` |
| `traffic-masters` | Paid traffic | `squads/traffic-masters/` |

Cada squad tem: `squad.yaml` (declaração AIOX), `agents/`, `tasks/`,
`workflows/`, opcional `data/`, `checklists/`, `config/`.

## Squads do runtime Mekka (`squads/squads.ts`)

Diferente dos squads YAML AIOX, este é um TypeScript declarando os
**squads operacionais do trading runtime**:

| Squad | Mandate | Members (heróis Python) |
|---|---|---|
| `alpha-risk-command` | Garantir paper-only + pre-trade validations | Batman, Nick Fury, Wolverine |
| `hyperliquid-mock-ops` | Manter conectividade mock + execution rehearsal | Iron Man, Professor X, Spider-Man |
| `market-intel-lab` | Gerar contexto de mercado + sinais de anomalia | Superman, Doctor Strange, Vision, Thor, Aquaman, Flash, Black Panther, Deadpool |

## Anexo `squads.zip` (avaliado 2026-05-26)

- **Origem:** `/Users/gustavovicente/Downloads/squads.zip`
- **Tamanho:** 3.3 MB, 384 arquivos
- **Conteúdo:** mesmos 13 squads listados acima
- **Diff vs `squads/`:** zero novidades — só falta `squads.ts` no zip (que é específico do Mekka)
- **Decisão:** não importar. Squads já estão versionados.

## Regras operacionais

1. **Não duplicar squads.** Se um novo agente couber em squad existente,
   estendê-lo via `squads/<nome>/agents/<novo>.md`.
2. **AIOX Core é referência, não runtime.** O runtime Python do Mekka
   (`src/agents/`, `src/services/`) NÃO importa nem instancia squads
   YAML. Eles são para uso via CLI AIOX, sessões futuras de
   reorganização ou consumo externo.
3. **Para qualquer squad ser executado**, o operador precisa invocar o
   framework AIOX explicitamente (não automatizado nesta sessão).

## Como Prometheus se relaciona

Prometheus é **agente Python** (`src/agents/prometheus.py`), não squad
YAML. Vive no roster do Mekka (`squads/squads.ts` poderá ser estendido
no futuro para incluir um squad dev/QA com Prometheus + Sage + Beast +
Mentor — não feito nesta sessão para evitar acoplamento desnecessário).

## Notas relacionadas

- [[Fontes de Verdade]]
- [[Fluxo Automático e Versionamento]]
- [[Prometheus]]
- ADR-004 — `docs/adr/ADR-004-second-brain-architecture.md`
