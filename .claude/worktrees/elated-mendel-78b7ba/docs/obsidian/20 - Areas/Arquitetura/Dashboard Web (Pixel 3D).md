---
title: Dashboard Web (Pixel 3D)
type: componente
tags: [arquitetura, dashboard, ui]
status: ativo
created: 2026-05-07
---

# Dashboard Web — Pixel 3D Marvel/Wall Street

## O que é

Dashboard browser-first do Mekka Trading que combina:
- **API REST** + **WebSocket** servidos por FastAPI/uvicorn
- **Visualização pixel 3D animada** no tema "escritório financeiro Marvel/Wall Street"
- Lê dados em tempo real da persistência SQLite

## Localização

- Servidor: `src/dashboard/server.py`
- Estáticos (HTML/CSS/JS/sprites): `src/dashboard/static/`
- Persistência: `src/persistence/` (`db.py`, `models.py`, `repository.py`)

## Endpoints

### REST
| Endpoint | Descrição |
|---|---|
| `GET /api/overview` | Equity, PnL, posição atual, regime, kill-switch status |
| `GET /api/signals` | Sinais gerados pelos agentes |
| `GET /api/trades` | Histórico de trades (paper) |
| `GET /api/audit` | Trilha de auditoria das decisões |

### WebSocket
| Endpoint | Descrição |
|---|---|
| `WS /ws` | Stream de updates em tempo real (eventos, alertas, ticks) |

## Como executar

```bash
# Runtime + dashboard juntos
python run.py --dashboard

# Apenas dashboard (lendo SQLite já alimentado por outro processo)
python run.py --dashboard-only

# Customizar equity inicial
python run.py --dashboard --equity 25000

# Apenas um ciclo (smoke test)
python run.py --once
```

URL padrão: **http://localhost:8787**

## Variáveis de ambiente relevantes

Ver `.env.example`:
- `OPENAI_API_KEY` — necessário para os agentes raciocinarem
- `HYPERLIQUID_PRIVATE_KEY` / `HYPERLIQUID_WALLET_ADDRESS` — modo testnet
- `PAPER_TRADING=true` — não alterar sem revisão de risco
- `LOG_LEVEL=INFO` — verbosidade dos logs

## Pontos de atenção

> ⚠️ Mesmo com dashboard rodando, **trade real continua bloqueado** na camada de risco. O dashboard é janela de observação, não controle de execução.

- Fonte dos dados: SQLite escrito pela pipeline runtime (`src/persistence/repository.py`)
- Não há autenticação (uso local). Se expor pela rede, adicionar reverse-proxy + auth.
- Dashboard é stateless — pode ser reiniciado a qualquer momento sem perder dados (estão no SQLite)

## Próximos passos sugeridos

- [ ] Criar runbook "Diagnosticar dashboard que não carrega"
- [ ] Documentar o esquema SQLite em [[../../30 - Resources/Decisoes Tecnicas/]]
- [ ] ADR sobre escolha do FastAPI vs Flask
- [ ] Mapear sprites/animações do pixel 3D em [[../../80 - Attachments/]]

## Notas relacionadas

- [[_Arquitetura Index]]
- [[../../50 - MOCs/MOC - Operações & Observability]]
