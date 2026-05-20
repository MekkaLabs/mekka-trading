# 🧠 Mekka Trading — Obsidian Vault

Este é o **segundo cérebro** do projeto Mekka Trading, organizado pelo método **PARA + MOC**.

> O vault é versionado junto do código. Notas viram parte do ciclo de
> desenvolvimento: cada decisão técnica grande gera um ADR, cada sessão
> de trabalho gera uma daily note, cada novo procedimento gera um
> runbook. A regra é: **se quebra o sistema duas vezes, vira nota.**

## Como abrir

1. Instale o [Obsidian](https://obsidian.md) (versão 1.4+).
2. **Open folder as vault** → selecione esta pasta `docs/obsidian/`.
3. Abra a nota [[Home]] como dashboard.
4. **Habilite os plugins de comunidade declarados em `community-plugins.json`** (Obsidian vai sugerir automaticamente):
   - **Dataview** — várias notas têm queries `dataview` embutidas. Sem ele, as queries aparecem como código bruto.
   - **Templater** — opcional, mas habilita variáveis avançadas nos templates.

Ative em **Settings → Community Plugins → Browse → instalar e habilitar**.

> Quem clona o repo herda `community-plugins.json` mas o Obsidian **não baixa o binário automaticamente** — ainda é necessário clicar "Install" uma vez. Isso é design do Obsidian para evitar plugins maliciosos via Git.

## Estrutura (PARA + extensões)

| Pasta | Propósito |
|---|---|
| `00 - Inbox` | Captura rápida — onde toda nota nasce |
| `10 - Projects` | Iniciativas com prazo e entregável |
| `20 - Areas` | Responsabilidades contínuas (Trading, Arquitetura, Agentes IA, Risco, Operacional) |
| `30 - Resources` | ADRs, runbooks, glossário, referências externas |
| `40 - Archive` | Concluído ou desativado |
| `50 - MOCs` | Maps of Content — índices vivos com queries Dataview |
| `60 - Daily` | Log diário |
| `70 - Templates` | 7 templates: Daily, ADR, Agente, Aprendizado, Estratégia, Runbook, Story |
| `80 - Attachments` | Imagens, PDFs |

## Versionado no Git

Este vault é **versionado junto do código**. O workspace e o cache do Obsidian são ignorados via `.gitignore` na raiz do repo:

```
docs/obsidian/.obsidian/workspace.json
docs/obsidian/.obsidian/workspace-mobile.json
docs/obsidian/.obsidian/workspaces.json
docs/obsidian/.obsidian/cache/
docs/obsidian/.trash/
```

Tudo mais em `.obsidian/` é versionado — incluindo `community-plugins.json`, `app.json`, `core-plugins.json`, `daily-notes.json` e `templates.json` — para que o ambiente do vault seja reprodutível.

## Filosofia de uso

- **5 minutos por dia** processando o Inbox.
- **Reviews semanais** dos MOCs principais.
- **ADRs** para decisões arquiteturais não-óbvias — cada decisão recebe um número e fica em `30 - Resources/Decisoes Tecnicas/`.
- **Daily notes** como log de trabalho (não memorial). Use `Template - Daily Note`.
- **Aprendizados** sempre que algo te surpreender — bom ou ruim.
- **Runbooks** sempre que uma sequência de passos for executada duas vezes.

## Convenções de wikilink

- Use **short links** (`[[Nick Fury]]`) e não paths relativos (`[[../20 - Areas/Agentes IA/Nick Fury]]`). O Obsidian resolve sozinho graças a `newLinkFormat: "shortest"` em `app.json`.
- Quando houver ambiguidade (duas notas com o mesmo nome), o Obsidian sugere um caminho parcial — aceite a sugestão em vez de digitar manualmente.

## Sincronização com `docs/stories/`

Hoje a lista de stories em [[Stories do Projeto]] é mantida manualmente. Uma futura story do projeto (TODO) entregará `scripts/sync_obsidian.py` que lê `docs/stories/*.md` e mantém a lista em sincronia automaticamente.
