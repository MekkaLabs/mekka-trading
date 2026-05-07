---
title: MOC — Risco & Compliance
type: moc
tags: [moc, risco]
created: 2026-05-07
---

# 🛡️ MOC — Risco & Compliance

> Mapa vivo dos controles de risco, kill-switch e governança.

## Princípios

1. **Risk-First**: nada chega à execução sem passar pelo risk-engine
2. **Kill Switch**: governança permanente, padrão controlado por governança
3. **Live Bloqueado**: trade real é bloqueado na camada de risco
4. **Auditável**: todo veto/approval gera registro

## Limites Configuráveis

| Variável | Default | Descrição |
|---|---|---|
| `MAX_POSITION_SIZE_PCT` | 0.02 | Posição máxima como fração do equity |
| `MAX_LEVERAGE` | 5 | Alavancagem máxima por trade |
| `MAX_DAILY_DRAWDOWN_PCT` | 0.10 | Drawdown diário máximo antes do halt |
| `PAPER_TRADING` | true | Modo paper (sem ordens reais) |

## Componentes do Risk Engine

- Policy Limits — limites declarativos
- Risk Regime Manager — detecção automática de regime crítico
- Kill Switch — corte imediato em condição crítica
- Validation Gates — gates obrigatórios entre etapas do workflow

## Stories já implementadas (relacionadas a risco)

- story-001 — Mekka Foundation
- story-003 — Stress regime
- story-005 — Exchange capability validator
- story-019 — Ops threshold alerting
- story-020 — Ops alert suppression window
- story-021 — Regime-aware ops severity
- story-022 — Ops mission commander routing

## Notas de Risco

```dataview
LIST
FROM #risco
WHERE file.path != this.file.path
SORT file.mtime DESC
```

## Próximos passos

- [ ] Documentar matriz de regimes ↔ controles
- [ ] Mapear todos os kill-switch triggers
- [ ] Criar runbook "ativação manual do kill-switch"
