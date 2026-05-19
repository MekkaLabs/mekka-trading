# Story 218 — Monitor Wiring (NickFury Integration)

**Milestone:** 34 — Monitoring & Alerting  
**Status:** Done  
**Tipo:** Pipeline Integration  

---

## Contexto

As Stories 213–217 criaram 5 serviços de monitoramento, mas nenhum estava
integrado ao pipeline principal. O NickFury não chamava nenhum deles.

---

## Goal

Integrar os 4 monitores + AlertThrottleManager ao `NickFury` para que sejam
invocados automaticamente a cada ciclo de trading.

---

## Scope Delivered

### Mudanças em `src/agents/nick_fury.py`

1. **`__init__`** — 5 novas instâncias injetadas:
   ```python
   self._throttle            = AlertThrottleManager()
   self._drawdown_monitor    = DrawdownMonitor(alerter=self._telegram)
   self._concentration_alerter = PositionConcentrationAlerter(alerter=self._telegram)
   self._pnl_tracker         = IntradayPnLTracker(alerter=self._telegram)
   self._funding_monitor     = FundingRateMonitor(alerter=self._telegram)
   ```

2. **`run_main_cycle()`** — método `_run_pre_cycle_monitors()` chamado após snapshot:
   - DrawdownMonitor com peak_equity do DailyPnLWriter
   - PositionConcentrationAlerter com posições abertas do snapshot
   - IntradayPnLTracker com PnL realizado + não-realizado do snapshot

3. **`_cycle_for_symbol()`** — FundingRateMonitor chamado após ProfessorX analysis:
   - Apenas se `analysis.funding_rate is not None`

4. **Novo método privado** `_run_pre_cycle_monitors()`:
   - Throttle aplicado por evento antes de cada monitor
   - Absorve qualquer exceção — nunca quebra o ciclo principal

---

## Hard Rules Mantidas

- `paper_trading=True` — nenhuma ordem real
- Nunca burla Batman — monitores são read-only
- Uma feature → uma story

---

## Acceptance

```python
# NickFury instancia os 5 serviços no __init__
fury = NickFury()
assert hasattr(fury, "_drawdown_monitor")
assert hasattr(fury, "_concentration_alerter")
assert hasattr(fury, "_pnl_tracker")
assert hasattr(fury, "_funding_monitor")
assert hasattr(fury, "_throttle")
```

---

## What's Next

- Milestone 35 — a definir com o operador
