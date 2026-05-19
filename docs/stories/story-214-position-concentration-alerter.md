# Story 214 — PositionConcentrationAlerter

**Milestone:** 34 — Monitoring & Alerting  
**Status:** Done  
**Tipo:** Observability / Risk Monitoring  

---

## Contexto

Batman garante que nenhuma posição individual ultrapasse `max_position_size_pct`
**antes** da abertura. Mas após a abertura, a equity pode cair e a posição passar a
representar uma fatia desproporcional do portfólio — situação de concentração não
monitorada.

Adicionalmente, o operador não tinha visibilidade sobre a concentração atual do
portfólio sem acessar o dashboard manualmente.

---

## Goal

Criar `PositionConcentrationAlerter`: serviço que, a cada ciclo, verifica se
alguma posição aberta representa mais que `max_concentration_pct` da equity atual
e dispara alerta Telegram com detalhes da posição.

---

## Scope Delivered

- `src/services/position_concentration_alerter.py` — `PositionConcentrationAlerter`
  - `check(positions, equity_usd)` → `list[ConcentrationAlert]`
  - Aceita lista de dicts `{symbol, notional_usd, side}` — desacoplado dos models de execution
  - Dedup por símbolo: alerta uma vez por posição por sessão
  - Nunca lança exceção
- `src/models/monitoring.py` — `ConcentrationAlert` (já adicionado na Story 213)
- `tests/test_story_214_position_concentration_alerter.py` — 9 testes

---

## Hard Rules Mantidas

- Read-only: nunca modifica posições
- Nunca burla Batman
- Uma feature → uma story

---

## Acceptance

```python
from src.services.position_concentration_alerter import PositionConcentrationAlerter

alerter = PositionConcentrationAlerter(max_concentration_pct=0.25)  # 25%

positions = [{"symbol": "BTC", "notional_usd": 3000.0, "side": "LONG"}]
alerts = await alerter.check(positions=positions, equity_usd=10_000.0)
# 30% > 25% → alerta
assert len(alerts) == 1
assert alerts[0].symbol == "BTC"
assert alerts[0].concentration_pct == pytest.approx(30.0)
```

---

## What's Next

- Story 215 — IntradayPnLTracker
- Story 217 — AlertThrottleManager (dedup centralizado)
