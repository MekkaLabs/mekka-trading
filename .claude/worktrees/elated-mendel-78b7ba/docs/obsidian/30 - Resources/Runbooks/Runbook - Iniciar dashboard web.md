---
title: "Runbook — Iniciar dashboard web"
type: runbook
tags: [runbook, ops, dashboard]
created: 2026-05-07
severity: low
---

# Runbook — Iniciar dashboard web

> **Quando usar**: para abrir a visualização browser-first do Mekka Trading
> **Severidade**: baixa
> **Tempo médio**: 1 min

## Pré-requisitos

- Python 3.12 instalado
- `.venv` ativado: `source .venv/bin/activate`
- Dependências: `pip install -r requirements.txt`
- `.env` configurado (a partir de `.env.example`)

## Passos

### Opção A — Runtime + Dashboard juntos
```bash
python run.py --dashboard
```

### Opção B — Apenas Dashboard (lendo SQLite já alimentado)
```bash
python run.py --dashboard-only
```

### Opção C — Customizar equity inicial
```bash
python run.py --dashboard --equity 25000
```

## Validação

1. Abrir http://localhost:8787 no browser
2. Verificar overview carregando dados
3. Confirmar que WebSocket conecta (ver Network tab no DevTools — `ws://localhost:8787/ws`)
4. Endpoints REST acessíveis:
   - http://localhost:8787/api/overview
   - http://localhost:8787/api/signals
   - http://localhost:8787/api/trades
   - http://localhost:8787/api/audit

## Rollback

- `Ctrl+C` para parar o servidor
- Se a porta 8787 ficar ocupada: `lsof -i :8787` → `kill <PID>`

## Troubleshooting

| Sintoma | Causa provável | Ação |
|---|---|---|
| `ModuleNotFoundError: fastapi` | Deps não instaladas | `pip install -r requirements.txt` |
| Página em branco | SQLite vazio | Rode primeiro `python run.py --once` para popular |
| WebSocket cai constantemente | Firewall/Antivirus | Permita localhost:8787 |
| Dashboard mostra dados antigos | Cache do browser | Hard refresh (Cmd+Shift+R / Ctrl+Shift+R) |

## Pós-incidente

- [ ] Logs em `observability/store/`
- [ ] Audit em `memory/audit-log/`
- [ ] Se mudou comportamento, registrar em [[Aprendizado]]

## Referências

- [[../../20 - Areas/Arquitetura/Dashboard Web (Pixel 3D)]]
- README — seção "Dashboard Web + Pixel 3D"
- [[../../50 - MOCs/MOC - Operações & Observability]]
