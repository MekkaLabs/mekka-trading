# Story 213 — DrawdownMonitor

**Milestone:** 34 — Monitoring & Alerting  
**Status:** Done  
**Tipo:** Observability / Risk Monitoring  

---

## Contexto

O `TelegramAlerter` já possui o método `drawdown_alert()` (Story 035), mas ele
precisa ser chamado manualmente. Não existe nenhum serviço que **monitoramente
ativamente** o drawdown intraday e dispare alertas em estágios progressivos.

O operador só descobria o drawdown crítico quando o kill switch já tinha engajado
— sem tempo de reação antecipada.

---

## Goal

Criar `DrawdownMonitor`: serviço leve que, a cada ciclo, compara a equity atual
contra o pico do dia e dispara alertas Telegram em **3 níveis escalonados**:

| Nível | Threshold | Ação |
|-------|-----------|------|
| `WARNING` | 50 % do limite diário | Alerta informativo |
| `CRITICAL` | 80 % do limite diário | Alerta urgente |
| `KILL`    | 100 % do limite diário | Alerta + recomenda kill switch |

---

## Scope Delivered

- `src/services/drawdown_monitor.py` — `DrawdownMonitor`
  - `check(current_equity, peak_equity)` → `DrawdownAlert | None`
  - Dedup interno por nível: cada nível dispara **uma única vez** por sessão
  - Integração com `TelegramAlerter.alert()` (método genérico — sem dependência circular)
  - Sem estado em disco — reseta ao reiniciar (paper-trading-first)
- `src/models/monitoring.py` — `DrawdownAlert` Pydantic model
- `tests/test_drawdown_monitor.py` — 8 testes

---

## Hard Rules Mantidas

- `paper_trading=True` — nenhuma ordem real
- Nunca burlar Batman — este serviço é read-only (observação pura)
- Uma feature → uma story
- Nunca lança exceção para o caller (absorve internamente)

---

## Acceptance

```python
from src.services.drawdown_monitor import DrawdownMonitor

monitor = DrawdownMonitor(max_daily_drawdown_pct=0.10)  # 10% limite

alert = await monitor.check(current_equity=9500.0, peak_equity=10_000.0)
# drawdown = 5% → 50% do limite → WARNING
assert alert.level == "WARNING"
assert alert.drawdown_pct == pytest.approx(5.0)

# segundo check no mesmo nível → None (dedup)
alert2 = await monitor.check(current_equity=9500.0, peak_equity=10_000.0)
assert alert2 is None
```

---

## What's Next

- Story 214 — PositionConcentrationAlerter
- Story 217 — AlertThrottleManager (dedup centralizado entre todos os monitors)
