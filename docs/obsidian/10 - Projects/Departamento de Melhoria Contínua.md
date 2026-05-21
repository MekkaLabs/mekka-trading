---
title: Departamento de Melhoria Contínua
type: projeto
tags: [projeto, continuous-improvement, squad, roadmap]
status: ativo
created: 2026-05-21
updated: 2026-05-21
---

# Departamento de Melhoria Contínua

> Design completo em `docs/CONTINUOUS-IMPROVEMENT-DEPARTMENT.md`.
> Comandado por [[Mekka]], premortem por [[Galactus]].

## Squad — ENTREGUE (2026-05-21)

7 scanners read-only/fail-silent alimentando o conselho. Fluxo:
**scanners → [[Galactus]] (premortem) → [[Mekka]] (consolida + ranqueia) → operador (`/Melhorias` + Telegram)**.

| Scanner | Domínio | Arquivo | Status |
|---|---|---|---|
| [[Beast]] | trading-ops | `beast.py` | ✅ existia |
| CodeAuditor | dev | `code_auditor.py` | ✅ novo |
| RiskScanner | trading-ops | `risk_scanner.py` | ✅ novo |
| OpsScanner | infra | `ops_scanner.py` | ✅ novo |
| [[Jean Grey]] (MemoryScanner) | memory | `jean_grey.py::scan_proposals` | ✅ novo |
| [[Ice Man]] | research | `ice_man.py` | ✅ novo |
| [[Sage]] | measurement | `sage.py` | ✅ novo |

- UI: badge de fonte + filtro por scanner em `/Melhorias` (`.impr-src-filter`).
- Validado: `/api/improvements?fresh=1` retorna propostas por fonte; 0 erros.
- CodeAuditor já detectou sozinho `server.py` (6710 linhas) como refactor HIGH.

### Guard-rails (invioláveis)
Todo scanner é read-only + fail-silent; nada executa sozinho; humano aprova;
nunca auto-merge; nunca toca `settings.py` (double-gate) nem o kill switch.

## Próximas melhorias

### Squad (polish)
- [ ] Testes unitários para os novos scanners (CodeAuditor flagou: agentes sem teste).
- [ ] **Sage v2** — medição atribuída a uma melhoria específica (antes/depois daquela mudança), marcando *efetiva / neutra / regressão* e alimentando a [[Jean Grey]].
- [ ] **Ice Man v2** — pesquisa via GitHub releases/issues + MCPs financeiros (LSEG/bigdata). Nota: o app não chama o WebSearch do Claude Code.
- [ ] KPI do departamento ([[Sage]]`.kpi()`) exposto numa tile do dashboard.

### Mainnet Binance (próxima fase — depois do squad)
Server fica em **testnet** até a virada. Já entregue: SL fail-safe + Guardião de SL.
- [ ] Guardião de SL no boot (proteger posições órfãs em segundos, não em até 5 min).
- [ ] Reconciliação completa no restart (recuperar posições + tracking no DB).
- [ ] Preset conservador 1ª semana (size 0.1% / 2x / 3 trades / 2 posições / 5% DD).
- [ ] Runbook de virada mainnet (flip `BINANCE_TESTNET=false` com checklist).
- [ ] Gates humanos H1–H6 (≥1 mês testnet, wallet dedicada/funded, assinar `docs/MAINNET-AUTHORIZATION.md`).

## Cross-references
- Heróis novos: [[Ice Man]], [[Sage]]
- Comandante/premortem: [[Mekka]], [[Galactus]]
- Memória: [[Jean Grey]]
- Índice do roster: [[_Agentes Index]]
