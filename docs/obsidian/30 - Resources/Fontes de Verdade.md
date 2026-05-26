---
title: Fontes de Verdade — Mekka Trading
type: policy
status: ativo
tags: [governance, second-brain, sot, mekka-trading]
created: 2026-05-26
updated: 2026-05-26
---

# Fontes de Verdade (Source of Truth)

> Política explícita de onde cada tipo de conhecimento nasce, vive e é
> consultado. Foi definida na migração do segundo cérebro em
> [[Migração do Segundo Cérebro - 2026-05-26]] e deve ser respeitada por
> todas as sessões — humanas ou Claude Code — daqui em diante.

## Princípio geral

**Cada artefato tem UM dono.** Onde ele nasce é onde ele é autoritativo.
O segundo cérebro DESCREVE o sistema; o repositório É o sistema.
Nunca duplicar conteúdo entre fontes — sempre LINKAR.

## Tabela canônica

| Domínio | Fonte de Verdade | Reflexo opcional no vault | Sincronização |
|---|---|---|---|
| **Código Python** | `src/` no repo | descrições em `20 - Areas/Arquitetura/` | manual; cada PR grande revisa notas afetadas |
| **Settings + secrets** | `.env` (local) + `src/config/settings.py` | nada (nunca em notas) | **nenhuma** — segredo nunca sai do disco local |
| **Stories canônicas** | `docs/stories/story-NNN-*.md` | `10 - Projects/Mekka Trading/06 - Stories and Roadmap/Stories/Story NNN.md` | manual; auditor reporta gaps |
| **ADRs canônicos** | `docs/adr/ADR-NNN-*.md` | `30 - Resources/Decisoes Tecnicas/ADR-NNN - *.md` (prosa) | manual; um quando ADR for promovido a peso de arquitetura |
| **HANDOFFs operacionais** | `docs/HANDOFF*.md` no repo | `60 - Daily/YYYY-MM-DD.md` (resumo) | manual após cada sessão grande |
| **Templates Obsidian** | `docs/obsidian/70 - Templates/` | `70 - Templates/` no vault | `scripts/obsidian_sync.py` |
| **MOCs, áreas, recursos comuns** | `docs/obsidian/` (versionado) | espelhado no vault | `scripts/obsidian_sync.py` (modo padrão copia apenas NEW) |
| **Daily notes operacionais** | vault `60 - Daily/` | nada (não voltam ao repo) | escrito direto no vault |
| **Inbox / captura rápida** | vault `00 - Inbox/` | nada | livre no vault; promove quando triar |
| **Análises, sessões, aprendizados** | vault (área correspondente) | quando estabilizar, promover para `docs/obsidian/` | manual |
| **Roster declarado** | `AGENTS.md` (repo) | `10 - Projects/Mekka Trading/03 - Agents/Roster de Heróis.md` | atualizar ambos quando agente novo |
| **Configurações Obsidian** | `docs/obsidian/.obsidian/` é fonte canônica para `app.json`, `community-plugins.json`, `daily-notes.json`, `templates.json` | `.obsidian/` do vault (cuidado: Obsidian sobrescreve) | `obsidian_sync.py --include-config` |
| **Configurações locais Obsidian** | `.obsidian/{workspace,workspaces,workspace-mobile,appearance,graph}.json` é local-only | nunca sai do vault | **gitignored** |

## Regras invioláveis

1. **Secrets nunca em notas.** Senhas, chaves de API, tokens de exchange,
   private keys — `.env` é o único lugar. Notas que precisem citar um
   segredo usam placeholder (`$HYPERLIQUID_PRIVATE_KEY`).
2. **Não duplicar conteúdo entre repo e vault.** Se uma decisão técnica
   está em `docs/adr/ADR-003-llm-structured-output-first.md`, a nota no
   vault REFERENCIA o ADR (com link relativo ou wikilink), não copia.
3. **Notas históricas não somem.** Quando uma área é descontinuada, vai
   para `40 - Archive/` com motivo no front-matter, não é apagada.
4. **Estado runtime nunca no vault.** Logs (`logs/`), DB (`data/`),
   métricas e snapshots de mercado são L4 (runtime) — pertencem ao disco,
   não ao segundo cérebro. Aprendizado extraído deles pode virar nota.
5. **Vault é DESCRITIVO, não EXECUTIVO.** Uma nota pode dizer "para
   iniciar o dashboard, rode `python scripts/start.sh`" — mas o script
   real vive em `scripts/`. Vault não roda nada.

## Ciclo de promoção

```
Captura no Inbox (vault)
        ↓ triagem semanal
Nota em Area/Resource (vault)
        ↓ se estabiliza e vira referência
Promovido para docs/obsidian/ (repo, versionado)
        ↓ obsidian_sync.py
Espelhado de volta no vault para consulta diária
```

## Notas relacionadas

- [[Guia de Manutenção do Segundo Cérebro]]
- [[Instruções para Claude Code]]
- [[Migração do Segundo Cérebro - 2026-05-26]]
- [[Sistema de Documentação]]
