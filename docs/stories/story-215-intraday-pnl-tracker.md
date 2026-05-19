# Story 215 — IntradayPnLTracker

**Milestone:** 34 — Monitoring & Alerting  
**Status:** Done  
**Tipo:** Observability / Monitoring  

---

## Contexto

O sistema já persiste P&L diário via `DailyPnLWriter` (Story 027), mas não existe
monitoramento **intraday** de P&L em tempo real. O operador não recebe alertas
automáticos quando o sistema atinge marcos positivos ou negativos durante o dia.

---

## Goal

Criar `IntradayPnLTracker`: serviço que mantém snapshots horários do P&L intraday
e dispara alertas Telegram quando P&L cruza marcos configuráveis.

---

## Scope Delivered

- `src/services/intraday_pnl_tracker.py` — `IntradayPnLTracker`
  - `record(realized_pnl, unrealized_pnl, equity_usd)` → `PnLSnapshot`
  - Snapshots guardados em memória por hora UTC (dict `{hour: PnLSnapshot}`)
  - Alertas ao cruzar marcos: `+3%`, `+5%`, `+10%` (gain) e `-2%`, `-5%` (loss)
  - `get_summary()` → string formatada para `/intraday` no bot Telegram
  - `reset_day()` — limpa snapshots para novo dia UTC
  - Nunca lança exceção
- `src/models/monitoring.py` — `PnLSnapshot` (já adicionado na Story 213)
- `tests/test_story_215_intraday_pnl_tracker.py` — 10 testes

---

## Hard Rules Mantidas

- Read-only para o pipeline — `record()` não escreve em disco
- Nunca burla Batman
- Uma feature → uma story

---

## Acceptance

```python
from src.services.intraday_pnl_tracker import IntradayPnLTracker

tracker = IntradayPnLTracker(gain_thresholds_pct=[3.0, 5.0], loss_thresholds_pct=[-2.0])

snap = await tracker.record(
    realized_pnl=350.0,
    unrealized_pnl=100.0,
    equity_usd=10_000.0,
)
assert snap.total_pnl_usd == pytest.approx(450.0)
# 4.5% → cruza marco +3% → alerta Telegram disparado
```

---

## What's Next

- Story 216 — FundingRateMonitor
- Story 217 — AlertThrottleManager
