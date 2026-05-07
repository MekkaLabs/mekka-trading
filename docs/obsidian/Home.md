---
title: Home — Mekka Trading Second Brain
type: dashboard
tags: [dashboard, home, mekka-trading]
project: mekka-trading
created: 2026-05-07
updated: 2026-05-07
---

# 🧠 Mekka Trading — Segundo Cérebro

> **Projeto:** `mekka-trading` (independente de `mekkalabs-docs` e `AIOX-Docs`)
> **Repositório:** https://github.com/labsmekka/mekka-trading
> **Cópia espelhada no vault Obsidian:** `~/Documents/Obsidian Vault/mekka-trading/`

Sistema de Trading Autônomo orquestrado por IA, baseado em AIOX Core + Hyperliquid (mock).
Este é o vault de conhecimento do projeto: arquitetura, decisões, agentes, runbooks e aprendizados.

---

## 🚀 Navegação Rápida

### Mapas de Conteúdo (MOCs) — comece aqui
- [[50 - MOCs/MOC - Arquitetura|🏗️ MOC Arquitetura]]
- [[50 - MOCs/MOC - Agentes IA|🦸 MOC Agentes IA]]
- [[50 - MOCs/MOC - Trading & Estratégia|📈 MOC Trading & Estratégia]]
- [[50 - MOCs/MOC - Risco & Compliance|🛡️ MOC Risco & Compliance]]
- [[50 - MOCs/MOC - Operações & Observability|🔭 MOC Operações]]
- [[50 - MOCs/MOC - Aprendizados|📚 MOC Aprendizados]]

### Estrutura PARA
| Pasta | Propósito |
|---|---|
| [[00 - Inbox]] | Captura rápida — onde toda nota nova nasce |
| [[10 - Projects]] | Iniciativas com prazo e entregável claro |
| [[20 - Areas]] | Áreas de responsabilidade contínua |
| [[30 - Resources]] | Referências, decisões, runbooks |
| [[40 - Archive]] | Concluído ou desativado |
| [[50 - MOCs]] | Mapas de Conteúdo (índices vivos) |
| [[60 - Daily]] | Notas diárias / log de trabalho |
| [[70 - Templates]] | Templates reutilizáveis |
| [[80 - Attachments]] | Imagens, PDFs, anexos |

---

## 🎯 Sprint Atual

```dataview
TABLE without ID
  file.link AS "Projeto",
  status AS "Status",
  due AS "Prazo"
FROM "10 - Projects"
WHERE status != "done" AND status != "archived"
SORT due ASC
```

> *Se a tabela acima estiver vazia, instale o plugin **Dataview** (Settings → Community plugins → Browse → Dataview).*

---

## 🆕 Últimas notas modificadas

```dataview
LIST
FROM ""
WHERE !contains(file.path, "70 - Templates") AND !contains(file.path, ".obsidian")
SORT file.mtime DESC
LIMIT 10
```

---

## 🏷️ Tags principais

- `#arquitetura` — decisões e diagramas de arquitetura
- `#agente` — qualquer agente IA do sistema
- `#squad` — composições de squads
- `#estrategia` — estratégias de trading
- `#risco` — controles de risco e compliance
- `#runbook` — procedimentos operacionais
- `#decisao` — Architecture Decision Records (ADRs)
- `#aprendizado` — lições aprendidas
- `#bug` — bugs encontrados e soluções
- `#externa` — referências externas (papers, links, artigos)

---

## 📌 Atalhos úteis

- **Captura rápida**: novas notas vão sempre para `00 - Inbox` — depois você move para o lugar certo
- **Daily Note**: `Ctrl/Cmd + P` → "Daily notes: Open today's daily note"
- **Templates**: `Ctrl/Cmd + P` → "Templates: Insert template"
- **Graph view**: `Ctrl/Cmd + G` para ver conexões entre notas

---

## 🔗 Recursos do Projeto

- Repositório: *(adicione a URL após criar o repo no GitHub)*
- README do projeto: [[../../README|README.md]]
- Stories: `docs/stories/` (24 stories já implementadas)
- Squads: `squads/` (14 squads especializadas)
