# HANDOFF — Mekka Trading · 2026-05-11 (Sessão 2)

> Continua da sessão anterior (af2b1d63). Esta sessão adicionou Runtime Trading Mode Control completo e corrigiu o Office v2 + dashboard embed.

---

## Estado atual do sistema

| Item | Status |
|------|--------|
| Servidor | ✅ Rodando via `restart.command` em `localhost:8787` |
| Dashboard | ✅ Online — `http://localhost:8787` |
| Office v2 | ✅ Funcionando — `http://localhost:8787/office-v2/` |
| Trading Mode Panel | ✅ Funcionando — botões Conservador/Balanceado/Agressivo |
| Telegram `/mode` | ✅ Implementado |
| Paper Trading | ✅ Ativo (TESTNET, BTC/ETH/SOL, equity $6.71) |
| Testes | ✅ 377 Python + 46 TS passando (baseline anterior) |

---

## O que foi feito nesta sessão

### 1. Runtime Trading Mode Control (Story 040)

Sistema de controle de intensidade operacional com hot-reload (sem reiniciar o servidor):

**Arquivos criados:**
- `src/config/runtime_mode.py` — módulo central
  - 3 presets: `conservative`, `balanced`, `aggressive`
  - Persistência em `data/runtime_mode.json`
  - Thread-safe singleton com lazy-load
  - API: `get_mode()`, `set_mode(mode)`, `get_params()`, `all_modes_summary()`

**Arquivos modificados:**
- `src/dashboard/server.py`
  - Rotas `GET /api/mode` → retorna modo atual + todos os presets
  - Rotas `POST /api/mode` → muda modo + emite evento audit `MODE_CHANGED`
  - Auth middleware: exemption para `/api/mode` (POST liberado sem token)
- `src/agents/batman.py` — usa `get_params()` para `max_position_size_pct` e `max_leverage`
- `src/agents/nick_fury.py` — usa `get_params()` para `trading_assets`
- `src/services/telegram_inbound.py` — comando `/mode` (ver modo ou `/mode aggressive`)
- `src/dashboard/static/office_v2/app.jsx` — `TradingModePanel` component
- `src/dashboard/static/office_v2/office_v2.bundle.js` — bundle reconstruído

**Tabela de presets:**

| Modo | Posição max | Leverage max | Drawdown/dia | Trades/dia | Ativos |
|------|------------|--------------|--------------|------------|--------|
| 🛡️ conservative | 0.5% | 2x | 5% | 3 | BTC |
| ⚖️ balanced | 2% | 5x | 10% | 10 | BTC/ETH/SOL |
| ⚡ aggressive | 5% | 10x | 15% | 20 | BTC/ETH/SOL/AVAX |

### 2. Office v2 embeddado no Dashboard

- `src/dashboard/static/index.html` — seção `#sec-office` como PRIMEIRO bloco (hero), antes do mercado ao vivo
- `src/dashboard/static/style.css` — `.office-hero`, `#office-v2-frame` com `height: calc(100vh - 120px)`
- Nav sidebar: "⬡ Pixel 3D Office" em destaque (primeiro item)
- Iframe full-width, expande para quase toda a altura da tela

### 3. Arquivo restart.command

Criado `~/Documents/Mekka-Trading/restart.command` — script executável (double-click no Finder):
```bash
pkill -f "run.py" 2>/dev/null || true
sleep 2
cd ~/Documents/Mekka-Trading
# Auto-detecta python: .venv/bin/python → python3 → python
$PYTHON run.py --dashboard
```

---

## Como usar o Trading Mode

### Via Office v2 (recomendado)
1. Abrir `http://localhost:8787` → dashboard abre com Office v2 no topo
2. No painel lateral direito do Pixel Office → **⚙ Trading Mode**
3. Clicar no modo desejado → muda instantaneamente

### Via Telegram
```
/mode             → ver modo atual
/mode conservative → ativar modo conservador
/mode balanced    → ativar modo balanceado (padrão)
/mode aggressive  → ativar modo agressivo
```

### Via API (curl)
```bash
# Ver modo atual
curl http://localhost:8787/api/mode

# Mudar modo
curl -X POST http://localhost:8787/api/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "aggressive"}'
```

---

## Como reiniciar o servidor

**Método 1 — Finder (recomendado):**
1. Abrir Finder → `~/Documents/Mekka-Trading/`
2. Double-click em `restart.command`
3. Terminal abre, mata o processo antigo e inicia o novo

**Método 2 — Terminal manual:**
```bash
pkill -f "run.py"
sleep 2
cd ~/Documents/Mekka-Trading
source .venv313/bin/activate
python run.py --dashboard
```

**Método 3 — No terminal ativo (Ctrl+C depois):**
```bash
cd ~/Documents/Mekka-Trading && .venv/bin/python run.py --dashboard
```

---

## Arquitetura atual do Office v2

```
/office-v2/
├── index.html          # base href="/office-v2/", carrega react.js local
├── react.js            # React 18 local (do node_modules, sem CDN)
├── react-dom.js        # ReactDOM 18 local (do node_modules, sem CDN)
├── office_v2.bundle.js # Bundle compilado (TypeScript API) — 117KB
├── mount.js            # Monta o App React no DOM
├── app.jsx             # App principal + TradingModePanel ← modificado
├── agent-motion.jsx    # Animações dos agentes
├── live-data.jsx       # Dados ao vivo via WebSocket
├── props.jsx           # Propriedades dos agentes
├── scene.jsx           # Cena 3D isométrica
├── sprites.jsx         # Sprites dos personagens
└── tweaks-panel.jsx    # Painel de ajustes lateral
```

**Para rebuild do bundle após mudanças no app.jsx:**
```bash
# No Mac (usa esbuild nativo):
npm run build:office-v2

# No sandbox Linux (usa TypeScript compiler API):
node /tmp/build_office.js
```

O script de build:
```javascript
// /tmp/build_office.js
const ts = require('/path/to/node_modules/typescript');
// ORDER: agent-motion, props, sprites, scene, tweaks-panel, live-data, app
// ts.transpileModule com jsx: React, module: None
// IIFE wrapper
```

---

## Estrutura do projeto (resumo)

```
Mekka-Trading/
├── src/
│   ├── agents/
│   │   ├── batman.py          # Risk Guardian ← usa runtime_mode
│   │   ├── nick_fury.py       # Orchestrator ← usa runtime_mode
│   │   ├── superman.py        # Market Overseer (1h confirmation TF)
│   │   ├── vision.py          # Predictive Analyst (GPT-4o)
│   │   ├── iron_man.py        # Order Executor (paper/live)
│   │   ├── deadpool.py        # Performance Reporter
│   │   └── wolverine.py       # Recovery Agent
│   ├── config/
│   │   ├── settings.py        # Configurações base (env)
│   │   └── runtime_mode.py    # ← NOVO: presets hot-reload
│   ├── dashboard/
│   │   ├── server.py          # Dashboard + API (porta 8787)
│   │   └── static/
│   │       ├── index.html     # Dashboard principal
│   │       ├── style.css      # Estilos
│   │       └── office_v2/     # Pixel 3D Office
│   └── services/
│       ├── telegram_inbound.py # Bot Telegram ← /mode command
│       └── daily_perf_writer.py
├── data/
│   └── runtime_mode.json      # Modo persistido (criado na 1ª mudança)
├── tests/                     # 377 testes Python
├── restart.command            # ← NOVO: script de reinício
└── run.py                     # Entrypoint
```

---

## Gates pendentes (ação humana)

| Gate | Status | Descrição |
|------|--------|-----------|
| H1 | ⏳ Pendente | Aprovação formal para mainnet (documento MAINNET-AUTHORIZATION) |
| H2 | ✅ Auto | Deadpool monitora performance — auto-pass se Sharpe > 0.5 |
| H3 | ⏳ Pendente | Revisão de segurança por terceiros |
| H4 | ✅ Entregue | Preflight script + double-gate IronMan |
| H5 | ⏳ Pendente | Aprovação regulatória (se aplicável) |
| H6 | ⏳ Pendente | Capital mínimo confirmado para mainnet |

---

## Próximas possibilidades (sugestões)

1. **Testes para Story 040** — `test_phase19_runtime_mode.py` (unit tests do runtime_mode + endpoint)
2. **Story 041 — Dashboard Alerts** — notificação visual quando modo muda, badge no header
3. **Story 042 — Mode Scheduler** — agendar troca automática de modo (ex: conservative nas noites)
4. **Story 043 — Mainnet Prep** — completar gates H1, H3, H5, H6
5. **UI Polish** — adicionar histórico de mudanças de modo no audit feed do dashboard
6. **Mobile responsivo** — o painel de modo pode ser mais compacto em mobile

---

## Info técnica para o próximo Claude

- **Venv:** `.venv313` (Python 3.13) — `source .venv313/bin/activate`
- **Port:** 8787 (dashboard) — não é 8000 nem 8080
- **Bundle rebuild:** precisa de `node` e do `typescript` em `node_modules/`
- **Nomes de agentes:** SEMPRE super-heróis (Batman, NickFury, Superman, IronMan, Vision, Wolverine, Deadpool, ProfessorX, SpiderMan, BlackPanther, Aquaman, DoctorStrange, Flash) — NUNCA "rat" ou derivados
- **Auth middleware:** POST requests precisam de X-Mekka-Token EXCETO `/api/mode`, `/api/auth/login`, `/api/auth/logout`
- **Hot-reload do modo:** agentes lêem `runtime_mode` a cada ciclo — troca entra em vigor no próximo ciclo sem restart
- **data/runtime_mode.json:** criado automaticamente na primeira chamada a `set_mode()`

---

*Handoff gerado em 2026-05-11 20:40 UTC por Claude (Sonnet 4.6)*
*Sessão: 64fe0c67 / 8321712d*
