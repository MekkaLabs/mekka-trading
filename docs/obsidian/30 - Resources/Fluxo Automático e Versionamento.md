---
title: Fluxo Automático e Versionamento — Sistema ↔ Segundo Cérebro ↔ GitHub
type: policy
status: ativo
tags: [governance, automation, ci, second-brain, mekka-trading]
created: 2026-05-26
updated: 2026-05-26
---

# Fluxo Automático e Versionamento

> Define como mudanças no sistema fluem para o conhecimento e como o
> versionamento separa o que é versionável do que é estritamente operacional.
> Complementa [[Fontes de Verdade]] (o que é dono de quê) e
> [[Guia de Manutenção do Segundo Cérebro]] (como manter vivo).

## Pipeline canônico (6 etapas)

```
1. Mudança relevante no sistema/código (src/, settings, scripts)
        ↓
2. Identificação do conhecimento impactado
        (hook pre-commit + auditor periódico)
        ↓
3. Atualização ou proposta em docs/obsidian/
        (manual + sugestão do hook)
        ↓
4. Sincronização segura para o vault canônico
        (scripts/obsidian_sync.py — dry-run → --apply)
        ↓
5. Validação de consistência
        (scripts/obsidian_coverage_audit.py + CI workflow)
        ↓
6. Versionamento correto no GitHub
        (apenas o que deve ser versionado entra no commit)
```

## Camadas e seus mecanismos

### Etapa 1 — Mudança no sistema
Quem dispara: trabalho de desenvolvimento normal.
- Edição em `src/` (agentes, serviços, modelos, dashboard)
- Novo arquivo em `docs/stories/`, `docs/adr/`
- Mudança em `src/config/settings.py`, `AGENTS.md`, `README.md`, `HANDOFF.md`

### Etapa 2 — Identificação automática do impacto
Quem garante: **`scripts/git-hooks/pre-commit-obsidian`**
(instalável via `bash scripts/install-git-hooks.sh`).

Quando `git commit` roda, o hook escaneia o staging e imprime sugestões:

```
🧠 Segundo cérebro — sugestões de revisão:
  · agente 'batman' mudou → revisar 20 - Areas/Agentes IA/Batman.md
  · settings.py mudou → revisar Operacional + ADRs sobre safety gates
```

**Características de segurança:**
- Não bloqueia o commit por falta de nota (apenas avisa).
- Bloqueia SOMENTE se `docs/obsidian` e vault estão em CONFLICT ativo
  (proteção contra perda silenciosa de edição).
- Bypass: `SKIP_OBSIDIAN_HOOK=1 git commit ...`.

### Etapa 3 — Atualização da fonte versionada
Quem faz: humano + Claude Code (com guidance em [[Instruções para Claude Code]]).

Sempre editar em `docs/obsidian/` (NUNCA direto no vault canônico
para conteúdo que deve ser versionado).

### Etapa 4 — Sincronização segura
Quem executa: **`scripts/obsidian_sync.py`**.

| Modo | Comando | Risco |
|---|---|---|
| Diagnóstico | `python scripts/obsidian_sync.py` | Zero (dry-run) |
| Copiar novos | `python scripts/obsidian_sync.py --apply` | Zero (não sobrescreve) |
| Resolver conflitos | `python scripts/obsidian_sync.py --apply --update` | Baixo (backup automático) |
| Forçar 1 arquivo | `python scripts/obsidian_sync.py --apply --force <path>` | Baixo (backup automático) |
| Mexer em configs | `python scripts/obsidian_sync.py --apply --include-config` | Médio (afeta comportamento do Obsidian) |

Garantias:
- One-way: nunca lê do vault para escrever no repo.
- Idempotente: rodar 2× consecutivos não muda nada além do 1º.
- Backup `.bak-YYYYMMDD-HHMMSS` antes de qualquer overwrite explícito.
- Exit code != 0 se houver CONFLICT não resolvido.

### Etapa 5 — Validação de consistência
Quem garante: **`scripts/obsidian_coverage_audit.py`** + CI workflow
**`.github/workflows/obsidian-audit.yml`**.

**Local:**
```bash
python scripts/obsidian_coverage_audit.py
python scripts/obsidian_coverage_audit.py --json > audit.json
```

**CI (automático em PRs e push para main):**
- Roda `obsidian_sync.py --vault docs/obsidian` (sanidade: idempotência interna).
- Roda `obsidian_coverage_audit.py --vault docs/obsidian`.
- Publica `audit.json` + `audit.txt` como artefato da execução.
- Comenta no PR um resumo dos gaps (informativo, não bloqueia merge).

Métricas reportadas:
- Agentes em `src/agents/` sem nota dedicada
- Notas-fantasma (notas sem referente em código)
- Serviços / modelos sem menção
- Stories sem nota individual
- ADRs canônicos sem reflexo
- Daily notes faltantes em dias úteis recentes

### Etapa 6 — Versionamento correto

**O que ENTRA no GitHub:**
- Todo `src/`, `tests/`, `docs/` (incluindo `docs/obsidian/`, exceto exclusões abaixo)
- Scripts em `scripts/`
- Configs canônicas do Obsidian: `docs/obsidian/.obsidian/app.json`,
  `core-plugins.json`, `community-plugins.json`, `daily-notes.json`,
  `templates.json`
- `.github/workflows/`

**O que FICA FORA (gitignored):**
- `docs/obsidian/.obsidian/workspace.json` (estado de janelas — local)
- `docs/obsidian/.obsidian/workspace-mobile.json`, `workspaces.json`
- `docs/obsidian/.obsidian/cache/`
- `docs/obsidian/.obsidian/appearance.json` (preferências visuais — local)
- `docs/obsidian/.obsidian/graph.json` (zoom/pan do grafo — local)
- `docs/obsidian/.trash/`
- `*.bak-*` (backups gerados pelo sincronizador)
- `audit.json`, `audit.txt`, `audit-*.json`, `audit-*.txt` (saídas locais)
- `.env`, `data/`, `logs/` (runtime — nunca no repo)

**O que NÃO está no GitHub (intencionalmente):**
- `~/Documents/mekka-trading-obsidian/` — vault canônico operacional
- `~/Documents/mekka-trading-obsidian.backup-*` — backups pontuais
- Notas em progresso no `00 - Inbox/` do vault
- Daily notes operacionais do vault (`60 - Daily/` do vault só, não do repo)

## Decisão: vault canônico fora do git

O vault `~/Documents/mekka-trading-obsidian` NÃO é um repositório git.
Razões:
1. **Captura rápida** sem cerimônia de commit.
2. **Daily notes e inbox** são pessoais e voláteis.
3. **Versionamento real** vive em `docs/obsidian/` (subset estável).
4. **Sincronização** já é coberta pelo `obsidian_sync.py`.

**Estratégia de backup do vault:**
- Snapshot manual periódico (a critério do operador):
  ```bash
  cp -R ~/Documents/mekka-trading-obsidian \
        ~/Documents/mekka-trading-obsidian.backup-$(date +%Y%m%d-%H%M%S)
  ```
- Time Machine / iCloud / qualquer backup do sistema operacional cobre o vault.
- O repo (`docs/obsidian/`) é o backup de longo prazo do conteúdo versionável.

## Configuração inicial (uma vez)

```bash
# 1) Instalar hook pre-commit
bash scripts/install-git-hooks.sh

# 2) Verificar fluxo end-to-end
python scripts/obsidian_sync.py        # dry-run
python scripts/obsidian_coverage_audit.py

# 3) CI workflow já ativo após push para main (.github/workflows/obsidian-audit.yml)
```

## Rotina ideal por evento

| Evento | Ação automática | Ação manual recomendada |
|---|---|---|
| Edit em `src/agents/X.py` | hook sugere atualizar `20 - Areas/Agentes IA/X.md` | revisar nota se mudança é semântica |
| Novo `docs/adr/ADR-NNN-*.md` | hook sugere criar nota em `Decisoes Tecnicas/` | criar nota prosa que reflete o ADR |
| Novo `docs/stories/story-NNN-*.md` | hook sugere criar `Story NNN.md` no vault | criar resumo com link ao arquivo canônico |
| Edição em `docs/obsidian/` | hook bloqueia se vault diverge | `python scripts/obsidian_sync.py --apply` |
| PR em GitHub | CI roda auditoria + posta comment | revisar gaps no comment |
| Final de sessão grande | — | daily note no vault + handoff no repo |
| Semanal | — | rodar auditoria local + review semanal |

## Sinais de fluxo quebrado

- Hook pre-commit retorna CONFLICT toda vez → vault foi editado direto;
  decidir qual versão fica e sincronizar.
- CI reporta `agents_missing > 0` por > 1 sprint → criar notas dos agentes
  novos ou justificar (ex.: utilitário interno sem peso de agente).
- `daily_gaps > 5` → dias úteis sem nota; sessões de trabalho não estão
  virando memória persistente.
- Sincronizador reporta CONFLICT em arquivo já em produção → bug do script
  ou edição manual no vault para arquivo gerenciado pelo repo.

## Notas relacionadas

- [[Fontes de Verdade]]
- [[Guia de Manutenção do Segundo Cérebro]]
- [[Instruções para Claude Code]]
- [[Migração do Segundo Cérebro - 2026-05-26]]
