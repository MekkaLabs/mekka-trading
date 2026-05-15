# Mekka Dashboard

Camada de observabilidade browser-first do Mekka Trading. Lê do mesmo
SQLite que Nick Fury escreve, expõe API REST + WebSocket, e renderiza
um painel "Marvel/Wall Street" pixel-3D em `/`.

## Status

- **Localização**: `src/dashboard/server.py` (~370 linhas), front em
  `src/dashboard/static/`
- **Stack**: aiohttp + WebSocket nativo
- **Bind default**: `0.0.0.0:8787`
- **Persistence**: lê via `MekkaRepository` (mesmo SQLite do pipeline)
- **Snapshots**: grava em `data/dashboard_snapshots/` (uma vez por minuto)

## Modos de execução

```bash
# Runtime + dashboard juntos (mais comum)
python run.py --dashboard

# Apenas dashboard, lendo SQLite que outro processo alimenta
python run.py --dashboard-only

# Customizando bind
python run.py --dashboard --dashboard-host 127.0.0.1 --dashboard-port 9000
```

## API REST

Todas em `GET`, retornam JSON. Não exigem auth (ainda — ver "Próximos
passos").

| Endpoint                        | Função                                                     |
| ------------------------------- | ---------------------------------------------------------- |
| `/`                             | UI HTML (pixel-3D escritório financeiro)                   |
| `/api/overview`                 | Resumo: contagem de signals, trades, audit, status global  |
| `/api/signals?limit=20`         | TradingSignals recentes                                    |
| `/api/trades?limit=20`          | ExecutionResults recentes                                  |
| `/api/audit?limit=50`           | audit_log entries (RISK_*, EXEC_*, SNAPSHOT_*)             |
| `/api/replay`                   | Snapshot do estado atual (para replay/timeline)            |
| `/api/replay/snapshots`         | Lista de snapshots persistidos em `dashboard_snapshots/`   |
| `/api/replay/export`            | Exporta replay em JSON ou CSV                              |
| `/api/replay/compare`           | Compara dois snapshots                                     |
| `/ws`                           | WebSocket — broadcast a cada ~5s do estado consolidado     |

## WebSocket

```js
const ws = new WebSocket("ws://localhost:8787/ws");
ws.onmessage = (e) => {
  const payload = JSON.parse(e.data);
  // payload contém: overview + sinais por camada + alertas recentes
};
```

O loop interno (`_broadcast_loop`) consulta o repository, agrega por
herói/camada usando `HERO_LAYER` mapping, e empurra para todos os
sockets conectados.

## Mapeamento Herói → Camada

Definido em `server.py::HERO_LAYER`:

```python
HERO_LAYER = {
    "Superman": "L1", "DoctorStrange": "L1", "BlackPanther": "L1",
    "Thor": "L1",     "Aquaman": "L1",       "SpiderMan": "L1",
    "Vision": "L2",   "ProfessorX": "L2",
    "Batman": "L3",   "IronMan": "L3",
    "NickFury": "L4",
}
```

Quando heróis novos forem entregues (Wolverine, Flash, Deadpool,
PortfolioManager), **adicionar entrada aqui** ou o front-end exibirá
"unmapped" para os eventos deles.

> **Drift conhecido**: PortfolioManager (Story 026) ainda não está em
> `HERO_LAYER`. Próxima Story que tocar dashboard deve adicioná-lo.

## Quando tocar / quando não tocar

### Pode mexer
- Adicionar novo endpoint REST read-only (`/api/<algo>`).
- Atualizar `HERO_LAYER` quando novo herói entra no roster.
- Melhorar visualização front-end em `static/`.
- Adicionar filtros de query string em endpoints existentes.

### Não pode mexer (sem aprovação humana)
- **Não escrever** no SQLite a partir do dashboard. Dashboard é
  read-only por princípio. Toda escrita passa por agentes Python.
- **Não expor** dados sensíveis via API: chaves, wallet privada,
  conteúdo de prompts LLM.
- **Não adicionar** endpoint que dispara ação de trading. Iron Man é o
  único caminho de execução.
- **Não rodar** dashboard em IP público sem auth. Bind `0.0.0.0` é
  para dev local — em produção exigir reverse proxy + auth básica.

## Próximos passos (registrados, não fazer agora)

1. **Auth básica** antes de bind público.
2. **Adicionar PortfolioManager** ao HERO_LAYER + cards de equity/positions na UI.
3. **Ingerir TS event-pipeline** (`memory/*.ndjson`) para unificar Python + TS na mesma timeline.
4. **Pipeline por camada (L1/L2/L3/L4)** com tempo de ciclo por herói.
5. **Telegram bot** lendo do mesmo `/api/overview` (Story 033).

## Como rodar local sem o pipeline

Útil para desenvolver o front:

```bash
# 1. Garantir que o SQLite tem dados (rodar o pipeline ao menos uma vez)
python run.py --once

# 2. Subir só o dashboard
python run.py --dashboard-only

# 3. Abrir http://localhost:8787 no browser
```

## Troubleshooting

- **404 em `/`**: confirma que `src/dashboard/static/index.html` existe.
- **WebSocket fecha imediatamente**: verifica que aiohttp e a
  versão de Python são compatíveis (3.13 recomendado).
- **`/api/overview` retorna vazio**: pipeline ainda não escreveu nada
  no SQLite. Rode `python run.py --once` antes.
- **Dashboard não recebe novos eventos**: verifique se Nick Fury está
  rodando em paralelo (`python run.py --dashboard` faz os dois) e se
  `MekkaRepository` aponta para o mesmo path em ambos os processos
  (`settings.sqlite_db_path`).
