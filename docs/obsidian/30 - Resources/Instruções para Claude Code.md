---
title: Instruções para Claude Code
type: ai-guidance
status: ativo
tags: [guide, claude-code, ai, second-brain, mekka-trading]
created: 2026-05-26
updated: 2026-05-26
---

# Instruções para Claude Code — Trabalhando com o Segundo Cérebro

> Este documento é leitura obrigatória para qualquer sessão do Claude Code
> que vá consultar, atualizar ou criar notas no segundo cérebro do
> Mekka Trading. Define o que pode, o que não pode, e como.

## Antes de qualquer ação no vault

1. **Leia** [[Fontes de Verdade]] — para saber onde cada conhecimento mora.
2. **Leia** [[Guia de Manutenção do Segundo Cérebro]] — para saber como
   modificar coisas com segurança.
3. **Confirme** o caminho do vault canônico:
   `~/Documents/mekka-trading-obsidian`.

## Quando consultar o vault

Use o vault como contexto sempre que precisar entender:
- O papel de um agente (`20 - Areas/Agentes IA/<Herói>.md`)
- Uma decisão arquitetural histórica (`30 - Resources/Decisoes Tecnicas/`)
- Um procedimento operacional (`30 - Resources/Runbooks/`)
- O status do projeto (`10 - Projects/Mekka Trading/`)
- O significado de um termo (`30 - Resources/Glossario/Glossário.md`)
- Uma sessão de trabalho anterior (`60 - Daily/YYYY-MM-DD.md`)

**Prefira o vault para CONTEXTO; prefira o código para FATOS.**
Se uma nota diz "Batman tem 18 gates" e o código mostra 22 — o código
ganha, e a nota precisa ser atualizada.

## Quando atualizar o vault

### ✅ Faça
- Atualizar uma nota existente cujo conteúdo ficou estale (com motivo
  explícito no commit/mensagem ao usuário).
- Criar daily note para a sessão atual se ela tiver entregue commits ou
  decisões importantes.
- Mover notas do `00 - Inbox/` para a área correta após triagem.
- Criar nota nova para agente/serviço/decisão recém-introduzida —
  primeiro em `docs/obsidian/` (versionado), depois sincronizar.

### ⚠️ Pergunte ao usuário antes
- Apagar qualquer nota.
- Sobrescrever uma nota com mudanças não-aditivas.
- Reorganizar pastas (mover MOCs, renomear áreas).
- Atualizar configs em `.obsidian/`.

### ❌ Nunca
- Copiar `.env`, secrets, private keys, tokens para o vault.
- Copiar logs brutos, dumps de DB, snapshots de mercado.
- Editar notas diretamente no vault canônico se a mesma informação
  já vive em `docs/obsidian/` (versionada) — sempre edite no repo e
  sincronize.
- Rodar `obsidian_sync.py --apply --update` sem dry-run antes.
- Confiar em uma nota antiga sem checar com `git log` em `src/` que ela
  ainda descreve a realidade.

## Promoção: vault → repo

Quando uma nota nasce no vault (`00 - Inbox/` ou área) e prova valor
recorrente, **promova** para `docs/obsidian/`:

```bash
cp "~/Documents/mekka-trading-obsidian/20 - Areas/X/Nota Útil.md" \
   "docs/obsidian/20 - Areas/X/Nota Útil.md"
git add "docs/obsidian/20 - Areas/X/Nota Útil.md"
git commit -m "docs(obsidian): promover Nota Útil para fonte versionada"
```

A partir daqui, o sincronizador a manterá no vault.

## Workflow padrão de sessão Claude Code

1. **Entrar** — Ler `CLAUDE.md`, `SECOND_BRAIN.md`, este guia.
2. **Investigar** — Antes de editar, conferir estado real:
   - `git status`, `git log --oneline -10`
   - `ls src/agents/`, `cat src/config/settings.py` (o que pede o caso)
   - Notas relevantes no vault.
3. **Trabalhar** — código primeiro, notas como subproduto.
4. **Documentar** — se a sessão alterou agente/feature relevante:
   - Atualizar nota correspondente em `docs/obsidian/` (NÃO no vault).
   - Criar daily note se o handoff valer.
5. **Sincronizar** — `python scripts/obsidian_sync.py` (dry-run),
   depois `--apply` se nada surpreender.
6. **Auditar** (opcional, semanal): `python scripts/obsidian_coverage_audit.py`.

## Sinais de alerta

Pare e pergunte ao usuário se encontrar:
- Conflito não trivial entre nota e código (qual é a verdade?).
- Nota que cita um agente/serviço que não existe (Cypher, Domino, Forge,
  Trade Outcome Resolver são casos legítimos — outros podem ser erro).
- Mais de 10 conflitos no dry-run do sincronizador.
- `.obsidian/app.json` vazio (`{}`) — pode ter sido sobrescrito pelo
  Obsidian; restaurar de `docs/obsidian/.obsidian/app.json` com
  `--include-config --update`.
- Daily notes com gap > 5 dias úteis — perda de rastreabilidade.

## Casos especiais conhecidos

### Agentes "fantasmas" no vault
- **Cypher, Domino, Forge, Trade Outcome Resolver** — têm nota mas não
  são módulos em `src/agents/`. São sprites do dashboard (Cypher,
  Domino), funções dentro de outros agentes (Forge em Professor X,
  TOR em Cyclops). As notas são VÁLIDAS e descrevem conceitos
  legítimos do sistema.

### Configs do Obsidian
- O Obsidian sobrescreve `app.json` ao abrir o vault, podendo zerá-lo.
  A versão canônica vive em `docs/obsidian/.obsidian/app.json`.
  Se zerar: `python scripts/obsidian_sync.py --apply --force ".obsidian/app.json" --include-config`.

### Stories
- Numeração esparsa: stories 047, 074, 075, 141, 183, 186 existem mas
  números intermediários podem não — não tente "preencher gaps".

## Notas relacionadas

- [[Fontes de Verdade]]
- [[Guia de Manutenção do Segundo Cérebro]]
- [[Migração do Segundo Cérebro - 2026-05-26]]
