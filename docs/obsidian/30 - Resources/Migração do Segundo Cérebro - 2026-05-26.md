---
title: Migração do Segundo Cérebro - 2026-05-26
type: resource
status: done
created: 2026-05-26
updated: 2026-05-26
tags: [obsidian, migration, second-brain, mekka-trading]
---

# Migração do Segundo Cérebro - 2026-05-26

## Decisão

O vault canônico do projeto Mekka Trading passa a ser:

- `~/Documents/mekka-trading-obsidian`

## Fontes analisadas

- `~/Documents/Mekka-Trading/docs/obsidian`
- `~/Documents/Gustavo-Obsidian/Mekka-Trading`
- `~/Documents/Obsidian Vault/mekka-trading`

## Backup criado antes da migração

- `~/Documents/mekka-trading-obsidian.backup-20260526-162005`

## Estratégia aplicada

- Preservar o vault atual como base.
- Importar conteúdo faltante de `docs/obsidian` sem sobrescrever arquivos já existentes.
- Sobrescrever apenas arquivos claramente melhores na versão do projeto:
  - `Home.md`
  - `70 - Templates/Template - ADR.md`
- Importar configurações úteis do Obsidian:
  - `community-plugins.json`
  - `daily-notes.json`
  - `templates.json`
- Manter a estrutura de projeto já existente em `10 - Projects/Mekka Trading/`.

## Conteúdo incorporado

- `00 - Inbox`
- `20 - Areas`
- `30 - Resources`
- `40 - Archive`
- `50 - MOCs`
- `60 - Daily`
- `70 - Templates`
- `80 - Attachments`
- `README.md`
- `10 - Projects/Departamento de Melhoria Contínua.md`

## Estado final após migração

- `162` notas Markdown
- `.obsidian` com configurações essenciais sincronizadas
- MOCs completos
- Áreas completas de arquitetura, agentes, operacional, risco e trading
- Runbooks, glossário, ADRs e referências externas disponíveis
- Daily notes do projeto presentes

## Arquivos intencionalmente não migrados

Estes arquivos existem em `docs/obsidian`, mas não foram copiados porque
duplicariam a organização já adotada no vault canônico:

- `10 - Projects/10 - Projects.md`
- `10 - Projects/Projeto - Mekka Trading.md`
- `10 - Projects/_Projects.md`

Motivo:

- o vault canônico já usa a estrutura `10 - Projects/Mekka Trading/...`
- copiar esses arquivos criaria duplicidade conceitual e ruído de wikilinks

## Observações importantes

- `README.md` do repositório principal está defasado em relação ao estado real do sistema.
- `HANDOFF.md` e os handoffs recentes em `docs/` são hoje a fonte mais confiável para o estado operacional.
- O runtime atual está em Binance testnet live, enquanto parte da documentação histórica ainda descreve paper-only/Hyperliquid mock.

## Próximo passo recomendado

Criar uma rotina de sincronização dirigida entre:

- `docs/obsidian` (vault versionado no repo)
- `mekka-trading-obsidian` (vault canônico operacional)

Regras sugeridas:

- `mekka-trading-obsidian` como destino final de uso
- `docs/obsidian` como fonte técnica versionada
- merges seletivos para `Home.md`, `Projeto - Mekka Trading`, templates e notas de operação

## Fundação implementada — 2026-05-26 (sessão Claude Code)

A rotina sugerida acima foi materializada nesta sessão:

### Scripts criados no repo
- `scripts/obsidian_sync.py` — sincronizador seguro one-way `docs/obsidian → vault`.
  Suporta dry-run (default), `--apply`, `--update` (resolve conflito com backup),
  `--include-config` (opt-in para `.obsidian/*.json`) e `--force <path>`.
- `scripts/obsidian_coverage_audit.py` — auditoria de cobertura código vs notas.
  Emite gaps de agentes, serviços, modelos, stories, ADRs e daily notes.

### Documentos canônicos criados
- [[Fontes de Verdade]] — política explícita de SoT por domínio.
- [[Guia de Manutenção do Segundo Cérebro]] — manual operacional.
- [[Instruções para Claude Code]] — guidance para sessões AI.

### Exclusões hard-coded confirmadas
Os 3 arquivos abaixo nunca serão copiados pelo sincronizador (decisão da
migração — vault organiza projetos sob `10 - Projects/Mekka Trading/`):
- `10 - Projects/10 - Projects.md`
- `10 - Projects/Projeto - Mekka Trading.md`
- `10 - Projects/_Projects.md`

### Lacunas identificadas (consulte a auditoria viva)
- 5 agentes em `src/agents/` sem nota dedicada (code_auditor, ops_scanner,
  risk_scanner, vision_critic, vision_moa).
- 4 notas-fantasma legítimas (Cypher, Domino, Forge, Trade Outcome
  Resolver) — são sprites/conceitos sem módulo Python.
- 76 serviços em `src/services/` sem menção no vault (esperado — só
  centrais merecem nota; auditor reporta para triagem).
- 30 stories do range 126–251 sem nota individual no vault.
- 5 daily notes faltantes em dias úteis recentes.

### Próxima manutenção recomendada
1. Decidir conscientemente se `.obsidian/app.json` do vault deve ser
   restaurado da versão canônica em `docs/obsidian/.obsidian/app.json`
   (atualmente vazio `{}` no vault — perdeu `newLinkFormat`,
   `attachmentFolderPath`, etc.).
2. Rodar `obsidian_coverage_audit.py` semanalmente; tratar gaps P0 (agentes).
3. Criar daily notes retroativas a partir dos `docs/HANDOFF*.md` recentes.
