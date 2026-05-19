# Story 217 — AlertThrottleManager

**Milestone:** 34 — Monitoring & Alerting  
**Status:** Done  
**Tipo:** Observability / Anti-Fatigue  

---

## Contexto

As Stories 213–216 criaram 4 monitores independentes, cada um com seu próprio
dedup interno. Em cenários de mercado volátil, múltiplos monitores podem disparar
alertas em rápida sucessão, causando fadiga de alertas no operador.

Faltava uma **camada centralizada de throttle** que:
1. Garanta cooldown mínimo entre alertas do mesmo tipo
2. Permita configurar janelas distintas por evento (ex: drawdown = 30min, funding = 2h)
3. Registre métricas de alertas suprimidos para diagnóstico

---

## Goal

Criar `AlertThrottleManager`: gateway central de dedup e throttle que os monitores
podem consultar antes de enviar qualquer alerta Telegram.

---

## Scope Delivered

- `src/services/alert_throttle_manager.py` — `AlertThrottleManager`
  - `is_allowed(event_key, cooldown_seconds)` → `bool`
  - `record_sent(event_key)` — marca evento como enviado (atualiza timestamp)
  - `get_stats()` → dict com `{event_key: {sent, suppressed, last_sent}}`
  - `reset()` — limpa todo o estado (novo dia UTC)
  - Thread-safe: usa lock asyncio para operações concorrentes
  - Nunca lança exceção
- `tests/test_story_217_alert_throttle_manager.py` — 9 testes

---

## Hard Rules Mantidas

- Read-only para o pipeline — não interfere em decisões de trade
- Nunca burla Batman
- Uma feature → uma story

---

## Acceptance

```python
from src.services.alert_throttle_manager import AlertThrottleManager

manager = AlertThrottleManager()
assert manager.is_allowed("DRAWDOWN_WARNING", cooldown_seconds=1800)  # True (primeiro)
manager.record_sent("DRAWDOWN_WARNING")
assert not manager.is_allowed("DRAWDOWN_WARNING", cooldown_seconds=1800)  # False (cooldown)

stats = manager.get_stats()
assert stats["DRAWDOWN_WARNING"]["sent"] == 1
assert stats["DRAWDOWN_WARNING"]["suppressed"] == 1
```

---

## What's Next

- Milestone 35 — próximo milestone a definir com o operador
- Integração dos 4 monitores com AlertThrottleManager no NickFury (futura story)
