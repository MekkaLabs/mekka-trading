# Story 216 — FundingRateMonitor

**Milestone:** 34 — Monitoring & Alerting  
**Status:** Done  
**Tipo:** Observability / Market Intelligence  

---

## Contexto

Batman já verifica funding rate **antes de cada trade** via `funding_gate_enabled`
(settings). Mas este gate só age quando há um sinal pronto. Não existe monitoramento
**proativo** de funding extremo — o operador não é notificado quando as taxas atingem
níveis anormais fora de um ciclo de trade.

Funding extremo é sinal importante de mercado: funding muito alto indica longs
excessivos (mercado sobrecomprado), funding muito negativo indica shorts excessivos.

---

## Goal

Criar `FundingRateMonitor`: serviço que recebe a taxa de funding atual e dispara
alerta Telegram quando atingir níveis WARN ou BLOCK — independente de haver trade.

---

## Scope Delivered

- `src/services/funding_rate_monitor.py` — `FundingRateMonitor`
  - `check(symbol, funding_rate_pct)` → `FundingAlert | None`
  - 4 thresholds reutilizados de `settings`:
    - `funding_long_warn_pct` — WARN para longs (funding positivo elevado)
    - `funding_long_block_pct` — BLOCK para longs (funding positivo extremo)
    - `funding_short_warn_pct` — WARN para shorts (funding negativo elevado)
    - `funding_short_block_pct` — BLOCK para shorts (funding negativo extremo)
  - Dedup por (symbol, direction, severity) — uma vez por nível por sessão
  - Nunca lança exceção
- `src/models/monitoring.py` — `FundingAlert` (já adicionado na Story 213)
- `tests/test_story_216_funding_rate_monitor.py` — 10 testes

---

## Hard Rules Mantidas

- Read-only: nunca bloqueia trades (isso é responsabilidade do Batman)
- Nunca burla Batman
- Uma feature → uma story

---

## Acceptance

```python
from src.services.funding_rate_monitor import FundingRateMonitor

monitor = FundingRateMonitor()
alert = await monitor.check(symbol="BTC", funding_rate_pct=0.12)
# 0.12% > funding_long_block_pct (0.10%) → BLOCK + HIGH_LONG
assert alert.severity == "BLOCK"
assert alert.direction == "HIGH_LONG"
```

---

## What's Next

- Story 217 — AlertThrottleManager (dedup centralizado)
