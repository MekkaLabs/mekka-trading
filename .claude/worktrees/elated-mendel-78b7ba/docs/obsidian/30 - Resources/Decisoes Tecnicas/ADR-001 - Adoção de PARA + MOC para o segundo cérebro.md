---
title: "ADR-001 — Adoção de PARA + MOC para o segundo cérebro"
type: adr
tags: [decisao, arquitetura]
status: aceita
date: 2026-05-07
---

# ADR-001 — Adoção de PARA + MOC

> **Status**: aceita
> **Data**: 2026-05-07
> **Autores**: Gusta

## Contexto

O projeto Mekka Trading tem alta complexidade: múltiplos módulos (TS + Python), 14+ squads, agentes temáticos, 24+ stories, observability complexa. Documentação solta em READMEs não escala.

Era preciso um sistema de gestão de conhecimento que:
- Funcione como segundo cérebro (não só doc do código)
- Versione junto do projeto (Git)
- Suporte links bidirecionais e exploração
- Distinga **projetos com prazo** de **áreas contínuas**

## Decisão

Adotar **PARA** (Tiago Forte) + **MOCs** (Maps of Content):

- `00 - Inbox` — captura rápida
- `10 - Projects` — iniciativas com entregável e prazo
- `20 - Areas` — responsabilidades contínuas (Trading, Arquitetura, Agentes IA, Risco, Operacional)
- `30 - Resources` — referências, ADRs, runbooks, glossário
- `40 - Archive` — concluído ou desativado
- `50 - MOCs` — índices vivos por domínio
- `60 - Daily` — log diário
- `70 - Templates` — templates reutilizáveis
- `80 - Attachments` — anexos

## Alternativas Consideradas

### Zettelkasten puro
- Prós: descoberta orgânica, sem hierarquia rígida
- Contras: curva de adoção alta, dificulta onboarding em projeto técnico

### Pastas hierárquicas tradicionais
- Prós: simples
- Contras: não diferencia *projeto* de *área*; não escala bem

## Consequências

### Positivas
- Modelo testado e amplamente documentado (Forte, Ahrens)
- Revisão semanal/mensal com critério claro (status do projeto, atividade da área)
- MOCs servem como entrada para qualquer pesquisa

### Negativas / Trade-offs
- Disciplina inicial alta para mover notas do Inbox
- Numeração nas pastas é artificial mas garante ordenação no Obsidian

## Notas Relacionadas

- [[../../Home]]
- [[../../50 - MOCs/MOC - Arquitetura]]

## Referências

- Tiago Forte — *Building a Second Brain*
- Nick Milo — *Linking Your Thinking* (origem do conceito de MOC)
