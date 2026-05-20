# 🤝 Mekka Trading — Handoff para próximo chat

> **Data**: 2026-05-20 (sessão 2)
> **Branch**: `main` @ `dca7131` — **10 commits ahead de `origin/main`** (`b3376fe`), nada pushed
> **Estado**: ✅ rodando em **Bybit testnet LIVE mode** com Vision (Anthropic Claude) ativo
> **Próximo chat**: cole este arquivo como contexto inicial.

---

## 1. Como o sistema está rodando agora

- **PID 37556** rodando `run.py --dashboard`
- Working dir: `/Users/gustavovicente/Documents/Mekka-Trading`
- Python: `.venv313/bin/python` (3.13) · Dashboard: http://localhost:8787 · Log: `/tmp/mekka_dashboard.log`

### `.env` ativo
```bash
ACTIVE_EXCHANGE=bybit
BYBIT_TESTNET=true            # is_mainnet=False
PAPER_TRADING=false
LIVE_TRADING_CONFIRMED=true
TRADING_ASSETS=BTC
MAX_POSITION_SIZE_PCT=0.005   # 0.5%  ⚠️ ver gotcha #2
MAX_LEVERAGE=2
ANTHROPIC_API_KEY=<presente>  # OPENAI_API_KEY vazio (fallback usa Anthropic)
```

### ⚠️ Subir o servidor SEMPRE com env limpa
O shell tem `ANTHROPIC_API_KEY=""`/`OPENAI_API_KEY=""` vazios (Claude Desktop) que sobrepõem o `.env`:
```bash
env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY \
  nohup .venv313/bin/python run.py --dashboard > /tmp/mekka_dashboard.log 2>&1 &
# aguardar ~25s (boot roda 1 ciclo completo de agentes), depois:
curl -s http://localhost:8787/api/env
```

---

## 2. ✅ O que foi entregue nesta sessão (10 commits)

```
dca7131 feat(dashboard): "Modo Deus" — god-mode execute (item c)
b794f84 feat(dashboard): Central de Melhorias + Mekka/Galactus sprites
1a0d1cd feat(agents): Mekka (commander) + Galactus (premortem)
edc4274 feat(dashboard): ícone Mekka (SVG) no header (item g)
668fa2d docs(obsidian): vault cleanup — folder index notes + fixes
fd92469 fix(agents): Jean Grey vault-scan accuracy (NFC + exemptions)
96815c2 chore(git): untrack runtime artifacts + fix .gitignore globs
a4febf7 feat(agents): Jean Grey — Memory Master MVP (P2.1)
3a2e5d1 feat(dashboard): painel de trading manual (P1.1)
53c70cc fix(dashboard): bugs visuais P0 (nav/theme/prefs/chart/sprites/i18n)
```

### 🏛️ Time de Melhoria Contínua (4 agentes) — NOVO, funcional
Fluxo: **Beast** propõe → **Jean Grey** contextualiza → **Galactus** premortem (devora ideias frágeis) → **Mekka** consolida → **operador aprova/reprova** em `/Melhorias`.
- `src/agents/mekka.py` — comandante/consolidador. `GET /api/improvements`, `POST /api/improvements/decision`. Decisões em `data/improvement_decisions.json` (gitignored).
- `src/agents/galactus.py` — premortem, verdict SURVIVES/NEEDS_HARDENING/DEVOURED + hunger 0-100 + failure modes.
- `src/agents/jean_grey.py` — memória/vault health (`GET /api/jean/health-report`).
- Inbox curado de propostas (qualquer domínio): `data/improvement_inbox.json` (lista de `{title, description, impact, area, evidence}`).
- Atua em 2 domínios: **trading-ops** (risk/execution/signals/latency) e **dev-squad** (backend/frontend/dashboard/design).
- Sprites: Mekka (verde tech + olhos-lente do logo), Galactus (roxo cósmico + crown). Em `agents-sprites.js` e `office_v2/sprites.jsx`.

### Outras entregas
- **P0 (53c70cc)**: nav Live primeiro, tema claro v1, reset de prefs, live chart boot robusto, sprites unificados, i18n v1.
- **P1.1 (3a2e5d1)**: painel de trading manual com "pedir parecer dos robôs" (Batman) → `/api/trade/manual-analyze` + execução via Batman→IronMan. ⚠️ removeu o bypass do stub antigo `/api/trade/manual`.
- **(g)**: "MEKKA OPS" → logo SVG (dois formatos verde-lima) + wordmark.
- **(c) Modo Deus**: Force Execute rotulado como "🔱 Modo Deus" (proeminente). Backend mantém **hard-block em mainnet** (só paper/testnet); kill switch nunca ignorável.
- **Vault cleanup (668fa2d/fd92469)**: Jean Grey com NFC (acentos macOS), exempt de templates/pastas/dedup estrutural, 10 notas-índice de pasta criadas. Vault `is_healthy=True` (0 broken, 0 dups, 9 órfãs advisory).

---

## 3. 🎯 BACKLOG RESTANTE (priorizado)

### 🔴 Itens visuais pedidos pelo operador (ainda abertos)

| Item | Descrição | Arquivos / notas |
|---|---|---|
| **h** | Todos os heróis rodando no office da Overview | `office_v2/scene.jsx` tem **20 estações** mas roster tem **~24 agentes** (com Beast/Jean/Mekka/Galactus). Reorganizar STATIONS p/ caber todos. Office usa `USE_BUNDLE=false` → edita `.jsx` direto (sem rebuild). |
| **a** | Trade Mode no bloco vazio ao lado do office | Overview: `sec-office` (iframe) + `sec-trading-settings`. Reposicionar em grid lado-a-lado. `_PAGE_SECTIONS.overview` em `app.js:~2962`. |
| **b** | Central de comandos do operador na Overview | Nova seção na Overview com atalhos: trade manual, executar, kill switch, modo. Reusar handlers existentes. |
| **e** | Tooltip "?" em TODOS os blocos (explicação leiga + responsável) | Existe `HELP_TIPS` + `enhanceTitlesWithHelp()` em `app.js:~424`. Hoje cobre poucos `h2`. Expandir o dicionário p/ todos os ~30 painéis, incluindo "responsável" (qual herói). |
| **f** | Overhaul UX da página de Configurações | `sec-settings` (widget customizer) + `sec-filters`. Hoje só checkboxes crus. Agrupar por categoria, busca, presets, preview. |
| **d** | Modo claro round 2 + i18n completa | Tema claro tem Layer 7 (`body[data-theme="light"]`) mas faltam regras p/ componentes novos (manual, melhorias, office). i18n: muitas strings ainda hardcoded fora do dict. |

### 🟣 Improvement Council — próximo passo: aprovação via Telegram
> Pedido do operador: as propostas/recomendações do conselho também podem ser
> **enviadas ao Telegram para serem aprovadas/reprovadas** (espelhar a UX da
> Central de Melhorias no Telegram).

**Infra existente (já mapeada):**
- `src/services/telegram_alerter.py` — **outbound**. `_post(text, parse_mode)` envia via Bot API `sendMessage`. Há padrão de alertas (`alert`, `trade_opened`, `wolverine_*`, `drawdown_alert`).
- `src/services/telegram_inbound.py` — **inbound** via **long-polling** (`getUpdates`, NÃO webhook). `TelegramInboundPoller` despacha comandos de texto (`/status`, `/pause`, `/mode`, etc.). Controlado por `TELEGRAM_INBOUND_ENABLED` + `telegram_inbound_poll_interval_seconds`.
- Já existe aprovação de trades via Telegram (Story 074, `TELEGRAM_TRADE_APPROVAL_ENABLED`).

**Plano sugerido:**
1. **Outbound** — método `improvement_proposed(rec)` no `TelegramAlerter` que envia cada recomendação pendente do Mekka (título, domínio, decisão, veredito do Galactus + hunger, mitigações, rationale). Disparar quando `Mekka.run()` produz recomendações `pending` (ou via `/melhorias` no Telegram).
2. **Aprovação** — duas opções:
   - **(a) Comandos de texto** (mais simples, casa com o inbound atual): `/melhorias` lista pendentes com IDs curtos; `/aprovar <id>` e `/reprovar <id>` chamam `Mekka().record_decision(id, status)`. Adicionar handlers no `telegram_inbound.py`.
   - **(b) Inline buttons** (`reply_markup` + `callback_query`): UX melhor, mas o poller atual só trata `message`/text — precisaria estender `_poll_once` para `callback_query`. Mais trabalho.
   - **Recomendado:** começar com (a), evoluir para (b).
3. **Sync** — `record_decision` já persiste em `data/improvement_decisions.json`, então aprovar no Telegram reflete na página `/Melhorias` e vice-versa (mesma fonte). 
4. **Dedup/segurança** — respeitar `chat_id` autorizado (como o inbound já faz) e a janela de dedup de alertas (gotcha #8 da sessão 1).

**Arquivos**: `telegram_alerter.py` (outbound), `telegram_inbound.py` (comandos), `mekka.py` (`record_decision` já existe), settings de Telegram.

### 🔵 Fase 3 — Saúde do código (item i, j)
- **i**: revisar todo o código p/ lixo/otimização/segurança (usar squads). Candidatos: `server.py` (~5k linhas), `nick_fury.py` (~2.2k).
- **j**:
  - **P2.2 Iceman** — agente on-chain real (whale tracking, DeFi flows). Black Panther hoje é stub.
  - **P3.1 Cybersec** — token obrigatório em POSTs, MEKKA_DASHBOARD_SECRET, audit HMAC, Telegram alert no Modo Deus.
  - **Refactor `server.py`** → routers por domínio (já é a 1ª recomendação dev-squad no `/Melhorias`!).
- **P3.6 ADRs retroativos**: Force Execute/Modo Deus, CycleCheckpoint, Beast, DecisionMemory, Mekka/Galactus council.

---

## 4. ⚠️ Gotchas conhecidos

1. **Automação do Codex fazia auto-commit** ("Sync local changes" / "Capture remaining local changes") — varria código + lixo de runtime. **RESOLVIDO**: `.gitignore` corrigido (`data/*.db`, `data/*.json`, `memory/audit-log/*.ndjson`/`.head`) + 397 arquivos untracked em `96815c2`. **Se a automação reativar**: ela não consegue mais re-trackear runtime, mas ainda pode fazer commits genéricos de código real → desligar de vez. Branch `backup-pre-cleanup-45b3022` guarda o estado pré-cleanup.
2. **Janela apertada de notional**: `MAX_POSITION_SIZE_PCT=0.005` + cap absoluto $100 vs mínimo Bybit 0.001 BTC (~$76). Trades manuais pequenos podem dar `ERROR: amount must be greater than 0.001`. Para FILLED real, ajustar `.env` (decisão do operador).
3. **`PAPER_TRADING=false`** ativo. Em testnet é seguro. Modo Deus respeita hard-block de mainnet.
4. **Office v2**: `USE_BUNDLE=false` → carrega `.jsx` via Babel em runtime. Editar sprites.jsx/scene.jsx reflete direto (sem `npm run build:office-v2`). Para produção, rebuildar o bundle.
5. **Nada foi pushed** (10 commits ahead). Push é tarefa do `@devops`.

---

## 5. 🛠️ Health check rápido
```bash
lsof -nP -iTCP:8787 -sTCP:LISTEN          # processo
curl -s http://localhost:8787/api/env      # exchange/network/mode
curl -s http://localhost:8787/api/improvements | python3 -m json.tool   # conselho Mekka
curl -s http://localhost:8787/api/jean/health-report | python3 -m json.tool  # vault health
```

---

## 6. 📝 Mensagem inicial sugerida para o próximo chat
> Continuando o Mekka Trading no `main` @ `dca7131` (Bybit testnet LIVE). Leia `HANDOFF.md`. O time de melhoria contínua (Mekka + Galactus + Beast + Jean Grey) está pronto e a Central de Melhorias funciona em `/Melhorias`. Quero atacar os itens visuais restantes: **h** (heróis no office), **a** (trade mode ao lado do office), **b** (comandos na overview), **e** (tooltips "?" em todos os blocos), **f** (UX de configurações), **d** (modo claro + i18n). Depois Fase 3 (Iceman, cybersec, refactor server.py).

---
**Fim do handoff.** Cada item restante tem arquivos e caminho identificados.
