# Mekka Trading

> Sistema Operacional de Trading Autônomo orquestrado por IA, baseado em padrões **AIOX Core** com integração mock à **Hyperliquid**.

[![Status](https://img.shields.io/badge/status-paper--only-yellow)]()
[![Node](https://img.shields.io/badge/node-%E2%89%A520-green)]()
[![Python](https://img.shields.io/badge/python-3.12-blue)]()
[![License](https://img.shields.io/badge/license-private-lightgrey)]()

---

## Sumário

- [Visão geral](#visão-geral)
- [Stage atual — Megazord v1.1](#stage-atual--megazord-v11)
- [Arquitetura em alto nível](#arquitetura-em-alto-nível)
- [Stack](#stack)
- [Setup local](#setup-local)
- [Quality gates](#quality-gates)
- [CLIs disponíveis](#clis-disponíveis)
- [Dashboard Web + Pixel 3D](#dashboard-web--pixel-3d)
- [Segurança](#segurança)
- [Documentação interna (Obsidian)](#documentação-interna-obsidian)
- [Versionamento e contribuição](#versionamento-e-contribuição)

---

## Visão geral

Mekka Trading é uma plataforma multi-agente para pesquisa, simulação e (futuramente) execução de estratégias de trading. **Agora opera apenas em paper trading**: ordens reais são bloqueadas na camada de risco.

- Arquitetura **CLI-first**, sem dependências cross-project
- Modelo de execução **risk-first**
- Orquestração multi-agente + squads
- Pipeline **observability-first** (eventos + logs + audit trail)

## Stage atual — Megazord v1.1

- Mission planner + squad router + runtime loop
- Stress scenario packs (volatility, liquidity, drawdown)
- Risk regime manager com kill switch crítico automático
- Controles risk-first com policy limits
- Execução paper-only via conector mock Hyperliquid
- Observability estruturada (logs + eventos + audit trail)

## Arquitetura em alto nível

Contrato de workflow:

```
INPUT → ANALYSIS → DECOMPOSITION → ROUTING → EXECUTION → VALIDATION → REFLECTION → OUTPUT
```

Módulos principais:

| Módulo | Função |
|---|---|
| `agents/` | Definições de agentes individuais |
| `squads/` | Composições de squads especializadas |
| `workflows/` | Workflows orquestrados |
| `cli/` | Interfaces de linha de comando |
| `prompts/` | Prompts estruturados |
| `exchanges/hyperliquid/` | Adaptador mock Hyperliquid |
| `market-data/` | Feeds de mercado |
| `risk-engine/` | Políticas de risco e kill switch |
| `execution-engine/` | Motor de execução paper |
| `strategy-engine/` | Sinais e estratégias |
| `backtesting/` | Replay e validação histórica |
| `observability/` | Store, alerts, reports |
| `memory/` | Audit-log, alerts, reports persistidos |
| `aiox-core/` | Framework AIOX Core (submódulo) |
| `src/` | Utilitários Python |

A documentação detalhada vive em [`docs/obsidian/`](./docs/obsidian/) — segundo cérebro PARA + MOC versionado junto do código.

## Stack

- **Runtime principal**: Node.js ≥ 20, TypeScript 5.7
- **Componentes auxiliares**: Python 3.12 (pytest, asyncio)
- **Exchange**: Hyperliquid (mock-only)
- **Notificações**: Telegram
- **News/sentiment**: CryptoPanic
- **LLM**: OpenAI

## Setup local

```bash
# 1. Clonar (incluindo submódulo aiox-core)
git clone --recurse-submodules <URL_DO_REPO>
cd Mekka-Trading

# 2. Variáveis de ambiente
cp .env.example .env
# Edite .env com suas chaves (NUNCA commite o .env)

# 3. Dependências Node
npm install

# 4. Dependências Python (opcional, para módulos auxiliares)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 5. Build
npm run build
```

## Quality gates

Antes de qualquer commit relevante:

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

## CLIs disponíveis

| Comando | Função |
|---|---|
| `npm run run:runtime` | Loop principal Megazord |
| `npm run run:replay` | Replay de eventos históricos |
| `npm run run:export-report` | Exporta relatórios de missão |
| `npm run run:verify-integrity` | Valida integridade do audit-log |
| `npm run run:health-check` | Saúde geral do sistema |
| `npm run run:replay-dlq` | Reprocessa Dead Letter Queue |
| `npm run run:alerts-retention` | Aplica retenção de alertas |
| `npm run run:ops-status` | Status operacional |
| `npm run run:ops-alerts` | Lista alertas |
| `npm run run:ops-alert-audit` | Auditoria de entrega de alertas |

## Dashboard Web + Pixel 3D

Foi adicionado um dashboard browser-first em `src/dashboard/` com:

- API REST (`/api/overview`, `/api/signals`, `/api/trades`, `/api/audit`)
- WebSocket (`/ws`) para atualização em tempo real
- Visualização **pixel 3D animada** no tema escritório financeiro “Marvel/Wall Street”

Execução:

```bash
# Runtime + dashboard juntos
python run.py --dashboard

# Apenas dashboard (lendo SQLite já alimentado por outro processo)
python run.py --dashboard-only
```

URL padrão: `http://localhost:8787`

## Segurança

**Hard rules** (invioláveis):

- Trading real é **bloqueado** na camada de risco
- Kill switch sempre disponível, default sob controle de governança
- Hyperliquid é **mock-only** neste estágio
- Nenhuma chave de API ou roteamento de ordem real está implementado
- Nunca contornar a validação de risco
- Nunca compartilhar estado entre projetos
- Sempre emitir logs, eventos e audit

`PAPER_TRADING=true` é o default e **não deve ser alterado** sem revisão formal.

## Documentação interna (Obsidian)

A pasta [`docs/obsidian/`](./docs/obsidian/) é um **vault Obsidian** funcionando como segundo cérebro do projeto:

- Método: **PARA** + **MOC** (Maps of Content)
- Templates para ADRs, runbooks, agentes, estratégias, daily notes
- Inventário completo de squads, agentes e stories
- Versionado junto do código (workspace/cache do Obsidian ignorados)

Como abrir: instale o [Obsidian](https://obsidian.md), `Open folder as vault` → selecione `docs/obsidian/`. Recomendado instalar o plugin **Dataview**.

## Versionamento e contribuição

- **Estratégia**: GitHub Flow (`main` + feature branches + tags semânticas)
- **Convenção de commits**: [Conventional Commits](https://www.conventionalcommits.org/)
- **Versionamento**: [SemVer](https://semver.org/)
- **Mudanças**: ver [`CHANGELOG.md`](./CHANGELOG.md)
- **Como contribuir**: ver [`CONTRIBUTING.md`](./CONTRIBUTING.md)

## Licença

Privado. Todos os direitos reservados.
