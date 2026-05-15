# Mekka Dashboard + AIOX Core Bridge

Este dashboard foi estruturado no padrão de observabilidade do AIOX Core:

- Fonte de verdade: armazenamento append-only/audit em SQLite (`audit_log`, `signals`, `trades`)
- Camada de transporte em tempo real: websocket para stream de estado
- API de leitura desacoplada para painéis/consumidores externos

## Mapeamento de Heróis no Dashboard

- `Professor X`: consolidação paralela (feed de auditoria)
- `Vision`: tabela de sinais recentes
- `Batman`: eventos `RISK_*` no stream
- `Iron Man`: execuções na tabela de trades
- `Nick Fury`: visão global em `overview`

## Endpoints

- `GET /api/overview`
- `GET /api/signals?limit=20`
- `GET /api/trades?limit=20`
- `GET /api/audit?limit=50`
- `GET /ws`

## Próximos passos (Story 026+)

- Ingerir também `events.jsonl`/telemetria do AIOX Core para unificar Python + TS
- Exibir pipeline por camada (L1/L2/L3/L4) com tempo de ciclo por herói
- Integrar `Wolverine` (monitor), `Flash` (scalper), `Deadpool` (simulação caos)
