---
title: Guia de Manutenção do Segundo Cérebro
type: guide
status: ativo
tags: [guide, second-brain, operations, mekka-trading]
created: 2026-05-26
updated: 2026-05-26
---

# Guia de Manutenção do Segundo Cérebro

> Manual operacional para manter o vault vivo, alinhado com o código e
> útil. Complementa [[Fontes de Verdade]] (política) e
> [[Guia de Uso do Vault]] (fluxo diário).

## Topologia

```
~/Documents/Mekka-Trading/        ← repositório (código + docs versionados)
├── src/                          ← código (fonte de verdade da implementação)
├── docs/
│   ├── stories/                  ← stories canônicas
│   ├── adr/                      ← ADRs canônicos
│   ├── HANDOFF*.md               ← handoffs operacionais
│   └── obsidian/                 ← parte VERSIONADA do segundo cérebro
└── scripts/
    ├── obsidian_sync.py          ← sincronizador docs/obsidian → vault
    ├── obsidian_coverage_audit.py ← auditoria de cobertura
    └── obsidian_normalize.py     ← normaliza wikilinks (legacy)

~/Documents/mekka-trading-obsidian/   ← VAULT CANÔNICO (uso diário)
~/Documents/mekka-trading-obsidian.backup-20260526-162005/  ← backup pré-migração
```

## Ciclo de manutenção (recomendado)

### Diário (5 min)
- Processar `00 - Inbox`: mover capturas para área/recurso correto.
- Daily note do dia (`60 - Daily/YYYY-MM-DD.md`) com sessão de trabalho.

### Após cada PR/commit grande
- Se mudou um agente: atualizar a nota correspondente em
  `20 - Areas/Agentes IA/<Herói>.md`.
- Se criou serviço novo em `src/services/`: decidir se merece nota em
  `20 - Areas/Arquitetura/` ou se é citado em nota de feature.
- Se entregou story: atualizar status em `Stories e Roadmap` e criar
  nota da story se ainda não existir.
- Se tomou decisão de design não óbvia: novo ADR (em `docs/adr/` E em
  `30 - Resources/Decisoes Tecnicas/`).

### Semanal (15 min)
- `python scripts/obsidian_coverage_audit.py` — ver gaps.
- `python scripts/obsidian_sync.py` (dry-run) — ver novos arquivos do
  repo prontos para entrar no vault.
- Review Semanal em `30 - Resources/Reviews/Review Semanal.md`.

### Quando atualizar configs do Obsidian
- Editar em `docs/obsidian/.obsidian/` (versionado).
- `python scripts/obsidian_sync.py --apply --include-config --update`
  para propagar ao vault (backup automático).

## Comandos essenciais

```bash
# Dry-run: ver o que aconteceria
python scripts/obsidian_sync.py

# Aplicar: copia só NEW (mais seguro)
python scripts/obsidian_sync.py --apply

# Aplicar + resolver conflitos com backup
python scripts/obsidian_sync.py --apply --update

# Forçar overwrite de UM arquivo (com backup)
python scripts/obsidian_sync.py --apply --force "70 - Templates/Daily Note.md"

# Auditoria de cobertura
python scripts/obsidian_coverage_audit.py

# Auditoria como JSON (CI/automação)
python scripts/obsidian_coverage_audit.py --json
```

## Exclusões que o sincronizador respeita

**Hard-coded (sempre ignoradas):**
- `10 - Projects/10 - Projects.md`
- `10 - Projects/Projeto - Mekka Trading.md`
- `10 - Projects/_Projects.md`
  → o vault organiza projetos sob `10 - Projects/Mekka Trading/` e não
  precisa dos índices de PARA duplicados.
- `.obsidian/workspace.json`, `workspaces.json`, `workspace-mobile.json`
- `.obsidian/cache/`
- `.obsidian/appearance.json`, `graph.json`
- `.trash/`

**Soft (opt-in com `--include-config`):**
- `.obsidian/app.json`
- `.obsidian/core-plugins.json`
- `.obsidian/community-plugins.json`
- `.obsidian/daily-notes.json`
- `.obsidian/templates.json`

> Configs do Obsidian têm efeito colateral imediato no vault aberto.
> O sincronizador exige opt-in explícito para evitar surpresas (ex:
> trocar `newLinkFormat` quebra autocompletes em andamento).

## Resolução de conflitos

Conflito = mesmo path existe nos dois lados com conteúdo diferente.

1. **Versão do vault é a boa?** Faça o upgrade na origem:
   ```bash
   cp ~/Documents/mekka-trading-obsidian/<path> docs/obsidian/<path>
   ```
2. **Versão do repo é a boa?**
   ```bash
   python scripts/obsidian_sync.py --apply --force "<path>"
   ```
3. **Mistura?** Edite manualmente; deixe explícito o que veio de cada
   lado.

Em qualquer caso, o sincronizador cria `<path>.bak-YYYYMMDD-HHMMSS`
antes de qualquer overwrite explícito.

## Saúde do segundo cérebro — KPIs

| Métrica | Como medir | Limite saudável |
|---|---|---|
| Notas órfãs (zero backlinks) | Obsidian → Graph view → Orphan filter | < 10% do total |
| Inbox processado | Contagem em `00 - Inbox/` | < 5 notas pendentes |
| Daily notes em dias úteis | `obsidian_coverage_audit.py` reporta gaps | 0 gaps no mês corrente |
| Agentes sem nota | auditor | 0 |
| Stories sem nota | auditor | < 10 (range recente) |
| ADRs sem reflexo | auditor | 0 |

## Anti-padrões a evitar

- ❌ Editar a mesma decisão em 2 lugares (vault + repo) sem promover.
- ❌ Copiar `.env` ou logs para o vault "para ter referência".
- ❌ Apagar notas antigas — sempre archive (`40 - Archive/`).
- ❌ Criar nota sem linkar a pelo menos um MOC.
- ❌ Confiar no Obsidian Sync proprietário para o repo — usar git +
  `obsidian_sync.py`.
- ❌ Sincronizar sem dry-run primeiro.

## Notas relacionadas

- [[Fontes de Verdade]]
- [[Instruções para Claude Code]]
- [[Guia de Uso do Vault]]
- [[Migração do Segundo Cérebro - 2026-05-26]]
